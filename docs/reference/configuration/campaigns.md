# Campaign Configuration

Campaign configuration files define multi-model, multi-engine benchmark
runs. KITT expands the campaign into a matrix of
**models x engines x suites** and executes each combination. Files live
in `configs/campaigns/`.

## Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `campaign_name` | `str` | Yes | Unique campaign identifier |
| `description` | `str` | No | Human-readable description |
| `schedule` | `str` | No | Cron expression for scheduled runs |
| `auto_compare` | `bool` | No | Compare with previous run on completion |
| `models` | `list[Model]` | Yes | Models to benchmark |
| `engines` | `list[Engine]` | Yes | Engines to test against |
| `disk` | `DiskConfig` | No | Disk space management |
| `notifications` | `NotifyConfig` | No | Notification settings |
| `quant_filter` | `QuantFilter` | No | Quantization file filters |
| `resource_limits` | `ResourceLimits` | No | Skip models exceeding limits |
| `parallel` | `bool` | No | Run combinations in parallel (default: `false`) |
| `devon_managed` | `bool` | No | Use Devon for model downloads (default: `false`) |

### Model entry

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Model display name |
| `params` | `str` | Parameter count label (e.g. `"8B"`) |
| `safetensors_repo` | `str` | HuggingFace repo for safetensors format |
| `gguf_repo` | `str` | HuggingFace repo for GGUF format |
| `ollama_tag` | `str` | Ollama model tag |
| `estimated_size_gb` | `float` | Approximate disk footprint |

### Engine entry

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Registered engine name |
| `suite` | `str` | Suite to run for this engine |
| `formats` | `list[str]` | Accepted model formats (`safetensors`, `gguf`) |
| `config` | `dict` | Engine-specific parameter overrides |
| `quant_filter` | `str` | Specific quantization to select |

## Example

```yaml
campaign_name: example-campaign
description: "Test 2 models across llama.cpp and Ollama"

models:
  - name: Llama-3.1-8B-Instruct
    params: "8B"
    safetensors_repo: meta-llama/Llama-3.1-8B-Instruct
    gguf_repo: bartowski/Meta-Llama-3.1-8B-Instruct-GGUF
    ollama_tag: "llama3.1:8b"
    estimated_size_gb: 16.0

  - name: Qwen2.5-7B-Instruct
    params: "7B"
    safetensors_repo: Qwen/Qwen2.5-7B-Instruct
    gguf_repo: Qwen/Qwen2.5-7B-Instruct-GGUF
    ollama_tag: "qwen2.5:7b"
    estimated_size_gb: 14.0

engines:
  - name: llama_cpp
    suite: standard
    formats: [gguf]
    config: {}

  - name: ollama
    suite: standard
    formats: [gguf]
    config: {}

disk:
  reserve_gb: 100.0
  cleanup_after_run: true

notifications:
  desktop: true
  on_complete: true
  on_failure: true

quant_filter:
  skip_patterns:
    - "IQ1_*"
    - "IQ2_*"
    - "Q4_0_4_4"
    - "Q4_0_4_8"
    - "Q4_0_8_8"

parallel: false
devon_managed: true
```

## Matrix expansion

Given 2 models and 2 engines, KITT creates 4 benchmark runs (one per
combination). Each run uses the suite specified in the engine entry.
Models are matched to engines based on the `formats` field -- for example,
a model without a `gguf_repo` will be skipped for engines that require
the `gguf` format.

## Scheduled campaigns

Add a `schedule` field with a cron expression to run the campaign
automatically:

```yaml
schedule: "0 2 * * *"   # 2 AM daily
auto_compare: true
```
