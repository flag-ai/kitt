# KITT Documentation

**End-to-end testing suite for LLM inference engines.**

KITT (Kirizan's Inference Testing Tools) measures quality consistency and
performance across LLM inference engines -- vLLM, llama.cpp, Ollama, and more --
so you can make informed deployment decisions backed by reproducible data.

Every engine runs in a Docker container. You supply a model path, pick an engine,
and KITT handles the rest: container lifecycle, benchmark execution, metric
collection, and result storage.

---

## Feature Highlights

**Multi-Engine Support**
:   Test across vLLM, llama.cpp, Ollama, ExLlamaV2, and MLX with a single command. Compare
    results side by side across engines.

**Docker and Native Engines**
:   Engines run in Docker containers or as native host processes. KITT manages
    the full lifecycle automatically. On DGX Spark, native mode is the default
    for Ollama and llama.cpp.

**Quality Benchmarks**
:   Evaluate model accuracy with MMLU, GSM8K, TruthfulQA, and HellaSwag.
    Checkpoint recovery keeps long runs safe.

**Performance Benchmarks**
:   Measure throughput, latency, memory usage, and warmup characteristics under
    controlled conditions.

**Hardware Fingerprinting**
:   Automatic GPU, CPU, RAM, storage, and CUDA detection. Results are tagged with
    a compact fingerprint for reproducibility.

**KARR Results Storage**
:   All benchmark results persisted through KARR (Kitt's AI Results
    Repository). Database-backed by default (SQLite or PostgreSQL) with full
    query, aggregation, and export support.

**Multiple Output Formats**
:   Export results as JSON, Markdown summaries, or comparison tables. JSON output
    integrates directly with CI pipelines.

**Custom YAML Benchmarks**
:   Define your own test cases in YAML. Mix custom benchmarks with built-in ones
    in any suite configuration.

**Docker Deployment Stacks**
:   Generate composable `docker-compose.yaml` files with optional web dashboard,
    monitoring, PostgreSQL, and agent components.

**Web Dashboard + REST API**
:   Flask-powered UI for browsing results and a REST API for programmatic access
    to benchmark data.

**Monitoring**
:   Prometheus metrics collection with pre-built Grafana dashboards for real-time
    engine and system observability.

**CI Integration**
:   JSON output and meaningful exit codes make KITT easy to integrate into
    automated testing pipelines.

---

## Quick Links

### [Getting Started](getting-started/index.md)

Install KITT, run your first benchmark, and explore Docker deployment workflows.

- [Installation](getting-started/installation.md) -- Docker and source install
- [Tutorial: First Benchmark](getting-started/first-benchmark.md) -- end-to-end walkthrough
- [Tutorial: Docker Quickstart](getting-started/docker-quickstart.md) -- container-based usage

### [Guides](guides/index.md)

In-depth guides for engines, benchmarks, results management, deployment, and more.

### [Reference](reference/index.md)

CLI reference, configuration schema, REST API, Docker files, and environment
variables.

### [Concepts](concepts/index.md)

Architecture overview, hardware fingerprinting, KARR results storage, engine
lifecycle, and the benchmark system.

---

## How It Works

```
 You                    KITT                     Docker
 ───                    ────                     ──────
  │  kitt run             │                        │
  │ ─────────────────────>│  docker run engine     │
  │                       │ ──────────────────────>│
  │                       │  health-check loop     │
  │                       │ <─────────────────────>│
  │                       │  run benchmarks        │
  │                       │ ──────────────────────>│
  │                       │  collect metrics       │
  │                       │ <──────────────────────│
  │  results + summary    │  docker stop           │
  │ <─────────────────────│ ──────────────────────>│
```

KITT is purpose-built for **generative LLMs** (Llama, Qwen, Mistral, and
similar). Encoder-only models such as BERT are not supported because they cannot
produce text through the inference engine APIs.
