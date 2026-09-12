# Docker Files

KITT uses Docker both for its own container image and for launching
inference engines as sibling containers. This page documents the project
Dockerfile, the monitoring docker-compose stack, and the Docker patterns
KITT relies on.

## Dockerfile

Location: `Dockerfile` (project root)

### Build stages

The Dockerfile uses a single-stage build based on `python:3.12-slim`:

```dockerfile
FROM python:3.12-slim

# System dependencies for psutil/pynvml compilation and Docker CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev docker.io \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Poetry and project dependencies
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-root --without dev

COPY src/ ./src/
COPY configs/ ./configs/
RUN poetry install --only-root

ENTRYPOINT ["poetry", "run", "kitt"]
```

Key points:

- **`docker.io`** is installed inside the container so KITT can call the
  Docker CLI to manage inference engine containers.
- **`gcc` and `python3-dev`** are needed to compile native extensions for
  `psutil` and `pynvml`.
- The entry point runs `poetry run kitt`, so any CLI command can be passed
  as arguments (e.g. `docker run kitt run -m /model -e vllm`).

### Multi-architecture support

The base image `python:3.12-slim` supports both amd64 and arm64, so the
Dockerfile is architecture-agnostic. Agents build the image locally via
`kitt-agent build`, producing a native image for the host architecture.
This avoids cross-architecture issues when the server (amd64) and agents
(e.g. ARM64 NVIDIA Grace Blackwell) differ.

### Additional Dockerfiles

| File | Purpose |
|------|---------|
| `docker/web/Dockerfile` | Web dashboard image (also used by `kitt-agent build`) |
| `docker/llama_cpp/Dockerfile.spark` | llama.cpp build for DGX Spark |

## docker-compose.yaml (Monitoring)

Location: `docker/monitoring/docker-compose.yaml`

This stack provides metrics collection and visualization:

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `prometheus` | `prom/prometheus:latest` | 9090 | Metrics scraping |
| `grafana` | `grafana/grafana:latest` | 3000 | Dashboard visualization |
| `influxdb` | `influxdb:2` | 8086 | Time-series storage for benchmark data |

Named volumes persist data across restarts: `prometheus_data`,
`grafana_data`, `influxdb_data`.

## Docker socket mounting

KITT manages inference engines as **sibling containers** -- it calls the
Docker CLI from inside its own container to start/stop engine containers
on the host. This requires mounting the Docker socket:

```bash
docker run -v /var/run/docker.sock:/var/run/docker.sock kitt run ...
```

Without the socket mount, KITT cannot launch or manage engine containers.

## Network mode

All engine containers use `--network host` so they bind directly to the
host network. This avoids port-mapping complexity and lets KITT reach
engines at `localhost:<port>`:

| Engine | Default Port |
|--------|-------------|
| vLLM | 8000 |
| llama.cpp | 8081 |
| Ollama | 11434 |
| ExLlamaV2 | 8000 |

## GPU passthrough

Engine containers require GPU access. KITT passes `--gpus all` to Docker
when launching engine containers:

```bash
docker run --gpus all --network host vllm/vllm-openai:latest ...
```

Ensure the NVIDIA Container Toolkit is installed on the host system. KITT
detects GPU availability through `pynvml` or by parsing `nvidia-smi`
output.

## Model volume mounting

Models stored on the host are mounted into engine containers. The host
path is typically set via the `MODEL_PATH` environment variable or the
`-m` CLI flag:

```bash
docker run --gpus all --network host \
  -v /models/llama-8b:/models/llama-8b \
  vllm/vllm-openai:latest --model /models/llama-8b
```
