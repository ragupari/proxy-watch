# ProxyMaze Real-Time Proxy Monitoring and Alerting System

ProxyMaze is a production-grade HTTP API built with FastAPI that continuously monitors proxy endpoint health in the background. It automatically detects when the proxy pool's failure rate exceeds a specified threshold (20%) and triggers webhook alerts before clients discover an outage.

## Features

-   **Background Monitoring:** Runs continuously in the background using `asyncio` loops, completely independent of HTTP requests.
-   **Real HTTP Probes:** Uses `httpx` to probe proxy URLs using actual HTTP requests (no mocked or cached responses).
-   **Alert State Machine:** Enforces a strict single active alert constraint. Detects threshold breaches (>= 20%) and resolves them (< 20%) seamlessly, issuing new unique alert IDs for subsequent breaches.
-   **Robust Webhooks:** Ensures exactly-once webhook delivery per state transition. Includes exponential backoff retry logic for transient errors (500, 502, 503, 504).
-   **Integrations:** Out-of-the-box formatted payload support for Slack and Discord alerts.
-   **State Consistency:** Ensures identical truth across endpoints (`/proxies`, `/alerts`) regarding the failure state and proxy metadata.
-   **Validation:** Seamless handling of unknown JSON fields in incoming requests via robust Pydantic schemas.

## Technology Stack

-   **Framework:** FastAPI + Python 3.11+
-   **Server:** Uvicorn (ASGI)
-   **Client:** HTTPX (Async HTTP Client for probing)
-   **Validation:** Pydantic

## Installation

1.  **Clone the Repository** and navigate to the project directory.

2.  **Set up a Virtual Environment**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

## Running the Application

Start the server using `uvicorn`:

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Add `--reload` for hot-reloading during development:
```bash
uvicorn src.main:app --reload
```

## API Endpoints

### Configuration & Health
- `GET /health` - Health check.
- `GET /config` - Retrieve current background monitor check interval and probe timeout.
- `POST /config` - Set the monitoring configuration. Applies immediately to the next check cycle.

### Proxy Pool Management
- `POST /proxies` - Load proxy URLs into the pool. Extrapolates IDs automatically from URL endpoints. Supports completely replacing or appending to the pool.
- `GET /proxies` - Survey the entire pool, providing aggregate stats and individual proxy health values.
- `GET /proxies/{id}` - Full detailed view of a single proxy's uptime and stats.
- `GET /proxies/{id}/history` - Historical check states for a single proxy.
- `DELETE /proxies` - Clears the pool (does not delete existing alerts).

### Alerts & Webhooks
- `GET /alerts` - Retrieve a history of all active and resolved threshold breach alerts.
- `POST /webhooks` - Register a standard JSON webhook receiver.
- `POST /integrations` - Register a Slack or Discord formatted webhook receiver.

### Observability
- `GET /metrics` - Operational stats (total checks, active alerts, total webhook deliveries).

## Testing

Run the included integration and unit tests via `pytest`:

```bash
PYTHONPATH=. pytest tests/
```

The tests cover state machine constraints, proxy status tracking, webhook registry, and duplicate prevention.

## Architecture Guidelines

-   **State:** The current version utilizes in-memory storage singletons located in `src/state.py`.
-   **Background Monitor:** Located in `src/monitor.py`. Do not block this async loop; it runs `check_interval_seconds` timeouts continuously upon app startup.
-   **Webhook Dispatch:** Located in `src/webhooks.py`. It asynchronously posts alerts avoiding locking the monitoring engine.
