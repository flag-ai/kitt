# Suite Configuration

Suite configuration files define which benchmarks to run together and how
to configure them. Files live in `configs/suites/` and are validated against
the `SuiteConfig` Pydantic model.

## Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `suite_name` | `str` | Yes | Unique identifier for the suite |
| `version` | `str` | No | Semantic version (default: `"1.0.0"`) |
| `description` | `str` | No | Human-readable description |
| `tests` | `list[str]` | Yes | Benchmark names to include |
| `global_config` | `dict` | No | Settings applied to every test (e.g. `runs`) |
| `sampling_overrides` | `SamplingParams` | No | Override sampling defaults for all tests |
| `test_overrides` | `dict[str, SuiteOverrides]` | No | Per-test overrides keyed by test name |

### SuiteOverrides

| Field | Type | Description |
|-------|------|-------------|
| `warmup` | `WarmupConfig` | Override warmup settings for this test |
| `sampling` | `SamplingParams` | Override sampling parameters for this test |
| `runs` | `int` | Override the number of runs for this test |

### SamplingParams

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `temperature` | `float` | `0.0` | Sampling temperature (0.0--2.0) |
| `top_p` | `float` | `1.0` | Nucleus sampling threshold (0.0--1.0) |
| `top_k` | `int` | `50` | Top-k sampling |
| `max_tokens` | `int` | `2048` | Maximum tokens to generate |

## Built-in suites

### quick

Smoke test that runs only the throughput benchmark with a single run.

```yaml
suite_name: quick
version: "1.0.0"
description: "Quick smoke test - runs throughput benchmark only"

tests:
  - throughput

global_config:
  runs: 1

sampling_overrides:
  temperature: 0.0
  max_tokens: 128
```

### standard

Full evaluation across all quality and performance benchmarks with three
runs per test.

```yaml
suite_name: standard_benchmarks
version: "1.1.0"
description: "Standard academic benchmarks for LLM evaluation (V1)"

tests:
  - mmlu
  - gsm8k
  - truthfulqa
  - hellaswag
  - throughput
  - latency
  - memory_usage
  - warmup_analysis

global_config:
  runs: 3

sampling_overrides:
  temperature: 0.0
  max_tokens: 2048

test_overrides:
  mmlu:
    runs: 1
  warmup_analysis:
    warmup:
      enabled: false
```

### performance

Performance-focused suite that skips quality benchmarks entirely.

```yaml
suite_name: performance
version: "1.0.0"
description: "Performance-focused benchmark suite"

tests:
  - throughput
  - latency
  - memory_usage
  - warmup_analysis

global_config:
  runs: 3

sampling_overrides:
  temperature: 0.0
  max_tokens: 2048

test_overrides:
  warmup_analysis:
    warmup:
      enabled: false
```

## Creating a custom suite

1. Create a new YAML file in `configs/suites/`:

    ```yaml
    suite_name: my_suite
    description: "Custom suite for latency testing"

    tests:
      - latency
      - throughput

    global_config:
      runs: 5

    sampling_overrides:
      temperature: 0.0
      max_tokens: 512
    ```

2. Run it with:

    ```bash
    kitt run -m /path/to/model -e vllm -s my_suite
    ```
