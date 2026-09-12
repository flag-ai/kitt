# DGX Spark

KITT includes specific detection and handling for NVIDIA DGX Spark systems.
This guide covers what KITT does differently on DGX hardware and any special
considerations for running benchmarks on these machines.

---

## Environment Detection

KITT automatically identifies DGX Spark systems during hardware fingerprinting.
The detection checks:

1. `/etc/dgx-release` -- if present and contains "spark", the environment is
   classified as `dgx_spark`.
2. `/etc/nvidia/nvidia-dgs.conf` -- presence of this file also triggers
   `dgx_spark` classification.
3. If `/etc/dgx-release` exists but does not contain "spark", the environment
   is classified as `dgx` (standard DGX).

You can verify the detected environment with:

```bash
kitt fingerprint --verbose
```

The output includes the environment type (`dgx_spark`, `dgx`, `native_linux`,
etc.) alongside GPU, CPU, RAM, and storage details.

---

## GPU Detection on DGX Spark (GH200)

The DGX Spark uses the NVIDIA GH200 Grace Hopper Superchip, which has a unified
memory architecture. This means standard VRAM queries may not return a
meaningful value:

- **pynvml**: `nvmlDeviceGetMemoryInfo` may fail or return zero on unified
  memory systems. KITT catches this and logs a debug message rather than
  crashing.
- **nvidia-smi**: The memory column may report `[N/A]`. KITT handles this
  gracefully and sets VRAM to 0 GB in the fingerprint.

Despite the memory query limitations, GPU model name and compute capability
detection work normally.

---

## Docker on DGX

DGX systems ship with Docker and the NVIDIA Container Toolkit pre-installed.
KITT uses `--network host` for all engine containers, which works out of the box
on DGX. No additional Docker configuration is required.

If you are running KITT inside a container on DGX, make sure the container has
access to the GPU:

```bash
docker run --gpus all --network host ...
```

---

## Tested Environments

KITT is tested on the following DGX platforms:

| Platform | Environment Type |
|----------|-----------------|
| DGX Spark (GH200) | `dgx_spark` |
| DGX Station / DGX A100 / DGX H100 | `dgx` |

Both environment types receive enhanced diagnostic messages when GPU detection
fails. If KITT cannot find a GPU on a system classified as `dgx_spark` or `dgx`,
it logs a warning with specific guidance to check that NVIDIA drivers are loaded
and accessible.

---

## Build and Deployment Notes

On DGX Spark, the GH200 has ARM (Grace) CPU cores. Make sure any Docker images
you use are built for `linux/arm64`. The standard KITT engine images (vLLM,
llama.cpp, Ollama) publish multi-architecture images that include ARM support.
On the DGX Spark, native mode is the default for Ollama and llama.cpp,
avoiding Docker overhead entirely.

When generating deployment stacks with `kitt stack generate`, the generated
`docker-compose.yaml` does not pin a platform architecture, so Docker will
automatically pull the correct image for the host.
