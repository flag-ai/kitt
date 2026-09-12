# Benchmarks

KITT ships with quality and performance benchmarks organized into test suites.
You can also define custom benchmarks in YAML.

## Test Suites

| Suite | Description | Benchmarks | Default Runs |
|---|---|---|---|
| `quick` | Smoke test | Throughput only | 1 |
| `standard` | Full evaluation | All quality + performance | 3 |
| `performance` | Performance-focused | Throughput, latency, memory, warmup | 3 |

## Built-in Benchmarks

### Quality

| Benchmark | Description |
|---|---|
| MMLU | Massive Multitask Language Understanding -- broad knowledge evaluation |
| GSM8K | Grade school math reasoning |
| TruthfulQA | Factual consistency evaluation |
| HellaSwag | Commonsense reasoning |

Quality benchmarks require the `datasets` extra (`poetry install -E datasets`).

### Performance

| Benchmark | Description |
|---|---|
| Throughput | Requests per second at various concurrency levels |
| Latency | Time-to-first-token and end-to-end response time |
| Memory | Peak VRAM and CPU memory usage during inference |
| Warmup Analysis | Measures performance stabilization over initial requests |

## Running Benchmarks

Use `kitt run` to execute a test suite against a model and engine:

```bash
kitt run -m MODEL -e ENGINE -s SUITE -o OUTPUT
```

| Option | Short | Description |
|---|---|---|
| `--model` | `-m` | Path to model or model identifier (required) |
| `--engine` | `-e` | Inference engine key (required) |
| `--suite` | `-s` | Test suite: `quick`, `standard`, `performance` (default: `quick`) |
| `--output` | `-o` | Output directory for results |
| `--runs` | | Override the number of runs per benchmark |
| `--skip-warmup` | | Skip the warmup phase |
| `--config` | | Path to custom engine configuration YAML |
| `--store-karr` | | Also store results in KARR's legacy Git-backed backend |

Examples:

```bash
# Quick throughput test with Ollama
kitt run -m llama3 -e ollama

# Full standard suite with vLLM
kitt run -m /models/llama2-7b -e vllm -s standard -o ./my-results

# Performance suite with legacy Git-backed KARR storage
kitt run -m /models/mistral-7b -e llama_cpp -s performance --store-karr

# Override run count
kitt run -m /models/qwen-7b -e ollama -s standard --runs 5
```

## Output Artifacts

Each run produces the following files in the output directory:

| File | Description |
|---|---|
| `metrics.json` | Full benchmark metrics in JSON format |
| `hardware.json` | Detected hardware information |
| `config.json` | Configuration used for the run |
| `summary.md` | Human-readable Markdown summary |
| `outputs/` | Compressed benchmark outputs (chunked) |

## Custom Benchmarks

### Creating a New Benchmark

Generate a YAML template with `kitt test new`:

```bash
kitt test new my-eval
kitt test new my-eval --category performance
```

This creates a file at `configs/tests/quality/custom/my-eval.yaml` (or in the
`performance` directory if you set `--category performance`).

### YAML Benchmark Template

```yaml
name: my-eval
category: quality_custom
description: "My custom evaluation"
dataset:
  source: local
  path: ./data/my-eval.jsonl
prompts:
  template: "{question}"
  answer_key: "answer"
sampling:
  max_tokens: 256
  temperature: 0.0
scoring:
  method: exact_match
runs: 3
```

Edit the template to point at your dataset, adjust the prompt template, and
configure scoring. KITT picks up custom YAML benchmarks automatically when they
are placed in `configs/tests/`.

## Listing Benchmarks

List all available benchmarks (built-in and custom):

```bash
kitt test list
```

Filter by category:

```bash
kitt test list -c performance
kitt test list -c quality
```

## Checkpoint Recovery

Long-running benchmarks save checkpoints every 100 items. If a run is
interrupted, restarting with the same output directory resumes from the last
checkpoint rather than starting over.
