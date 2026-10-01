from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.idempotency import check_idempotency
from app.main import app, get_db_session, verify_api_key

client = TestClient(app)


# Mock DB Session
class MockAsyncSession:
    """
    Mock SQLAlchemy AsyncSession to handle db.add() and await db.flush() in tests.
    """

    def __init__(self):
        self.add = MagicMock()
        self.flush = AsyncMock()


# Dependency Override
async def overrides_get_db():
    """
    Mock Database session generator for testing
    :return:
    """
    yield MockAsyncSession()


async def override_check_idempotency():
    """
    Bypass Redis Idempotency check during unit tests
    :return:
    """
    return None


def override_verify_api_key():
    """
    Bypass API key validation during unit tests."""
    return "mocked-valid-key"


# Apply overrides to the FastAPI App
app.dependency_overrides[get_db_session] = overrides_get_db
app.dependency_overrides[check_idempotency] = override_check_idempotency
app.dependency_overrides[verify_api_key] = override_verify_api_key


def test_health_check():
    """
    Verify base healthcheck
    :return:
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "EnergyPulse API"}


def test_ingest_valid_telemetry():
    """
    Test successful ingestion of telemetry Data
    :return:
    """
    payload = {
        "device_id": "bess_unit_01",
        "power_kw": 1500.0,
        "state_of_charge": 88.5,
        "recorded_at": "2026-09-30T12:00:00Z",
    }
    response = client.post("/api/v1/telemetry", json=payload)
    # Expect 202 Accepted as defined in main.py
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["processed_device"] == "bess_unit_01"


def test_ingest_invalid_telemetry_validation():
    """
    Ensure Pydantic catches invalid telemetry fields (e.g., invalid state_of_charge)
    :return:
    """
    # State of charge cannot exceed 100% or be negative
    invalid_payload = {
        "device_id": "bess_unit_01",
        "power_kw": "not-a-number",  # Type mismatch
        "state_of_charge": 150.0,  # Out of range (> 100)
        "recorded_at": "2026-09-30T12:00:00Z",
    }
    response = client.post("/api/v1/telemetry", json=invalid_payload)
    # FastAPI/Pydantic automatically returns 422 Unprocessable Entity for schema
    # validation failures
    assert response.status_code == 422
