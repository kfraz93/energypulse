from celery import Celery

# Initialize Celery with edis as Broker and Backend

celery_app = Celery(
    "energy_pulse_tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


# --- Mock Database Session Dependency ---
class MockDBSession:
    def add_telemetry(self, device_id: str, power: float):
        # In production, this executes an INSERT statement into PostgreSQL / TimescaleDB
        print(
            f"[Database Worker] INSERT INTO telemetry (device_id, power_kw) VALUES"
            f" ('{device_id}', {power});"
        )

    def close(self):
        print("[Database Worker] Session closed.")


# Define a Background Task
@celery_app.task(name="process_telemetry_async")
def process_telemetry_async(device_id: str, power_kw: float):
    """
    Celery background worker task that opens a database session
    and persists the telemetry data asynchronously.
    :param device_id:
    :param power_kw:
    :return:
    """
    print(
        f"[Celery Worker] Starting background processing for "
        f"device: {device_id} ({power_kw} kW)..."
    )

    db = MockDBSession()
    try:
        db.add_telemetry(device_id, power_kw)
    finally:
        db.close()

    print(
        f"[Celery Worker] Successfully processed and stored telemetry for {device_id}!"
    )
    return {"status": "processed", "device_id": device_id, "power_kw": power_kw}
