# kitt-yaml-runner

Shared runner image for YAML-kind benchmarks. Reads a declarative
spec from `/spec.yaml`, talks to an OpenAI-compatible engine at
`--engine-url`, writes `/results/out.json`.

## Build

```bash
docker build -t kitt-yaml-runner:dev benchmarks-reference/kitt-yaml-runner/
```

## Run

```bash
docker run --rm \
  --network host \
  -v "$PWD/benchmarks-reference/yaml/mmlu.yaml:/spec.yaml:ro" \
  -v "$PWD/results:/results" \
  kitt-yaml-runner:dev \
  --engine-url http://localhost:8000 \
  --model-name Qwen2.5-7B \
  --config /dev/null \
  --spec /spec.yaml
```

## Protocol

See [`benchmarks-reference/README.md`](../README.md).
