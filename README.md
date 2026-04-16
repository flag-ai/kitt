# KITT

**Kirizan's Inference Testing Tools** — a web-based benchmarking and
quality-regression suite for local LLM inference engines.

Part of the [FLAG](https://github.com/flag-ai) platform: KITT tests
inference engines, [DEVON](https://github.com/flag-ai/devon) manages
the models, and [BONNIE](https://github.com/flag-ai/bonnie) runs the
engines and benchmark containers on the GPU host.

## Architecture

KITT runs as a single Go binary with an embedded React SPA, backed by
Postgres. It does not execute benchmarks locally — instead it asks
DEVON to stage the model on a GPU host, then asks BONNIE on that host
to orchestrate the paired engine + benchmark containers.

```
┌────────────────────────────────┐
│  KITT (this repo)              │
│  - Web UI (embedded React)     │
│  - HTTP API (Chi v5)           │
│  - Campaign runner             │
│  - Engine registry             │
│  - Benchmark registry          │
│  - Cron scheduler              │
│  - Postgres (pgxpool + sqlc)   │
└──────────┬──────────┬──────────┘
           │          │
           │          └─── asks DEVON to stage model on a host
           │
           └────────── asks BONNIE on that host to run the
                       paired engine + benchmark containers
```

## Running KITT

### With Docker Compose (recommended)

```bash
cp .env.example .env
# Edit .env — at minimum set POSTGRES_PASSWORD and KITT_ADMIN_TOKEN.
docker compose up -d
```

First-run bootstrap is exposed via `POST /api/v1/setup` if
`KITT_ADMIN_TOKEN` is not pre-seeded; otherwise the web UI is
immediately ready behind the bearer token you configured.

### Local development

```bash
make dev                      # brings up Postgres
go run ./cmd/kitt migrate up  # apply migrations
go run ./cmd/kitt serve       # starts the web server on :8080
```

The web SPA lives under `web/` and is built into `web/dist/` for the
Go binary to embed.

```bash
cd web
npm ci
npm run dev     # Vite dev server with proxy
npm run build   # required before `go build` — the binary embeds dist/
```

### Environment variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Postgres DSN (required) |
| `KITT_ADMIN_TOKEN` | Bearer token for the web UI / HTTP API (required) |
| `KITT_DEVON_URL` | DEVON base URL for `/models/ensure` calls |
| `KITT_DEVON_TOKEN` | Bearer token used when calling DEVON |
| `KITT_SLACK_WEBHOOK` | Slack incoming-webhook URL for notifications |
| `KITT_DISCORD_WEBHOOK` | Discord incoming-webhook URL for notifications |
| `KITT_CORS_ORIGINS` | Comma-separated allowlist for browser clients |
| `LOG_LEVEL` | `debug` / `info` / `warn` / `error` |
| `LOG_FORMAT` | `text` or `json` |

Secrets may also be loaded from [OpenBao](https://openbao.org/) via
the `flag-commons` secrets provider — see the `internal/config/`
package.

## Repo layout

```
kitt/
├── cmd/kitt/                   Entrypoint (serve, migrate, version)
├── internal/
│   ├── api/                    Chi router + handlers + middleware
│   ├── benchmarks/             Benchmark kinds (yaml, container)
│   ├── bonnie/                 Thin wrapper over flag-commons/bonnie
│   ├── campaign/               Runner + cron scheduler + state
│   ├── config/                 Env / OpenBao config loader
│   ├── db/                     sqlc-generated queries + *.sql sources
│   ├── devon/                  HTTP client for /models/ensure
│   ├── engines/                Compile-in engine registry
│   ├── models/                 API-layer DTOs
│   ├── notifications/          Slack + Discord webhook dispatchers
│   ├── recommendation/         Engine + quant recommender
│   ├── service/                Service-layer glue
│   └── storage/                Postgres-backed result store
├── migrations/                 golang-migrate SQL migrations
├── web/                        React / Vite / TypeScript SPA (embedded)
├── benchmarks-reference/       Reference benchmark library (PR J)
│   ├── yaml/                   Declarative YAML benchmark specs
│   ├── containers/             Containerized benchmark harnesses
│   ├── kitt-yaml-runner/       Shared runner image for YAML kind
│   └── tools/                  Mock engine + smoke test
├── .github/workflows/
│   ├── ci.yml                  Lint + test + sqlc + security + web + smoke
│   └── publish-benchmarks.yml  Benchmark image matrix on release tags
├── Dockerfile                  Multi-stage: Node → Go → Alpine
├── docker-compose.yml          Reference compose
├── Makefile                    Common tasks
└── migrations/                 SQL migrations
```

## Benchmarks

KITT 2.x ships a hybrid benchmark catalog: **declarative YAML**
benchmarks for the simple score-the-letter evals, and **container
benchmarks** for anything needing a runtime (sandboxed code
execution, multimodal inputs, GPU introspection).

Both kinds live in [`benchmarks-reference/`](./benchmarks-reference/)
and are registered at first boot into the `benchmark_registry`
table. The web UI `Benchmarks` page surfaces every entry and lets
operators disable/enable individual ones per campaign.

Container images are published by
`.github/workflows/publish-benchmarks.yml` to
`ghcr.io/flag-ai/kitt-<name>:<version>` on every release tag.

Every benchmark image — and the `kitt-yaml-runner` — implements the
uniform container protocol documented in
[`benchmarks-reference/README.md`](./benchmarks-reference/README.md):
a fixed CLI (`--engine-url`, `--model-name`, `--config`), a
`/results/out.json` output schema, and POSIX exit codes.

## Testing

```bash
make test                # go test -race -cover
make test-integration    # integration tests (requires Postgres)
make lint                # golangci-lint
make security            # gosec
make smoke-benchmarks    # every benchmark entrypoint vs a mock engine
```

## Status

This is the Go rewrite of the original Python KITT. The Python source
is preserved on the `python-legacy` branch for reference. Fresh
installs should start from a clean Postgres; there is no automatic
data migration from the Python 1.x series.

## License

Apache 2.0. See [LICENSE](./LICENSE).
