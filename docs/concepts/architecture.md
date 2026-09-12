# Architecture

KITT is built around a plugin architecture for inference engines and benchmarks, with Docker containers as the execution environment for all engines. This page describes the major components and how they fit together.

## High-Level Overview

```
Host (KITT CLI)                         Docker Container
+-------------------+                  +------------------+
| kitt run           |   HTTP/JSON      | Engine Server    |
|   engine.generate()| <==============> |   API endpoint   |
|   GPUMemoryTracker |  localhost:PORT  |   /health        |
+-------------------+                  |   --gpus all     |
                                       |   /models (mount)|
                                       +------------------+
```

KITT runs on the host (or in its own container) and manages inference engine containers via the Docker CLI. All communication between KITT and engine containers happens over HTTP on localhost, using each engine's native API.

## Engine Plugin System

The engine system is built on three components:

### InferenceEngine ABC

The abstract base class in `engines/base.py` defines the contract every engine must fulfill:

- **`initialize()`** -- Pull the Docker image, create and start the container, wait for the health check to pass.
- **`generate(prompt, **kwargs)`** -- Send a generation request to the running engine via its HTTP API and return the result.
- **`cleanup()`** -- Stop and remove the Docker container.

### EngineRegistry

The registry in `engines/registry.py` maintains a mapping of engine names to their implementation classes. Engines register themselves using the `@register_engine` decorator:

```python
@register_engine("vllm")
class VLLMEngine(InferenceEngine):
    ...
```

### Auto-Discovery

`EngineRegistry.auto_discover()` imports all built-in engine modules from the `engines/` package. This is called at startup so that all engines are available without manual imports.

### Built-in Engines

| Engine    | Docker Image                                            | API Style             | Default Port |
|-----------|---------------------------------------------------------|-----------------------|--------------|
| vLLM      | `vllm/vllm-openai:latest`                              | OpenAI `/v1/completions` | 8000         |
| llama.cpp | `ghcr.io/ggerganov/llama.cpp:server`                    | OpenAI `/v1/completions` | 8081         |
| Ollama    | `ollama/ollama:latest`                                  | Ollama `/api/generate` | 11434        |
| ExLlamaV2 | `kitt/exllamav2:latest`                                 | OpenAI `/v1/completions` | 8000         |
| MLX       | _(native only)_                                         | OpenAI `/v1/completions` | 8000         |

## Docker Management

### No Docker SDK

KITT deliberately avoids the Docker Python SDK. Instead, `DockerManager` in `engines/docker_manager.py` provides static methods that call the `docker` CLI via `subprocess`. This keeps the dependency footprint small and avoids version-pinning issues with the SDK.

### Container Naming

Containers are named `kitt-{timestamp}` to allow multiple concurrent runs without conflicts.

### Network Mode

All engine containers use `--network host` so the engine server binds directly to localhost on the host. This avoids Docker's port-mapping overhead and simplifies connectivity.

### GPU Access

Engine containers are started with `--gpus all` to expose all host GPUs to the inference server.

### Sibling Container Pattern

KITT can itself run inside a Docker container. In this mode, the Docker socket (`/var/run/docker.sock`) is mounted into the KITT container, allowing it to create and manage engine containers as siblings rather than nested containers. This avoids Docker-in-Docker complexity.

## Remote Agent Architecture

KITT supports deploying thin agents to remote GPU servers. The agent is a standalone Python package (`kitt-agent`) served directly from the KITT web server, ensuring version compatibility.

```
KITT Server                              GPU Server (Agent)
+--------------------+                  +--------------------+
| Web UI / REST API  |  Register/HB    | kitt-agent daemon   |
|   /api/v1/agent/*  | <=============> |   heartbeat thread  |
|   agent_install.py |  Docker cmds    |   Docker orchestr.  |
|   (serves tarball) | ==============> |   log streaming     |
+--------------------+                  +--------------------+
```

### Agent installation flow

1. User runs `curl -fL <server>/api/v1/agent/install.sh | bash`
2. The script creates a venv, downloads the agent sdist from `/api/v1/agent/package`, and installs it
3. `kitt-agent init` writes `~/.kitt/agent.yaml` with server URL, token, name, and port
4. `kitt-agent start` registers with the server, starts the heartbeat thread, and listens for commands

### Agent command protocol

The server sends JSON commands to the agent's `/api/commands` endpoint:

| Command | Payload | Action |
|---------|---------|--------|
| `run_container` | image, port, volumes, env, health_url | Pull image, start container, stream logs |
| `run_test` | model_path, engine_name, suite_name, benchmark_name | Resolve model, run `kitt run`, stream logs |
| `stop_container` | command_id | Stop a running container |
| `check_docker` | _(none)_ | Verify Docker is available |
| `cleanup_storage` | model_path (optional) | Delete specific or all cached models |

The agent reports results back to the server at `/api/v1/agents/{id}/results`.

### Model storage workflow

When executing `run_test`, the agent uses `ModelStorageManager` to resolve the model:

1. Check if already in local `model_storage_dir`
2. Mount NFS share if configured (`model_share_source` → `model_share_mount`)
3. Copy model from share to local storage
4. Run benchmark with local path
5. Clean up local copy if `auto_cleanup` is enabled

### Standalone agent package

The agent package lives in `agent-package/` at the repository root:

```
agent-package/
├── pyproject.toml          # Standalone package (kitt-agent)
└── src/kitt_agent/
    ├── cli.py              # Click CLI: init, start, status, update, stop, test, service, preflight
    ├── config.py           # Pydantic config models
    ├── daemon.py           # Flask mini-app receiving commands
    ├── docker_ops.py       # Docker container management
    ├── hardware.py         # Hardware detection with unified memory support
    ├── heartbeat.py        # Heartbeat thread with settings sync
    ├── log_streamer.py     # SSE log streaming
    ├── model_storage.py    # NFS mount, local copy, cleanup
    ├── preflight.py        # Prerequisite checks (Docker, GPU, disk, etc.)
    └── registration.py     # Server registration
```

## Project Structure

```
src/kitt/
├── cli/           # Click commands (run, engines, test, results, compare, web, fingerprint, stack, agent, monitoring)
├── engines/       # Inference engine plugins (base ABC, registry, vllm, llama_cpp, ollama, exllamav2, mlx)
├── benchmarks/    # Benchmark plugins (base ABC, registry, performance/*, quality/*)
├── config/        # Pydantic models + YAML loader
├── hardware/      # System fingerprinting (GPU, CPU, RAM, storage, CUDA)
├── runners/       # Suite/single test runners + checkpoint recovery
├── collectors/    # GPU memory tracking, system metrics
├── reporters/     # JSON, Markdown, comparison output
├── git_ops/       # KARR legacy Git-backed storage
├── monitoring/    # Monitoring stack config, generator, deployer
├── stack/         # Composable Docker stack config + generator
├── security/      # TLS cert generation and config
├── web/           # Flask dashboard + REST API + blueprints + Devon iframe
└── utils/         # Compression, validation, versioning

agent-package/     # Standalone thin agent (installed on GPU servers)
└── src/kitt_agent/ # Self-contained agent daemon
```

### Key Design Decisions

- **Dataclasses** are used for result types and internal data structures.
- **Pydantic v2** is used for configuration validation (YAML configs are loaded and validated through Pydantic models).
- **Click** is the CLI framework; Rich provides tables, panels, and spinners for terminal output.
- **Logging** uses `logging.getLogger(__name__)` throughout all modules.
- **Full type hints** are required on all public methods.

## Web Dashboard

The web UI is a Flask application (`web/app.py`) using TailwindCSS, HTMX, and Alpine.js. It registers page blueprints (Dashboard, Agents, Devon, Models, Campaigns, Quick Test, Results, Settings) and API v1 blueprints under `/api/v1/`.

### Devon Tab

When `DEVON_URL` is set, the Devon tab embeds the Devon web UI in an iframe for integrated model management. A `/api/v1/devon/status` endpoint checks connectivity. The tab's visibility is controlled via the Settings page and persisted in the `web_settings` SQLite table.

### Settings Persistence

UI preferences (such as Devon tab visibility) are stored in a `web_settings` key-value table managed by `SettingsService`. Settings are injected into all templates via a Flask context processor.

## Relationship to DEVON

KITT tests models; DEVON manages and stores them. The two projects share the same technical stack (Poetry, Click, Rich, Python 3.10+, plugin registry pattern). The KITT web dashboard embeds Devon's UI directly when `DEVON_URL` is configured. DEVON can also export model paths in a format KITT consumes:

```bash
devon export --format kitt -o models.txt
```

## Next Steps

- [Engine Lifecycle](engine-lifecycle.md) -- detailed container lifecycle and health checks
- [Benchmark System](benchmark-system.md) -- how benchmarks are defined and executed
- [Hardware Fingerprinting](hardware-fingerprinting.md) -- system identification for result organization
