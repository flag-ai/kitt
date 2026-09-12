# Tutorial: Docker Quickstart

This tutorial covers running KITT entirely from Docker -- no Python environment
on the host required. It progresses from single commands through Docker Compose
to full production stacks.

!!! note "Prerequisites"
    Docker and the NVIDIA Container Toolkit must be installed. See the
    [Installation](installation.md) guide for details.

---

## Build the KITT Image

```bash
docker build -t kitt .
```

The Dockerfile installs KITT with all optional extras so every feature is
available inside the container.

---

## Run a Benchmark from the Container

KITT needs three mounts to work from inside a container:

```bash
docker run --rm --network host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /path/to/models:/models:ro \
  -v ./kitt-results:/app/kitt-results \
  kitt run -m /models/llama-7b -e vllm -s quick
```

| Mount | Purpose |
|---|---|
| `/var/run/docker.sock` | KITT manages engine containers via the Docker socket |
| `/path/to/models` (read-only) | Model weights shared between KITT and the engine |
| `./kitt-results` | Results written back to the host |

!!! warning
    The Docker socket mount gives the KITT container full Docker access on the
    host. Use this only in trusted environments.

You can run any KITT command this way -- not just `kitt run`:

```bash
docker run --rm kitt fingerprint --verbose
docker run --rm kitt test list
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock kitt engines list
```

---

## Docker Compose

The repository includes a `docker-compose.yaml` for convenience. Set the
`MODEL_PATH` environment variable and use `docker compose run`:

```bash
MODEL_PATH=/path/to/models docker compose run kitt run -m /models/llama-7b -e vllm
```

To run the standard suite across multiple engines:

```bash
MODEL_PATH=/path/to/models docker compose run kitt run -m /models/llama-7b -e vllm -s standard
MODEL_PATH=/path/to/models docker compose run kitt run -m /models/llama-7b -e llama_cpp -s standard
```

!!! tip
    Export `MODEL_PATH` in your shell profile so you don't have to set it on
    every invocation: `export MODEL_PATH=/path/to/models`.

---

## Production Stacks with `kitt stack`

For production deployments, KITT generates composable Docker Compose stacks that
bundle the web dashboard, database, monitoring, and agent components.

### Generate a Stack

```bash
kitt stack generate prod --web --postgres --monitoring
```

This creates a `docker-compose.yaml` under `~/.kitt/stacks/prod/` with:

- **Web dashboard** -- Flask UI and REST API
- **PostgreSQL** -- persistent result storage
- **Prometheus + Grafana** -- metrics collection and dashboards

Add `--agent` to include the distributed agent daemon for remote execution:

```bash
kitt stack generate prod --web --postgres --monitoring --agent
```

### Manage Stack Lifecycle

Start, check, and stop stacks by name:

```bash
kitt stack start --name prod
kitt stack status --name prod
kitt stack stop --name prod
```

### List and Remove Stacks

```bash
kitt stack list
kitt stack remove prod --delete-files
```

!!! note
    The `--web` and `--reporting` flags are mutually exclusive. Use `--web` for
    the full dashboard or `--reporting` for headless report generation.

---

## Example: Full Production Deployment

A complete workflow from image build to running benchmarks through a production
stack:

```bash
# Build the KITT image
docker build -t kitt .

# Generate and start a stack with all components
kitt stack generate prod --web --postgres --monitoring --agent
kitt stack start --name prod

# Run benchmarks (results flow to PostgreSQL and Grafana automatically)
docker run --rm --network host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /path/to/models:/models:ro \
  kitt run -m /models/llama-7b -e vllm -s standard

# Check the web dashboard at http://localhost:5000
# Check Grafana dashboards at http://localhost:3000

# When finished
kitt stack stop --name prod
```

---

## Next Steps

- Learn about engine configuration: [Engines Guide](../guides/engines.md)
- Set up monitoring dashboards: [Monitoring Guide](../guides/monitoring.md)
- Explore the REST API: [API Reference](../reference/api.md)
