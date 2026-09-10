# Installation

KITT can run from a pre-built Docker image or be installed from source with
Poetry. The Docker method is the fastest way to get started; the source install
gives you direct access to the CLI and development tools.

---

## Docker (Primary Method)

Build the image and run benchmarks in a single command. No Python environment
required on the host.

```bash
docker build -t kitt .
```

```bash
docker run --rm --network host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /path/to/models:/models:ro \
  -v ./kitt-results:/app/kitt-results \
  kitt run -m /models/llama-7b -e vllm
```

| Mount | Purpose |
|---|---|
| `/var/run/docker.sock` | Lets KITT manage engine containers from inside its own container |
| `/path/to/models` (read-only) | Model weights accessible to both KITT and the engine |
| `./kitt-results` | Benchmark output written back to the host |

!!! warning
    Mounting the Docker socket grants the container full control over Docker on
    the host. Only use images you trust.

---

## Source Install

### Prerequisites

- **Python 3.10+** and **Poetry**
- **Docker** for running inference engines
- **System build tools** for native dependencies:

=== "Ubuntu / Debian"

    ```bash
    sudo apt-get install gcc python3-dev
    ```

=== "Arch Linux"

    ```bash
    sudo pacman -S --needed base-devel
    ```

=== "macOS"

    ```bash
    xcode-select --install
    ```

- **NVIDIA Container Toolkit** for GPU support (required by all engines except
  CPU-only llama.cpp builds):

    ```bash
    # Follow the official NVIDIA guide for your distro:
    # https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
    nvidia-ctk --version   # verify installation
    ```

### Install

Clone the repository and install with Poetry:

```bash
git clone https://github.com/kirizan/kitt.git
cd kitt
poetry install
```

Activate the virtual environment:

```bash
eval $(poetry env activate)
```

Verify the installation:

```bash
kitt --version
kitt fingerprint
```

### Optional Extras

KITT ships with optional dependency groups for features that not every user
needs. Install them individually or pull in everything at once.

```bash
# Individual extras
poetry install -E datasets
poetry install -E web
poetry install -E cli_ui

# Everything
poetry install -E all
```

| Extra | What It Adds | Required For |
|---|---|---|
| `datasets` | HuggingFace Datasets | Quality benchmarks (MMLU, GSM8K, TruthfulQA, HellaSwag) |
| `web` | Flask | `kitt web` dashboard and REST API |
| `cli_ui` | Textual | `kitt compare` interactive TUI |
| `all` | All of the above | Full feature set |

!!! note
    Performance benchmarks (throughput, latency, memory, warmup) have no extra
    dependencies -- they work with the base install.

---

## Verify GPU Access

After installation, confirm that Docker can see your GPU:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

Then check KITT's hardware detection:

```bash
kitt fingerprint --verbose
```

This prints a full system profile including GPU model, VRAM, CPU, RAM, storage
type, CUDA version, and driver version.

---

## Next Steps

- [Tutorial: First Benchmark](first-benchmark.md) -- run an end-to-end test
- [Tutorial: Docker Quickstart](docker-quickstart.md) -- container-based workflows
