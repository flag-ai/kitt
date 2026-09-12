# Benchmark System

KITT's benchmark system is built on a plugin architecture that supports both built-in and custom benchmarks. Benchmarks are registered via decorators, can be defined in Python or YAML, and support checkpoint recovery for long-running evaluations.

## Benchmark ABC

The `LLMBenchmark` abstract base class in `benchmarks/base.py` defines the interface every benchmark must implement:

- **`run(engine, config)`** -- Public entry point. Handles setup, calls `_execute()`, and collects results. This method manages checkpoint loading and saving.
- **`_execute(engine, config)`** -- The actual benchmark logic. Subclasses override this to implement their specific evaluation.

All benchmarks receive an initialized engine instance and a configuration object, and return structured result data.

## BenchmarkRegistry

The `BenchmarkRegistry` in `benchmarks/registry.py` maintains the mapping from benchmark names to their implementation classes. Registration uses the `@register_benchmark` decorator:

```python
@register_benchmark("throughput")
class ThroughputBenchmark(LLMBenchmark):
    def _execute(self, engine, config):
        ...
```

At startup, all built-in benchmarks are auto-discovered and registered, similar to the [engine plugin system](architecture.md#engine-plugin-system).

## Built-in Benchmarks

### Performance Benchmarks

Performance benchmarks measure inference engine speed and resource usage. They do not evaluate output quality.

| Benchmark | What It Measures |
|-----------|-----------------|
| `throughput` | Tokens per second at various batch sizes and sequence lengths |
| `latency` | Time-to-first-token (TTFT) and inter-token latency (ITL) |
| `memory` | Peak GPU memory usage under different loads |
| `warmup_analysis` | Performance difference between cold-start and warmed-up inference |

### Quality Benchmarks

Quality benchmarks evaluate the correctness and consistency of model outputs. These use standard academic evaluation datasets.

| Benchmark | Dataset | What It Measures |
|-----------|---------|-----------------|
| `mmlu` | MMLU | Multitask language understanding across 57 subjects |
| `gsm8k` | GSM8K | Grade-school math reasoning with chain-of-thought |
| `truthfulqa` | TruthfulQA | Resistance to generating common falsehoods |
| `hellaswag` | HellaSwag | Common-sense sentence completion |

## YAML-Defined Benchmarks

Custom benchmarks can be defined in YAML without writing Python code. The `YAMLBenchmark` class in `benchmarks/loader.py` loads YAML files and creates benchmark instances at runtime.

```yaml
name: custom_throughput
category: performance
base: throughput
config:
  batch_sizes: [1, 4, 8]
  sequence_lengths: [128, 512]
  num_iterations: 5
```

YAML benchmarks reference a `base` benchmark and override specific configuration values. This makes it easy to create variants of built-in benchmarks tuned for specific hardware or use cases.

Create a new custom benchmark with:

```bash
kitt test new my-benchmark
```

## Checkpoint Recovery

Long-running benchmarks (especially quality evaluations that process thousands of dataset items) save checkpoints periodically so that interrupted runs can be resumed.

The `CheckpointManager` handles checkpoint persistence:

- **Save interval** -- Every 100 items processed.
- **Checkpoint contents** -- Completed items, partial results, progress index, configuration snapshot.
- **Recovery** -- On restart, if a matching checkpoint exists, the benchmark resumes from where it left off rather than starting over.

Checkpoints are stored locally and are identified by a combination of model, engine, and benchmark name.

## Test Suites

Suites group multiple benchmarks into a single run. KITT ships with three predefined suites:

| Suite | Purpose | Benchmarks | Runs per Benchmark |
|-------|---------|------------|--------------------|
| `quick` | Smoke test | throughput only | 1 |
| `standard` | Full evaluation | all quality + all performance | 3 |
| `performance` | Performance-focused | throughput, latency, memory, warmup | 3 |

### Suite Configuration

Suites are defined in YAML configuration files. A suite config specifies which benchmarks to run, global settings, and optional per-test overrides:

```yaml
name: standard
runs: 3
global_config:
  max_tokens: 256
  temperature: 0.0
benchmarks:
  - throughput
  - latency
  - memory
  - warmup_analysis
  - mmlu
  - gsm8k
  - truthfulqa
  - hellaswag
test_overrides:
  mmlu:
    max_tokens: 64
  gsm8k:
    max_tokens: 512
```

The `global_config` applies to all benchmarks unless overridden. The `test_overrides` section allows per-test configuration within the suite.

## SuiteRunner

The `SuiteRunner` in `runners/` orchestrates suite execution:

1. Load and validate the suite configuration.
2. For each benchmark in the suite, for each run iteration:
    - Initialize the engine (if not already running).
    - Execute the benchmark via `run()`.
    - Collect results and GPU memory data.
3. Aggregate results across runs (mean, stddev, min, max).
4. Generate reports (JSON, Markdown).
5. Persist results through [KARR](karr.md).

## Next Steps

- [Engine Lifecycle](engine-lifecycle.md) -- how engines are started before benchmarks run
- [KARR — Results Storage](karr.md) -- how benchmark results are stored
