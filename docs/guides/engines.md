# Engines

KITT supports multiple inference engines. Engines can run inside Docker
containers or as native host processes, depending on the engine and
environment.

## Supported Engines

| Engine | Key | Docker Image | API Format | Default Port | Model Formats | Modes |
|---|---|---|---|---|---|---|
| vLLM | `vllm` | `vllm/vllm-openai:latest` | OpenAI `/v1/completions` | 8000 | safetensors, pytorch | docker, native |
| llama.cpp | `llama_cpp` | `ghcr.io/ggerganov/llama.cpp:server` | OpenAI `/v1/completions` | 8081 | gguf | docker, native |
| Ollama | `ollama` | `ollama/ollama:latest` | Ollama `/api/generate` | 11434 | gguf | docker, native |
| ExLlamaV2 | `exllamav2` | `kitt/exllamav2:latest` | OpenAI `/v1/completions` | 8000 | exl2, gptq | docker |
| MLX | `mlx` | _(native only)_ | OpenAI `/v1/completions` | 8000 | safetensors, mlx | native |

## Listing Engines

Display all registered engines, their Docker images, pull status, and supported
model formats:

```bash
kitt engines list
```

The output shows **Ready** for engines whose Docker image is already pulled, and
**Not Pulled** for those that still need to be fetched.

## Checking Availability

Run diagnostics on a single engine to see whether its image is available,
Docker is reachable, and which model formats it accepts:

```bash
kitt engines check vllm
kitt engines check ollama
```

If the image has not been pulled, the output includes a `Fix:` hint with the
exact setup command. If Docker itself is not running, you will see a link to the
Docker installation guide.

## Pulling Images

Download the Docker image for an engine:

```bash
kitt engines setup vllm
kitt engines setup ollama
```

Use `--dry-run` to see the `docker pull` command without executing it:

```bash
kitt engines setup --dry-run llama_cpp
```

## Model Format Compatibility

Engines are divided into two groups by the model formats they accept:

**safetensors / pytorch** -- vLLM loads models in their native
HuggingFace format. Point the `--model` flag at a directory containing
`model.safetensors` or `pytorch_model.bin` files (or a HuggingFace repo ID
for engines that support it).

**gguf** -- llama.cpp and Ollama load quantized GGUF files. Point `--model`
at a single `.gguf` file or a directory containing one. Ollama also accepts
its own tag syntax (e.g. `llama3.1:8b`).

Attempting to load a safetensors model in llama.cpp (or a GGUF file in vLLM)
will fail at container startup with a clear error message.

## Custom Engine Configuration

Override engine defaults by writing a YAML config and passing it with
`--config`:

```bash
kitt run -m /models/llama2-7b -e vllm --config ./my-engine.yaml
```

Engine config files live in `configs/engines/` and follow this structure:

```yaml
# configs/engines/vllm.yaml
name: vllm
image: vllm/vllm-openai:latest
port: 8000
health_endpoint: /health
env:
  VLLM_ATTENTION_BACKEND: FLASH_ATTN
extra_args:
  - --max-model-len
  - "4096"
```

Each engine's built-in config is in `configs/engines/<key>.yaml`. You can copy
one of these as a starting point and adjust image tags, environment variables,
or extra CLI arguments passed to the engine server inside the container.

## Engine Lifecycle

When you run `kitt run`, KITT automatically:

1. Starts a Docker container with `--gpus all` and `--network host`.
2. Mounts the model directory into the container.
3. Polls the health endpoint with exponential backoff (up to 300 seconds).
4. Runs benchmarks via the engine's HTTP API on `localhost:<port>`.
5. Stops and removes the container when benchmarks finish.

Container names follow the pattern `kitt-<timestamp>` so they are easy to
identify in `docker ps` output.
