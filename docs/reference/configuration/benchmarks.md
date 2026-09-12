# Custom Benchmark Configuration

Custom benchmarks allow you to define your own evaluation tests using YAML
files. They are loaded at runtime by the `YAMLBenchmark` class from
`kitt.benchmarks.loader` and validated against the `TestConfig` Pydantic
model.

## File location

Place custom benchmark YAML files in:

```
configs/tests/quality/custom/
```

KITT discovers them automatically when listing tests or running suites.

## Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Unique benchmark identifier |
| `version` | `str` | No | Semantic version (default: `"1.0.0"`) |
| `category` | `str` | Yes | Must be `quality_custom` for custom benchmarks |
| `description` | `str` | No | Human-readable description |
| `warmup` | `WarmupConfig` | No | Warmup phase settings |
| `dataset` | `DatasetConfig` | No | Dataset source configuration |
| `prompts` | `PromptConfig` | No | Prompt template and few-shot settings |
| `sampling` | `SamplingParams` | No | Generation sampling parameters |
| `evaluation` | `EvaluationConfig` | No | Metrics and answer extraction |
| `runs` | `int` | No | Number of runs (default: `3`) |

### DatasetConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `source` | `str` | `null` | HuggingFace dataset ID |
| `local_path` | `str` | `null` | Path to a local dataset directory |
| `split` | `str` | `"test"` | Dataset split to use |
| `sample_size` | `int` | `null` | Number of samples (`null` = all) |

### PromptConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `template` | `str` | `""` | Prompt template with `{question}` placeholder |
| `few_shot` | `int` | `0` | Number of few-shot examples to prepend |
| `few_shot_source` | `str` | `"dev"` | Split to draw few-shot examples from |

### EvaluationConfig

| Field | Type | Description |
|-------|------|-------------|
| `metrics` | `list[str]` | Metric names to compute (e.g. `accuracy`) |
| `answer_extraction` | `dict` | Rules for extracting answers from output |

## Example

```yaml
name: example_custom
version: "1.0.0"
category: quality_custom
description: "Example custom benchmark"

warmup:
  enabled: true
  iterations: 3
  log_warmup_times: true

dataset:
  local_path: ./datasets/custom/
  sample_size: 10

prompts:
  template: |
    Answer the following question concisely.

    Question: {question}
    Answer:

sampling:
  temperature: 0.0
  max_tokens: 256

evaluation:
  metrics:
    - accuracy

runs: 1
```

## Creating a custom benchmark

1. Copy the example file to a new YAML in `configs/tests/quality/custom/`:

    ```bash
    cp configs/tests/quality/custom/example_custom.yaml \
       configs/tests/quality/custom/my_test.yaml
    ```

2. Edit the file: set `name`, `category: quality_custom`, configure the
   dataset source (HuggingFace `source` or `local_path`), and customize
   the prompt template.

3. Verify the benchmark loads:

    ```bash
    kitt test list
    ```

4. Run it as part of a suite or directly:

    ```bash
    kitt run -m /path/to/model -e vllm -s my_suite
    ```
