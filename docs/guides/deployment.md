# Docker Deployment

KITT can generate composable Docker deployment stacks using `kitt stack`. Each
stack is a `docker-compose.yaml` built from the components you select, stored
at `~/.kitt/stacks/<name>/`.

## Generating a Stack

```bash
kitt stack generate <name> [OPTIONS]
```

At least one component flag is required. Available components:

| Flag | Component | Description |
|---|---|---|
| `--web` | Web UI + REST API | Full Flask dashboard with agents, campaigns, results, and models |
| `--reporting` | Reporting dashboard | Lightweight read-only results viewer |
| `--agent` | Agent daemon | Runs on GPU servers, executes benchmarks on behalf of the web server |
| `--postgres` | PostgreSQL | Persistent database backend |
| `--monitoring` | Monitoring stack | Prometheus + Grafana + InfluxDB |

`--web` and `--reporting` are **mutually exclusive** -- use one or the other.

## Port Configuration

| Option | Default | Component |
|---|---|---|
| `--port` | 8080 | Web UI or reporting dashboard |
| `--agent-port` | 8090 | Agent daemon |
| `--postgres-port` | 5432 | PostgreSQL |
| `--grafana-port` | 3000 | Grafana |
| `--prometheus-port` | 9090 | Prometheus |
| `--influxdb-port` | 8086 | InfluxDB |

## Auth Tokens and Secrets

| Option | Description |
|---|---|
| `--auth-token` | Bearer token for REST API authentication |
| `--secret-key` | Flask secret key for session signing |
| `--postgres-password` | PostgreSQL password (default: `kitt`) |
| `--server-url` | KITT server URL for agent registration |

Tokens and passwords are written into the generated `.env` file alongside the
`docker-compose.yaml`.

## Stack Lifecycle

### Generate

```bash
kitt stack generate prod --web --postgres --monitoring --auth-token mytoken
```

### Start

```bash
kitt stack start --name prod
```

### Check Status

```bash
kitt stack status --name prod
```

### Stop

```bash
kitt stack stop --name prod
```

### List All Stacks

```bash
kitt stack list
```

### Remove

```bash
kitt stack remove prod
kitt stack remove prod --delete-files   # also removes generated files
```

## Example Workflows

### Full Web Stack with Database

A production-like deployment with the web UI, PostgreSQL for persistent
storage, and API authentication:

```bash
kitt stack generate prod --web --postgres --port 8080 --auth-token mytoken
kitt stack start --name prod
```

### Reporting-Only Stack

A lightweight read-only dashboard for viewing existing results:

```bash
kitt stack generate reports --reporting --port 8080
kitt stack start --name reports
```

### GPU Agent

Deploy an agent daemon on a GPU server that registers with a central KITT
web server:

```bash
kitt stack generate gpu1 --agent --agent-port 8090 --server-url https://server:8080
kitt stack start --name gpu1
```

### Full Stack with Monitoring

Everything together -- web UI, database, and metrics collection:

```bash
kitt stack generate full --web --postgres --monitoring --port 8080
kitt stack start --name full
```

## Production Considerations

- **TLS**: The web component auto-generates self-signed TLS certificates by
  default. For production, supply your own certificates via `--tls-cert` and
  `--tls-key` on the `kitt web` command, or terminate TLS at a reverse proxy.

- **Secrets**: Generate strong values for `--auth-token`, `--secret-key`, and
  `--postgres-password`. Do not use the defaults in production.

- **Volumes**: The generated `docker-compose.yaml` uses named Docker volumes
  for PostgreSQL data and Grafana dashboards. Back these up regularly.

- **Networking**: All containers run on the host network by default. Adjust
  port flags if you have conflicts with other services.

- **Resource limits**: For GPU-heavy workloads, consider running the agent
  stack on dedicated GPU hosts and the web + database stack on a separate
  management node.
