# Tutorial: First Benchmark

This tutorial walks through a complete benchmark run -- from checking your
hardware to storing results in KARR.

!!! note "Prerequisites"
    KITT must be installed and your GPU must be accessible to Docker. See the
    [Installation](installation.md) guide if you haven't set that up yet.

---

## 1. Check Your Hardware Fingerprint

KITT identifies each machine by a compact fingerprint string. Run:

```bash
kitt fingerprint
```

Example output:

```
rtx4090-24gb_i9-13900k-24c_64gb-ddr5_samsung-990pro-nvme_cuda-12.4_550.90_linux-6.8
```

Use `--verbose` for a full breakdown of every detected component:

```bash
kitt fingerprint --verbose
```

!!! tip
    The fingerprint is embedded in every result set so you can always trace which
    hardware produced a given benchmark.

---

## 2. Pull the Engine Image

Before running benchmarks, make sure the engine's Docker image is available
locally. KITT can pull it for you:

```bash
kitt engines setup vllm
```

This downloads the default vLLM image (`vllm/vllm-openai:latest`). The first
pull may take several minutes depending on your connection.

---

## 3. Verify Engine Readiness

List all registered engines and their status:

```bash
kitt engines list
```

You should see vLLM listed with its image marked as available. If the image
column shows "missing", re-run `kitt engines setup vllm`.

---

## 4. List Available Benchmarks

See what benchmarks KITT ships with:

```bash
kitt test list
```

Output groups benchmarks by category:

| Category | Benchmarks |
|---|---|
| Performance | throughput, latency, memory, warmup_analysis |
| Quality | mmlu, gsm8k, truthfulqa, hellaswag |

!!! note
    Quality benchmarks require the `datasets` extra. Install it with
    `poetry install -E datasets` if you haven't already.

---

## 5. Run a Quick Benchmark

The `quick` suite runs a single throughput benchmark -- ideal for verifying that
everything works before committing to a full evaluation.

```bash
kitt run -m /path/to/model -e vllm -s quick
```

KITT will:

1. Start a vLLM container with your model
2. Wait for the health check to pass
3. Execute the throughput benchmark
4. Tear down the container
5. Write results to `kitt-results/` and store them in KARR

!!! warning
    Make sure the model format matches the engine. vLLM accepts
    safetensors/pytorch; llama.cpp and Ollama require GGUF.

---

## 6. View the Results

Each run produces a timestamped directory under `kitt-results/` containing:

| File | Contents |
|---|---|
| `metrics.json` | Raw benchmark measurements (tokens/sec, latencies, memory) |
| `hardware.json` | System fingerprint captured at run time |
| `config.json` | Exact configuration used for the run |
| `summary.md` | Human-readable Markdown report |

Open the summary for a quick overview:

```bash
cat kitt-results/<model>/<engine>/<timestamp>/summary.md
```

Or view results as a Rich table in the terminal:

```bash
kitt results list --model llama-7b --engine vllm
```

---

## 7. Browse Results in KARR

Results are stored in KARR automatically. Initialize the database if this is
your first run:

```bash
kitt storage init
```

Then browse and query your stored results:

```bash
kitt storage list
kitt storage stats
```

You can also import any flat-file results from previous runs:

```bash
kitt storage import ./kitt-results/
```

!!! tip
    KARR uses SQLite by default (`~/.kitt/kitt.db`) with zero configuration.
    For production or multi-agent setups, see the
    [KARR concepts page](../concepts/karr.md) for PostgreSQL configuration.

---

## Next Steps

- Run the full `standard` suite: `kitt run -m /path/to/model -e vllm -s standard`
- Compare engines: run the same model on multiple engines, then use `kitt compare`
- Try Docker-based workflows: [Docker Quickstart](docker-quickstart.md)
