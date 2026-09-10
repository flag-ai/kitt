# Agent Daemon

The KITT agent daemon runs on GPU servers and receives benchmark jobs from a
central KITT server. This distributed model lets you manage a fleet of GPU
machines from a single control plane -- the server dispatches work and agents
execute it.

---

## How It Works

The agent is a lightweight Flask application that listens for commands over
HTTPS. When the server sends a `run_test` command, the agent resolves the
model to local storage, starts a benchmark in a background thread, and streams
logs back via Server-Sent Events (SSE). A heartbeat thread runs alongside the
daemon, reporting status and GPU utilization to the server at a configurable
interval (default 30 seconds). Settings configured on the server are synced
to the agent via the heartbeat response.

---

## Model Workflow

When a benchmark is dispatched, the agent resolves the model path through the
`ModelStorageManager`:

1. **Check local storage** — if the model is already under the configured
   `model_storage_dir`, use it directly.
2. **Mount NFS share** — if `model_share_mount` is configured, ensure it is
   mounted (via fstab or explicit `sudo mount -t nfs`).
3. **Copy from share** — copy the model from the share to local storage using
   `shutil.copytree`.
4. **Run benchmark** — execute the benchmark in a Docker container (falls back
   to local `kitt run` if the image is not available).
5. **Cleanup** — if `auto_cleanup` is enabled, delete the local copy after the
   benchmark completes.

This ensures benchmarks always run against a local copy, avoiding NFS latency
during inference.

### NFS share configuration

Set the share source and mount point via the web UI (**Agents > Detail >
Settings**) or during initialization:

```bash
kitt-agent init --server https://server:8080 \
    --model-dir /data/models \
    --share-source nas:/volume1/models \
    --share-mount /mnt/models
```

For passwordless mounts, add an entry to `/etc/fstab`:

```
nas:/volume1/models  /mnt/models  nfs  defaults,nofail  0  0
```

---

## Initializing the Agent

Before starting the agent you must register it with a KITT server:

```bash
kitt-agent init --server https://server:8080
```

This command writes `~/.kitt/agent.yaml` with the server URL, token, agent
name, and optional model storage paths.

| Flag | Default | Description |
|------|---------|-------------|
| `--token` | *(empty)* | Bearer token for server authentication |
| `--name` | hostname | Friendly agent name |
| `--port` | 8090 | Port the agent listens on |
| `--model-dir` | `~/.kitt/models` | Local model storage directory |
| `--share-source` | *(empty)* | NFS share source (e.g., `nas:/volume1/models`) |
| `--share-mount` | *(empty)* | Local mount point for NFS share |

---

## Preflight Checks

Run prerequisite checks before starting:

```bash
kitt-agent preflight --server https://server:8080 --port 8090
```

Checks performed:

| Check | Required | How |
|-------|----------|-----|
| Python >= 3.10 | Yes | `sys.version_info` |
| Docker available | Yes | `docker info` subprocess |
| Docker GPU access | Yes | `docker run --gpus all nvidia/cuda:...` |
| KITT Docker image | No | `docker image inspect kitt:latest` |
| NVIDIA drivers | Yes | `nvidia-smi` subprocess |
| NFS utilities | No | Check for `mount.nfs` in PATH |
| Disk space (>= 50GB) | No | `shutil.disk_usage` on model dir |
| Server reachable | Yes | HTTP GET to `/api/v1/health` |
| Port available | No | `socket.bind` on agent port |

Required checks that fail cause exit code 1.

The install script runs preflight automatically. You can also use the
`--preflight` flag on start:

```bash
kitt-agent start --preflight
```

---

## Building the Docker Image

The agent runs benchmarks inside a Docker container built from the KITT
source. Each agent builds the image locally so it is native to the host
architecture (amd64 or arm64). The install script does this automatically,
but you can also build or rebuild manually:

```bash
kitt-agent build
```

The command downloads the build context tarball from the server, verifies
its SHA-256 digest, and runs `docker build` locally. The resulting image is
tagged as `kitt:latest` (and with any custom tag from `kitt_image` in agent
settings).

| Flag | Description |
|------|-------------|
| `--server` | KITT server URL (reads from `agent.yaml` if not set) |
| `--tag` | Override the image tag |
| `--no-cache` | Build without Docker cache |

Rebuild the image after updating the agent to pick up new KITT changes:

```bash
kitt-agent update
kitt-agent build
```

---

## Starting the Agent

```bash
kitt-agent start
```

On startup the agent:

1. Loads `~/.kitt/agent.yaml` (override with `--config`).
2. Detects hardware — GPU (with unified memory fallback for architectures like
   DGX Spark GB10), CPU, RAM, storage, CUDA version, driver version, environment
   type, and compute capability.
3. Initializes `ModelStorageManager` from config.
4. Registers with the server via `POST /api/v1/agents/register`, sending a full
   hardware fingerprint and detailed hardware info.
5. Starts a `HeartbeatThread` that sends periodic status, GPU utilization,
   memory usage, and storage availability to the server.
6. Launches the Flask app on the configured port with optional TLS.

Use `--insecure` to skip TLS verification during development.

---

## Agent Settings

Settings are stored on the server in the `agent_settings` table and synced to
the agent via the heartbeat response. Edit them from the web UI on the agent
detail page or via the REST API.

| Setting | Default | Description |
|---------|---------|-------------|
| `model_storage_dir` | `~/.kitt/models` | Local directory for model copies |
| `model_share_source` | *(empty)* | NFS share source |
| `model_share_mount` | *(empty)* | Local mount point for NFS share |
| `auto_cleanup` | `true` | Delete local model copies after benchmarks |
| `heartbeat_interval_s` | `30` | Seconds between heartbeats (10-300) |
| `kitt_image` | *(empty)* | Docker image tag for benchmark containers |

---

## mTLS Communication

When the server uses HTTPS, agent-server communication is secured with mutual
TLS. During `kitt-agent init` KITT generates a client certificate and stores the
paths in `agent.yaml` under the `tls` key:

```yaml
tls:
  cert: /home/user/.kitt/certs/agent.pem
  key: /home/user/.kitt/certs/agent-key.pem
  ca: /home/user/.kitt/certs/ca.pem
```

Both the heartbeat and the registration request present the client certificate.
The server validates it against the same CA.

---

## Systemd Service

For production deployments, install the agent as a systemd service:

```bash
~/.kitt/agent-venv/bin/kitt-agent service install
```

This generates a systemd unit file, installs it via `sudo`, and starts the
service. The agent will survive reboots and restart automatically on failure.

Manage the service:

```bash
kitt-agent service status      # check service status
kitt-agent service uninstall   # stop, disable, and remove the service
```

---

## Updating the Agent

```bash
kitt-agent update              # download and install latest from server
kitt-agent update --restart    # update and restart in one step
```

The `update` command downloads the latest agent package from the KITT server
(`/api/v1/agent/package`) and reinstalls it into the agent's virtual environment.
Use `--restart` to automatically stop the running agent and start the new version.

After updating, rebuild the Docker image to pick up new KITT changes:

```bash
kitt-agent build
```

If the agent is managed by systemd, restart the service after updating:

```bash
kitt-agent update
kitt-agent build
sudo systemctl restart kitt-agent
```

---

## Heartbeat and Command Dispatch

The `HeartbeatThread` sends a JSON payload to
`/api/v1/agents/<agent_id>/heartbeat` at the configured interval. The payload
includes:

- Agent status (`idle`, `running`, `error`)
- Current task identifier
- GPU utilization percentage (via pynvml)
- GPU memory used in GB
- Storage free space in GB
- Agent uptime

During active benchmarks, the heartbeat interval is automatically increased to
at least 60 seconds to reduce overhead.

The heartbeat response includes:

- `commands` — pending jobs (e.g., quick tests queued from the web UI)
- `settings` — current agent settings for sync

The agent processes each command automatically — for `run_test` commands it
resolves the model, starts the benchmark, and streams log lines back to the
server via `POST /api/v1/quicktest/<test_id>/logs`. Status transitions are
reported via `POST /api/v1/quicktest/<test_id>/status`.

---

## Log Streaming

When a benchmark runs, the agent captures output through a `LogStreamer` and
exposes it as an SSE endpoint at `/api/logs/<command_id>`. The server or any
authorized client can subscribe to this stream for real-time log output.

---

## Checking Status

```bash
kitt-agent status
```

This reads `~/.kitt/agent.yaml` and probes the local agent at
`http://127.0.0.1:<port>/api/status` to report whether the daemon is running
and whether a benchmark is currently active.

---

## Managing Tests

List tests dispatched to this agent:

```bash
kitt-agent test list                    # show all tests for this agent
kitt-agent test list --status running   # filter by status
kitt-agent test list --limit 5          # limit results
```

Stop a running or queued test:

```bash
kitt-agent test stop <test_id>
```

The `stop` command marks the test as failed on the server with an
"Cancelled by user" error and sends a cancel signal to the local daemon
to kill the running process.

---

## Stopping the Agent

```bash
kitt-agent stop
```

Sends `SIGTERM` to the agent process using the PID stored in
`~/.kitt/agent.pid`.

---

## Test Agents

Test agents are virtual agents that simulate benchmark execution without real
GPU hardware. They are useful for end-to-end UI testing — creating campaigns,
running quick tests, viewing live logs, and inspecting results — all without a
real agent daemon or GPU server.

### Creating a test agent

Navigate to **Agents > Create Test Agent** in the web dashboard. Configure
hardware specs (GPU model, count, CPU, architecture, RAM, environment type) to
match the testing scenario. Test agents appear in the agent list with a **TEST**
badge and are always shown as online.

### Simulated execution

When a quick test or campaign is launched on a test agent:

1. The test transitions through the same status lifecycle as a real test
   (queued → running → completed).
2. Log lines stream in real time over SSE with realistic 0.5–1.5s delays.
3. Fake but logically consistent benchmark metrics are generated (throughput,
   latency, memory, accuracy).
4. Results are persisted through the normal `ResultStore` pipeline and appear
   in the Results page.

### Differences from real agents

- Test agents never go offline (the stale heartbeat check skips them).
- Storage and NFS settings are hidden on the agent detail page.
- No authentication token is provisioned (port is set to 0).
- Benchmark metrics are randomly generated within realistic ranges.
