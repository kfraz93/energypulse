# EnergyPulse

Production-grade, high-throughput asynchronous telemetry ingestion pipeline designed for distributed Battery Energy Storage Systems (BESS). 

Built with **FastAPI**, **TimescaleDB**, **Celery**, **Redis**, and instrumented for **Prometheus/Grafana** observability.

---

##  Architecture & Tech Stack

* **API Framework:** `FastAPI` (Async request handling, Pydantic v2 validation)
* **Time-Series Database:** `TimescaleDB` (Optimized hyper-tables for high-frequency IoT telemetry)
* **Task Queue & Broker:** `Celery` backed by `Redis` for asynchronous processing and background ingestion
* **Idempotency Layer:** Redis-backed caching key evaluation to prevent duplicate writes during network retries
* **Observability:** Prometheus `/metrics` endpoint with automated Grafana dashboard integration
* **Containerization:** Docker Compose with multi-service health checks (`pg_isready`, `redis-cli ping`)
* **Package Management & CI/CD:** `uv` for lightning-fast dependency resolution and GitLab CI pipelines (`ruff` linting + `pytest`)

---

## Quick Start (Local Development)

### Prerequisites
* Docker & Docker Compose installed on your machine.

### 1. Clone & Run the Stack
Spin up the entire containerized infrastructure (API, TimescaleDB, Redis, Prometheus, Grafana) with a single command:

```bash
docker compose up --build -d
```

2. Verify Container Health
Check that all services are running and healthy:

```Bash
docker compose ps
```

3. Test Telemetry Ingestion
Send a test telemetry payload to the API:

```Bash
curl -X 'POST' \
  '[http://127.0.0.1:8000/api/v1/telemetry](http://127.0.0.1:8000/api/v1/telemetry)' \
  -H 'accept: application/json' \
  -H 'x-api-key: suena-secret-green-key' \
  -H 'Idempotency-Key: test-key-001' \
  -H 'Content-Type: application/json' \
  -d '{
  "device_id": "bess_unit_01",
  "power_kw": 1500.0,
  "state_of_charge": 88.5,
  "recorded_at": "2026-09-30T12:00:00Z"
}'
```

🧪 Running Tests & Linting
If you want to run the test suite and code quality checks locally using uv:

``` Bash
# Run lint checks with Ruff
uv run ruff check .

# Run pytest integration suite
uv run pytest -v
```
## Deployment Strategy
Artifacts: Code is containerized via a secure Dockerfile and targeted for serverless deployment on AWS ECS Fargate via Amazon ECR (Elastic Container Registry).

CI/CD: Automated pipelines in GitLab CI validate code style, run unit/integration tests against PostgreSQL/Redis services, and ensure zero regressions before merge.