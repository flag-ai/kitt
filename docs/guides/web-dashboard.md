# Web Dashboard

The KITT web dashboard provides a browser-based UI for browsing results,
managing agents, running campaigns, and interacting with the REST API.
It requires the `web` extra (`poetry install -E web`).

## Launching the Dashboard

```bash
kitt web --port 8080 --results-dir ./results
```

The full set of options:

| Option | Default | Description |
|---|---|---|
| `--port` | 8080 | Port to serve on |
| `--host` | 0.0.0.0 | Host to bind to |
| `--results-dir` | current directory | Path to results directory |
| `--debug` | off | Enable Flask debug mode with auto-reload |
| `--legacy` | off | Use the legacy read-only dashboard |
| `--insecure` | off | Disable TLS (development only) |
| `--tls-cert` | auto | Path to TLS certificate |
| `--tls-key` | auto | Path to TLS private key |
| `--tls-ca` | auto | Path to CA certificate |
| `--auth-token` | none | Bearer token for API authentication |

## TLS Configuration

By default, KITT auto-generates a self-signed CA and server certificate on
first launch. The CA fingerprint is printed to the console so agents and
clients can verify the server identity.

**Custom certificates**: Supply your own with `--tls-cert` and `--tls-key`:

```bash
kitt web --tls-cert /path/to/cert.pem --tls-key /path/to/key.pem
```

**Development mode**: Disable TLS entirely with `--insecure`. This is
intended only for local development -- do not use it in production:

```bash
kitt web --insecure --debug
```

## Authentication

Enable API authentication with `--auth-token`. Clients must include
`Authorization: Bearer <token>` in API requests:

```bash
kitt web --auth-token my-secret-token
```

The token can also be set via the `KITT_AUTH_TOKEN` environment variable.

## Legacy Mode

The legacy dashboard is a read-only single-page viewer from KITT v1. It
scans `kitt-results/` and legacy `karr-*` directories for `metrics.json` files and
renders a summary table:

```bash
kitt web --legacy --results-dir ./kitt-results
```

Legacy mode does not require a database and does not support agents,
campaigns, or the REST API beyond basic result listing.

## REST API Endpoints

The full dashboard registers API blueprints under `/api/v1/`:

| Endpoint | Description |
|---|---|
| `GET /api/v1/health` | Health check |
| `GET /api/v1/results` | List and query benchmark results |
| `GET /api/v1/agents` | List registered agents |
| `POST /api/v1/agents/register` | Agent registration |
| `GET /api/v1/agents/<id>/settings` | Get agent settings |
| `PUT /api/v1/agents/<id>/settings` | Update agent settings |
| `POST /api/v1/agents/<id>/cleanup` | Trigger storage cleanup |
| `GET /api/v1/campaigns` | List campaigns |
| `POST /api/v1/campaigns` | Create a new campaign |
| `GET /api/v1/models` | List known models |
| `POST /api/v1/quicktest` | Submit a quick benchmark run |
| `GET /api/v1/events` | Server-sent events for live updates |

All mutable endpoints require a valid `Authorization` header when
`--auth-token` is set.

## Quick Test

Quick Test lets you run a single benchmark on a remote agent directly
from the browser. The feature has three pages:

**History** (`/quicktest`): Lists all past and in-progress tests with
status filter chips (queued, dispatched, running, completed, failed).
Shows model, engine, agent, status badge, and creation time. Click any
row to open the detail page.

**New Test** (`/quicktest/new`): A searchable model dropdown loads
models from Devon's `manifest.json` in the configured model directory.
Type to filter by model name with fuzzy substring matching, or enter a
custom path manually. Select an agent, engine, and benchmark, then
launch. The page redirects to the detail view automatically.

**Detail** (`/quicktest/<id>`): Displays test metadata (agent, engine,
benchmark, suite, timestamps) and log output. For active tests (queued,
dispatched, running), the page subscribes to
`/api/v1/events/stream/<test_id>` via SSE and streams log lines in
real time. For completed or failed tests, stored log lines are loaded
from the database. This lets you navigate away and return to view full
logs later.

## Settings

The **Settings** page lets you configure key paths and integrations
directly from the web UI without restarting the server:

| Setting | Environment Variable | Default |
|---------|---------------------|---------|
| Model Directory | `KITT_MODEL_DIR` | `~/.kitt/models` |
| Devon URL | `DEVON_URL` | *(none)* |
| Results Directory | `--results-dir` CLI flag | Current directory |

Values saved through the UI are stored in the database and take
priority over environment variables. Clearing a field reverts to the
environment variable or default. Changes take effect immediately
without a restart.

The Devon URL can also be configured inline on the **Devon** page when
it hasn't been set yet.

### Agent Settings

Per-agent settings are configured on each agent's detail page, not the
global Settings page. Navigate to **Agents > (agent name)** to find the
Settings card. These settings are synced to the agent via the heartbeat
response:

| Setting | Description |
|---------|-------------|
| Model Storage Directory | Local directory for model copies |
| Model Share Source (NFS) | NFS share source (e.g., `nas:/volume1/models`) |
| Model Share Mount Point | Local mount point for the NFS share |
| Auto Cleanup | Delete local model copies after benchmarks |
| Heartbeat Interval | Seconds between heartbeats (10-300) |

### Storage Monitoring

The agent detail page also shows a Storage card with the current
disk usage from heartbeat data. The "Clean Storage" button queues a
`cleanup_storage` command that the agent will pick up on its next
heartbeat, deleting all cached models from local storage.

## Database

The full dashboard uses SQLite stored at `~/.kitt/kitt.db`. Schema
migrations run automatically on startup. The database tracks agents,
campaigns, and indexed results.
