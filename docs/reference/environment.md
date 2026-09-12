# Environment Variables

KITT reads the following environment variables. All are optional and have
sensible defaults.

## General

| Variable | Description | Default |
|----------|-------------|---------|
| `KITT_HOME` | Configuration and data directory | `~/.kitt/` |
| `KITT_SECRET_KEY` | Flask session secret key | Random 32-byte hex |

## Docker and models

| Variable | Description | Default |
|----------|-------------|---------|
| `DOCKER_HOST` | Docker daemon socket URL | `unix:///var/run/docker.sock` |
| `MODEL_PATH` | Default path to model weights on the host | *(none)* |

## TLS and certificates

| Variable | Description | Default |
|----------|-------------|---------|
| `KITT_TLS_CERT` | Path to TLS certificate file | Auto-generated in `~/.kitt/certs/` |
| `KITT_TLS_KEY` | Path to TLS private key file | Auto-generated in `~/.kitt/certs/` |
| `KITT_TLS_CA` | Path to CA certificate for mTLS | Auto-generated in `~/.kitt/certs/` |

When no certificate paths are set and TLS is not disabled (`--insecure`),
KITT auto-generates a self-signed CA and server certificate on first
launch.

## API authentication

| Variable | Description | Default |
|----------|-------------|---------|
| `KITT_AUTH_TOKEN` | Bearer token for REST API authentication | *(none)* |

If neither `--auth-token` nor `KITT_AUTH_TOKEN` is set, authenticated
endpoints will reject all requests.

## Monitoring stack

| Variable | Description | Default |
|----------|-------------|---------|
| `KITT_PROMETHEUS_PORT` | Prometheus listen port | `9090` |
| `KITT_GRAFANA_PORT` | Grafana listen port | `3000` |
| `KITT_GRAFANA_PASSWORD` | Grafana admin password | `kitt` |
| `KITT_INFLUXDB_PORT` | InfluxDB listen port | `8086` |
| `KITT_INFLUXDB_TOKEN` | InfluxDB admin API token | `kitt-influx-token` |
| `KITT_INFLUXDB_PASSWORD` | InfluxDB admin password | `kittpwd123` |

## Database

| Variable | Description | Default |
|----------|-------------|---------|
| `KITT_DB_PATH` | Path to SQLite database file | `~/.kitt/kitt.db` |

## Web UI

| Variable | Description | Default |
|----------|-------------|---------|
| `KITT_MODEL_DIR` | Directory the Models tab scans for local model files | `~/.kitt/models` |
| `DEVON_URL` | Devon server URL for the Devon tab iframe and API access | *(none)* |
| `DEVON_API_KEY` | API key for authenticating with remote Devon | *(none)* |

`KITT_MODEL_DIR`, `DEVON_URL`, and the results directory can also be
configured from the **Settings** page in the web dashboard. UI-saved
values take priority: **DB > environment variable > default**.

## Agent

| Variable | Description | Default |
|----------|-------------|---------|
| `KITT_AGENT_ID` | Override agent identifier | Auto-generated UUID |
| `KITT_CONTROLLER_URL` | URL of the controller (web) instance | *(none)* |
