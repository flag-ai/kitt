# Hardware Fingerprinting

Hardware fingerprinting gives KITT a way to uniquely identify the system it runs on. This identity is used to organize benchmark results so that runs from different machines are never mixed together, and results from the same hardware can be compared over time.

## Purpose

Benchmark results are only meaningful when compared against runs from the same hardware configuration. A throughput measurement on an RTX 4090 cannot be directly compared with one from an A100. Hardware fingerprinting solves this by generating a compact, deterministic string that captures the key hardware characteristics of the system.

This fingerprint is embedded in every result stored by [KARR](karr.md), tagging each run with the exact hardware that produced it.

## Fingerprint Format

The fingerprint is a human-readable string that encodes GPU, CPU, RAM, storage, CUDA, driver, and OS information:

```
{gpu}-{vram}_{cpu}-{cores}_{ram}-{type}_{storage}_{cuda}_{driver}_{os}
```

Example:

```
rtx4090-24gb_i9-13900k-24c_64gb-ddr5_samsung-990pro-nvme_cuda-12.4_550.90_linux-6.8
```

The format is designed to be both machine-parseable and readable at a glance. Each segment is separated by underscores, with dashes used within segments.

## API

### `HardwareFingerprint.generate()`

Returns the compact fingerprint string. This is the primary entry point used by KARR and the CLI to identify hardware.

```bash
kitt fingerprint
# rtx4090-24gb_i9-13900k-24c_64gb-ddr5_samsung-990pro-nvme_cuda-12.4_550.90_linux-6.8

kitt fingerprint --verbose
# Displays full SystemInfo details in a Rich table
```

### `HardwareFingerprint.detect_system()`

Returns a `SystemInfo` dataclass containing all detected hardware attributes in structured form. This is used internally by `generate()` and is also available for code that needs individual fields.

## Detection Methods

KITT detects hardware through a combination of Python libraries and CLI fallbacks:

| Component | Primary Method | Fallback |
|-----------|---------------|----------|
| GPU       | pynvml (nvidia-ml-py) | `nvidia-smi` CLI output parsing |
| CPU       | py-cpuinfo    | `/proc/cpuinfo` on Linux |
| RAM       | psutil        | None |
| Storage   | Device type detection | Assumes SSD if unknown |
| CUDA      | pynvml        | `nvidia-smi` CLI |
| Driver    | pynvml        | `nvidia-smi` CLI |

The dual-path approach for GPU detection ensures fingerprinting works even when pynvml is not installed, as long as the NVIDIA driver and `nvidia-smi` are available on the system.

## Environment Types

KITT detects the runtime environment and includes it in the system information. This helps distinguish between otherwise identical hardware that may behave differently depending on virtualization or containerization.

| Environment      | Detection Criteria |
|------------------|--------------------|
| `dgx_spark`      | NVIDIA DGX Spark system |
| `dgx`            | NVIDIA DGX system |
| `wsl2`           | Windows Subsystem for Linux 2 (kernel string contains `microsoft` or `WSL`) |
| `docker`         | Running inside Docker (`.dockerenv` exists or `docker` in cgroup) |
| `container`      | Running in a non-Docker container (generic container detection) |
| `native_linux`   | Bare-metal or VM Linux |
| `native_macos`   | macOS system |
| `native_windows` | Native Windows (not WSL) |

Environment type detection is ordered from most specific to least specific. DGX systems are checked first, then containerized environments, and finally native OS detection.

## Usage in KARR

In KARR's current database backend, the full fingerprint is stored in the `hardware.fingerprint` column for every run, enabling queries like "show all results from this machine." The fingerprint is also included in flat-file JSON output.

In KARR's legacy Git-backed storage (Gen 2), the fingerprint was truncated to 40 characters for directory naming:

```
karr-rtx4090-24gb_i9-13900k-24c_64gb-ddr/
  └── meta-llama--Llama-3.1-8B/
      └── vllm/
          └── 20250115-143022/
              ├── metrics.json
              └── ...
```

## Next Steps

- [KARR — Results Storage](karr.md) -- how fingerprints are used in result storage
- [Architecture](architecture.md) -- overall system design
