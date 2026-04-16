# benchmarks-reference

Reference implementations of the KITT benchmark catalog. These sources
produce the YAML specs and container images that ship pre-seeded in
the `benchmark_registry` table.

Two kinds, matching the hybrid schema established in PR D:

- **`yaml/`** — declarative prompts + grading rules. Consumed at
  runtime by [`kitt-yaml-runner`](./kitt-yaml-runner/), a single
  container image that reads a YAML spec, hits the engine's
  OpenAI-compatible endpoint, and writes a results JSON.
- **`containers/`** — one directory per benchmark that needs its own
  runtime (sandboxed code execution, GPU introspection, multimodal
  inputs, etc.). Each directory contains a `Dockerfile` and an
  `entrypoint.py` implementing the container protocol below.

Images are published by `.github/workflows/publish-benchmarks.yml` on
release tags to `ghcr.io/flag-ai/kitt-<name>:<version>` and
`:latest`.

## Container protocol

Every benchmark container — including `kitt-yaml-runner` — MUST
implement the following contract so the campaign runner can dispatch
them uniformly.

### Invocation

```
<image> --engine-url <url> --model-name <name> --config /config.json [--spec /spec.yaml]
```

| Flag | Meaning |
|------|---------|
| `--engine-url` | Base URL of the running engine (e.g. `http://engine:8000`). OpenAI-compatible unless the benchmark explicitly says otherwise. |
| `--model-name` | Model identifier to pass in the API request body. |
| `--config` | Path to a benchmark-specific JSON config file (mounted by BONNIE's paired-run helper). |
| `--spec` | **YAML-runner only.** Path to the declarative spec being executed. |

### Outputs

- **`/results/out.json`** — MUST be written on success. Schema:
  ```json
  {
    "benchmark": "<name>",
    "score": 0.0,              // normalized primary metric (0..1 or raw)
    "metrics": {               // flat map of additional measurements
      "accuracy": 0.84,
      "items_evaluated": 500
    },
    "duration_ms": 12345,
    "metadata": {              // opaque to the runner; surfaced in UI
      "dataset_revision": "...",
      "samples_skipped": 0
    }
  }
  ```
- **stdout / stderr** — structured or unstructured logs. Streamed by
  BONNIE as an SSE event channel.

### Exit codes

- `0` — success; `/results/out.json` must exist and parse.
- non-zero — failure; any partial output under `/results/` is read and
  attached to the run record for debugging.

## Local development

Each container builds standalone:

```bash
docker build -t kitt-<name>:dev benchmarks-reference/containers/<name>
```

The `make smoke-benchmarks` target in the repo root builds every
container and runs it against a stubbed OpenAI-compatible endpoint to
verify the protocol contract. CI runs the same target on every PR
touching `benchmarks-reference/`.
