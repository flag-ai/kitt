# Engine Lifecycle

Every inference engine in KITT follows the same container lifecycle: pull the image, create and start the container, wait for health checks, execute benchmarks, and clean up. This page describes each stage in detail.

## Lifecycle Stages

### 1. Image Pull / Check

Before starting an engine, KITT checks whether the required Docker image is available locally. If not, it pulls the image from the configured registry.

```bash
# Manual image setup
kitt engines setup vllm
kitt engines setup vllm --dry-run  # show what would be pulled
```

The `kitt engines check` command verifies that an engine's image is available without starting a container.

### 2. Container Creation

KITT creates a Docker container with the following standard flags:

| Flag | Purpose |
|------|---------|
| `--network host` | Bind engine server directly to localhost (no port mapping overhead) |
| `--gpus all` | Expose all host GPUs to the container |
| `--name kitt-{timestamp}` | Unique container name to avoid conflicts with concurrent runs |
| `-v /path/to/models:/models` | Mount the model directory into the container |

The `DockerManager` constructs and executes the `docker run` command via `subprocess`. Each engine implementation adds its own engine-specific flags (API ports, model paths, quantization settings, etc.).

### 3. Health Check

After the container starts, KITT waits for the engine's health endpoint to respond successfully. This uses exponential backoff to avoid hammering a server that is still loading a model.

**Health check parameters:**

| Parameter | Value |
|-----------|-------|
| Timeout | 300 seconds |
| Initial interval | 1 second |
| Maximum interval | 10 seconds |
| Backoff strategy | Exponential (interval doubles each attempt, capped at max) |

The health check makes HTTP GET requests to the engine's health endpoint. A `200 OK` response indicates the engine is ready to accept generation requests. If the timeout expires before a successful response, KITT stops the container and raises an error.

### 4. Health Endpoints by Engine

Each engine exposes a different health endpoint:

| Engine    | Health Endpoint | Default Port | Success Indicator |
|-----------|----------------|--------------|-------------------|
| vLLM      | `/health`      | 8000         | 200 OK |
| Ollama    | `/api/tags`    | 11434        | 200 OK with model list |
| llama.cpp | `/health`      | 8081         | 200 OK |
| ExLlamaV2 | `/health`      | 8000         | 200 OK |

### 5. Benchmark Execution

Once the health check passes, KITT sends benchmark requests to the engine via its HTTP API on `localhost:PORT`. The engine's `generate()` method handles request formatting, sending, and response parsing for each engine's specific API.

During execution, KITT tracks GPU memory usage through the `GPUMemoryTracker` context manager (see below).

### 6. GPU Memory Tracking

The `GPUMemoryTracker` in `collectors/` is a context manager that monitors GPU memory utilization during benchmark execution:

```python
with GPUMemoryTracker() as tracker:
    results = engine.generate(prompt)
# tracker.peak_memory_mb, tracker.samples, etc.
```

It periodically samples GPU memory via pynvml and records:

- Peak memory usage (MB)
- Average memory usage (MB)
- Memory samples over time
- VRAM utilization percentage

This data is included in the benchmark results and persisted through KARR.

### 7. Container Stop and Removal

After all benchmarks complete (or if an error occurs), KITT stops and removes the engine container. The `cleanup()` method on each engine calls `DockerManager` to:

1. Stop the container (`docker stop`)
2. Remove the container (`docker rm`)

This ensures no orphaned containers are left running. If KITT is interrupted (e.g., Ctrl+C), a signal handler attempts cleanup before exiting.

## Network and Port Binding

All engines use `--network host`, which means the engine server binds directly to the host's network interfaces. This has several implications:

- **No port mapping** -- The engine listens on `localhost:PORT` directly, not through Docker's port forwarding.
- **Lower latency** -- Eliminates the overhead of Docker's userland proxy.
- **Port conflicts** -- Only one engine can use a given port at a time. KITT handles this by running engines sequentially within a suite.

When KITT itself runs in a Docker container (the sibling container pattern), `--network host` ensures both the KITT container and engine containers share the host network namespace, so `localhost` communication works as expected.

## Sequence Diagram

```
KITT CLI          DockerManager         Engine Container
   |                   |                      |
   |  docker pull      |                      |
   |------------------>|                      |
   |                   |  docker run          |
   |                   |--------------------->|
   |                   |                      | (loading model)
   |  GET /health      |                      |
   |----------------------------------------->|
   |  503              |                      |
   |<-----------------------------------------|
   |  (backoff)        |                      |
   |  GET /health      |                      |
   |----------------------------------------->|
   |  200 OK           |                      |
   |<-----------------------------------------|
   |  POST /generate   |                      |
   |----------------------------------------->|
   |  200 + response   |                      |
   |<-----------------------------------------|
   |                   |  docker stop/rm      |
   |                   |--------------------->|
   |                   |                      X
```

## Next Steps

- [Architecture](architecture.md) -- the engine plugin system and Docker management overview
- [Benchmark System](benchmark-system.md) -- what runs during stage 5
