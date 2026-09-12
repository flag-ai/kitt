# Engine Configuration

Engine configuration files customize how KITT launches and communicates
with each inference engine. Files live in `configs/engines/` and are
validated against the `EngineConfig` Pydantic model.

## Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Engine identifier (must match a registered engine) |
| `model_path` | `str` | No | Default model path (usually set at runtime) |
| `parameters` | `dict` | No | Engine-specific parameters passed at startup |

## Built-in engine configs

### vLLM

File: `configs/engines/vllm.yaml`

```yaml
name: vllm
parameters:
  tensor_parallel_size: 1
  gpu_memory_utilization: 0.9
  dtype: auto
  trust_remote_code: false
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `tensor_parallel_size` | `1` | Number of GPUs for tensor parallelism |
| `gpu_memory_utilization` | `0.9` | Fraction of GPU memory to use |
| `dtype` | `auto` | Data type (`auto`, `float16`, `bfloat16`) |
| `trust_remote_code` | `false` | Allow custom model code from HuggingFace |

### llama.cpp

File: `configs/engines/llama_cpp.yaml`

```yaml
name: llama_cpp
parameters:
  n_ctx: 4096
  n_gpu_layers: -1
  n_threads: null
  verbose: false
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `n_ctx` | `4096` | Context window size |
| `n_gpu_layers` | `-1` | GPU layers to offload (`-1` = all) |
| `n_threads` | `null` | CPU threads (`null` = auto-detect) |
| `verbose` | `false` | Enable verbose engine logging |

### Ollama

File: `configs/engines/ollama.yaml`

```yaml
name: ollama
parameters:
  base_url: "http://localhost:11434"
```

## Engine profiles

Named profiles live in `configs/engines/profiles/` and provide preset
parameter combinations. For example, `llama_cpp-high-ctx.yaml` overrides
the default context window for llama.cpp.

## Overriding engine settings at runtime

Engine parameters can also be set through the `EngineConfig` model_path
and parameters at runtime via the CLI or campaign configs:

```bash
kitt run -m /models/llama-8b -e vllm -o ./results
```

Campaign configs can supply per-engine settings in the `engines[].config`
field. See [Campaign Configuration](campaigns.md) for details.
