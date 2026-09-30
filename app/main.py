import logging
import os
import sys
from datetime import datetime
from typing import Annotated

import anyio.to_thread
import sentry_sdk
from fastapi import Depends, FastAPI, Header, HTTPException, status
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field, field_validator
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import process_telemetry_async
from app.database import get_db_session
from app.idempotency import check_idempotency, save_idempotency_response
from app.models import TelemetryRecord

# Sentry Error tracking Initialization
SENTRY_DSN = os.getenv("SENTY_DSN", "")  # Optional in dev required in prod
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=1.0,  # 100% tace rate for dev/testing
        environment=os.getenv("APP_ENV", "development"),
    )

# Logging configuration
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | &(names)s | %(message)s",
)
logger = logging.getLogger("energypulse.api")

app = FastAPI(
    title="Energypulse Telemetry API",
    version="1.0.0",
    description="Green tech asset telemetry ingestion service for Suena prep",
)

# Prometheus Metric Instrumentation
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# --- Dependency Injection Mock ---


class Settings:
    app_env: str = "development"
    max_power_limit_kw: float = 5000.0


def get_settings() -> Settings:
    """
    :return:
    """
    return Settings()


# --- Mock Authentication Dependency
def verify_api_key(x_api_key: Annotated[str | None, Header()] = None) -> str:
    """
    Validates incoming request headers for a secret API key.
    :param x_api_key:
    :return:
    """
    expected_key = "suena-secret-green-key"
    if x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key in request headers.",
        )
    return x_api_key


# --- Synchronous Helper (Simulating legacy blocking hardware parsing) ---
def parse_legacy_inverter_packet(raw_data_string: str) -> float:
    """
    Imaginary blocking third-party library function
    :param raw_data_string:
    :return:
    """
    return float(len(raw_data_string) * 10.5)


# --- Pydantic v2 Input Validation Schema --
class BatteryTelemetry(BaseModel):
    device_id: Annotated[
        str,
        Field(
            description="Unique identifier for the energy storage asset.",
            examples=["storage_unit_alpha_01"],
        ),
    ]
    power_kw: Annotated[
        float,
        Field(
            description="Active power in kW (+ charging, - discharging)",
            examples=[1250.5],
        ),
    ]
    state_of_charge: Annotated[
        float,
        Field(
            ge=0.0,
            le=100.0,
            description="Battery state of charge percentage (0-100)",
            examples=[85.2],
        ),
    ]
    recorded_at: Annotated[
        datetime,
        Field(
            description="Timestamp when telemetry sample was captured",
            examples=["2026-09-27T10:30:00Z"],
        ),
    ]

    @field_validator("power_kw")
    @classmethod
    def validate_power_limits(cls, value: float) -> float:
        """
        Custom validator to ensure power spikes do not exceed physical safety bounds.
        :param value:
        :return:
        """
        if abs(value) > 10000.0:
            raise ValueError(
                "Power output reading exceeds maximum allowable threshold of 10,000 kW."
            )
        return value


# --- Async API Endpoint with DB persistance ---
@app.post("/api/v1/telemetry", status_code=status.HTTP_202_ACCEPTED)
async def ingest_telemetry(
    payload: BatteryTelemetry,
    settings: Annotated[Settings, Depends(get_settings)],
    api_key: Annotated[str, Depends(verify_api_key)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Depends(check_idempotency)] = None,
):
    """
    Asynchronous ingestion endpoint for real-time energy storage telemetry.
    :param payload:
    :param settings:
    :param api_key:
    :param db
    :return:
    """
    logger.info(
        f"Processing telemetry ingestion for device: {payload.device_id} "
        f"| Power: {payload.power_kw} kW"
    )
    if abs(payload.power_kw) > settings.max_power_limit_kw:
        logger.error(
            f"Power limit violation: {payload.power_kw} kW exceeds "
            f"limit of {settings.max_power_limit_kw} kW"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Power {payload.power_kw} kW exceeds environment safety limit of "
            f"{settings.max_power_limit_kw} kW.",
        )
    # Persist directly into PostgreSQL via Async SQLAlchemy
    db_record = TelemetryRecord(
        device_id=payload.device_id,
        power_kw=payload.power_kw,
        state_of_charge=payload.state_of_charge,
        recorded_at=payload.recorded_at,
    )
    db.add(db_record)
    await db.flush()  # Flushes to generate IDs/timestamps without committing fully yet

    # trigger the Celery background task asynchronously
    task = process_telemetry_async.delay(payload.device_id, payload.power_kw)
    response_payload = {
        "status": "accepted",
        "task_id": task.id,
        "message": "Telemetry payload queued for background processing.",
        "processed_device": payload.device_id,
        "authenticated_client_suffix": api_key[-4:],
    }
    await save_idempotency_response(idempotency_key, response_payload)
    logger.info(
        f"Successfully queued telemetry task {task.id} for device {payload.device_id}"
    )
    return response_payload


# --- Endpoint utilizing Threadpool Offloading
@app.post("/api/v1/telemetry/legacy-parse", status_code=status.HTTP_201_CREATED)
async def ingest_legacy_telemetry(
    raw_packet: str, settings: Annotated[Settings, Depends(get_settings)]
):
    """
    Demonstrates running a blocking synchronous legacy parser
    safely in an AnyIO threadpool so it doesn't block the FastAPI event loop.
    :param raw_packet:
    :param settings:
    :return:
    """
    logger.info(f"Parsing legacy hardware packet of length {len(raw_packet)}")
    parsed_power = await anyio.to_thread.run_sync(
        parse_legacy_inverter_packet, raw_packet
    )
    if abs(parsed_power) > settings.max_power_limit_kw:
        logger.warning(
            f"Derived legacy power {parsed_power} kW exceeded safety threshold."
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Derived legacy power {parsed_power} kW exceeds limit of"
            f" {settings.max_power_limit_kw} kW",
        )
    return {
        "status": "success",
        "environment": settings.app_env,
        "raw_packet_length": len(raw_packet),
        "derived_power_kw": parsed_power,
    }


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    logger.debug("Health check probe executed.")
    return {"status": "healthy", "service": "EnergyPulse API"}
