# Changelog

All notable changes to KITT are documented on this page.

## 1.8.1

- Retired the "KARR (Kitt's AI Results Repository)" name for KITT's results storage. In the FLAG platform, KARR is Kirizan's AI Refinement Runtime (the control plane for BONNIE agents), so docs and CLI help now say "results storage" and "git-backed result store" instead. The concepts page moved from `concepts/karr.md` to `concepts/results-storage.md`.
- No behaviour change: `--store-karr`, `--karr`, `KARRRepoManager`, and the `karr-<fingerprint>/` layout are unchanged

## 1.8.0

- **Rolled back to the Python implementation** — `main` now carries the Python tree again after the Go rewrite (2.0.0–2.9.1) was retired
    - The Go code is preserved in the `go-migration-2.9.1` tag and in `main`'s history; the 2.x version line is permanently retired
    - Versions resume at 1.8.0 so the number never moves backwards (the thin agent's `update` command compares server versions)
    - The Go-only `benchmarks-reference/` container library is not carried forward; it will return with the containerized benchmark dispatch port

## 1.7.0

- Added native (non-Docker) execution mode for engines, with `ProcessManager` handling host process lifecycle
- Added engine profiles — named build/runtime configurations stored in the `engine_profiles` table, selectable in quicktest and the campaign wizard
- Removed the TGI engine

## 1.6.2

- Added real agent campaign dispatch via heartbeat — campaigns on real agents now break into individual quick test rows, queue them one at a time, and poll for completion using the existing heartbeat mechanism
- Campaign executor tracks progress with campaign-level log streaming, handles cancellation, and enforces a 30-minute per-test timeout

## 1.6.1

- Fixed campaign live log streaming stuck on "waiting for logs..." — simulation published events to test ID channels but the detail page subscribed to the campaign ID channel
- Replaced HTMX SSE with JavaScript EventSource + Alpine.js in campaign detail template (matching the quick test pattern)
- Persisted campaign logs to database (`campaign_logs` table, schema v10) so page refresh and post-completion views show log history
- Added `GET /api/v1/campaigns/<id>/logs` endpoint for stored log retrieval
- Fixed SSE connection not closing on cancelled status
- Added cancellation check between iterations in campaign simulation loop

## 1.6.0

- Added interactive campaign creation wizard with step-by-step flow: agent selection, engine compatibility filtering with format badges and platform warnings, searchable model multi-select, and compatibility matrix review
- Added virtual test agents for end-to-end UI testing without real GPU hardware — configurable hardware specs, always-online status, TEST badge in agent list
- Test agents simulate quick test and campaign execution with realistic delays, live SSE log streaming, and fake result generation through the normal ResultStore pipeline
- Campaign and quicktest APIs detect test agents and spawn simulation threads instead of dispatching to agents
- Added result generator producing realistic metrics for throughput, latency, memory, and accuracy benchmarks
- Fixed stored XSS in campaign row rendering by escaping user values
- Added thread safety with `db_write_lock` on all quicktest DB writes
- Added input validation for integer form fields in test agent creation

## 1.5.0

- Added agent-aware engine filtering to quick test UI — engines dynamically populated from API based on selected agent's CPU architecture
- Added `get_engine_compatibility()` in image resolver reporting per-engine ARM64/x86_64 compatibility
- Added `GET /api/v1/quicktest/agent-capabilities` endpoint returning per-agent engine compatibility
- Added override toggle and `force` flag to bypass both platform and model-format validation
- Fixed Devon UI "connecting" stuck state (`htmx:afterSwap` → `htmx:afterRequest`)
- ARM64 engine fixes: Docker CLI static binary, GGUF directory resolution, Ollama local import, vLLM NGC prefix detection

## 1.4.1

- Fixed `SCHEMA_VERSION` not incremented after adding migration v9 (`cpu_arch` column), so the migration never ran on server startup
- Added `cpu_arch` to Postgres fresh-install schema

## 1.4.0

- Added platform-aware image selection for ARM64 and multi-arch support — image resolver considers CPU architecture alongside GPU compute capability
- ARM64 boards (DGX Spark, Jetson Orin) get platform-specific images for engines without multi-arch builds
- Added `--platform` flag to `DockerManager.pull_image()` and `build_image()`
- Added `cpu_arch` field to agent registration, models, and database (migration v9)
- Added `kitt/llama-cpp:arm64` build recipe and Dockerfile for ARM64 hosts
- Fixed arm64/aarch64 architecture mismatch in agent Docker checks — added `normalize_arch()` for consistent naming
- Added `kitt remote` CLI commands for managing remote GPU servers via SSH

## 1.3.0

- Fixed end-to-end remote execution on DGX Spark
- Added agent 404 recovery with hostname fallback and canonical ID sync
- Added model format validation preflight checks — engines declare supported formats and KITT blocks incompatible model/engine combinations before container launch
- Added web UI engine/model compatibility filtering in quick test form
- Added configurable engine images via `~/.kitt/engines.yaml`
- Added `--auto-pull` flag to `kitt run` for automatic engine image pulling
- Added `kitt remote engines setup` command for remote engine image management

## 1.2.1

- Fixed agent benchmark results never reaching the server — `_execute_test()` now reads `metrics.json` from the output directory and forwards it as `result_data` in `_report()`
- Fixed `PermissionError` when `kitt run` defaults to relative `kitt-results/` inside a Docker container — agent now passes `-o` with a writable temp directory to `kitt run`
- Changed default output directory for `kitt run` from relative `kitt-results/` to `~/.kitt/results/` for robustness across environments
- Temp output directories (`/tmp/kitt-results-*`) are cleaned up after agent benchmarks complete
- Fixed architecture mismatch in agent Docker image selection — now checks image arch against host arch before use, falling back to locally-built `kitt:latest` when the registry image is the wrong platform
- Fixed `_report()` using agent name instead of agent ID in URL, causing 404 on result submission
- Fixed Docker entrypoint override for benchmark containers — added `--entrypoint kitt` since the KITT image has `ENTRYPOINT ["kitt", "web"]`
- Reverted Docker CLI package name in Dockerfiles back to `docker.io` — `docker-cli` does not exist in Debian bookworm repos
- Updated hardcoded `kitt_version` references from `1.1.0` to `1.2.1`
- Fixed `_check_auth()` timing attack — replaced `==` with `hmac.compare_digest` for constant-time token comparison
- Fixed thread safety — write lock now wraps entire SQLite transactions (execute + commit), not just the commit
- Fixed `_find_on_share()` path traversal — resolved candidates are validated against the share mount root
- Fixed result detail 404 — `query()` and `get_result()` now include the database ID in returned results
- Fixed `kitt --version` reporting wrong version — now reads from `kitt.__version__` dynamically
- Fixed cleanup button in agent detail page targeting the wrong endpoint (API instead of blueprint)
- Added `@require_auth` to `GET /api/v1/agents/<id>/settings` endpoint
- Added `kitt_image` to migration v8 defaults for consistency with `AgentManager._DEFAULT_SETTINGS`
- Added CSRF protection (`@csrf_protect`) to all state-changing web blueprint endpoints
- Added SHA-256 integrity verification for agent package downloads and build context
- Added Docker environment variable redaction in container start logs
- Added rotating file logging to agent (`~/.kitt/logs/agent.log`, 5MB per file, 3 backups)
- Fixed preflight server reachability check — tries TLS verification first, falls back to insecure for self-signed certs
- Fixed preflight `URLError`-wrapped SSL errors bypassing the insecure fallback
- Removed unused `verify` and `client_cert` parameters from `_report()` function
- Fixed cleanup endpoints bypassing `_write_lock` — extracted `AgentManager.queue_cleanup_command()` method
- Fixed `register()` TOCTOU race — moved SELECT inside write lock to prevent concurrent duplicate inserts
- Fixed `_find_on_share()` glob results not validated against share root (symlink traversal)
- Fixed `_find_on_share()` path validation to use `relative_to()` instead of `str.startswith()` for robustness
- Fixed `csrf_protect` Bearer token exemption — now validates the token before bypassing CSRF check
- Fixed hardcoded `kitt_version` in `run.py` and `json_reporter.py` — now uses `kitt.__version__` dynamically
- Fixed HTMX storage polling in agent detail page targeting JSON endpoint instead of HTML page
- Fixed `tarfile.extractall(filter="data")` incompatibility with Python 3.10 — guarded with version check
- Removed obsolete `docker/agent/Dockerfile` referencing deleted full agent
- Fixed `docker-cli` references in documentation (`docs/reference/docker-files.md`)
- Replaced f-string logger calls with lazy `%s` formatting across agent package and server
- Refactored API token verification — extracted `check_agent_auth()` and `check_agent_auth_by_name()` methods on `AgentManager`, removing raw `_conn` access from API endpoints
- Fixed `tarfile.extractall(filter="data")` guard to use `try/except TypeError` instead of version check, correctly handling Python 3.11.4+ backport
- Fixed `docs/reference/api.md` auth column for `GET /api/v1/agents/<id>/settings` — was incorrectly listed as unauthenticated
- Removed stale `docker/agent/Dockerfile` row from `docs/reference/docker-files.md`
- Removed dead `docker/agent/Dockerfile` reference in stack generator
- Fixed remaining f-string logger calls in `migrations.py` and `agent_install.py`
- Updated stale `kitt_version` in test fixtures from `1.1.0` to `1.2.1`
- Reverted `docker-cli` back to `docker.io` in Dockerfiles — `docker-cli` does not exist in Debian bookworm repos
- Added `save_result()` method to `ResultService` — `report_result` endpoint no longer accesses private `_store` directly
- Fixed `docs/reference/api.md` auth columns for `PATCH` and `DELETE` agent endpoints — were incorrectly listed as unauthenticated
- Fixed `docs/concepts/architecture.md` result reporting URL from `{name}` to `{id}`
- Fixed install script preflight check — `if [ $? -ne 0 ]` was dead code under `set -euo pipefail`, replaced with `if ! command` pattern
- Fixed Docker container leak on health check timeout — container is now stopped before reporting failure
- Removed unused `--foreground` flag from `kitt agent start` proxy command
- Fixed all `docs/reference/api.md` auth columns to match actual `@require_auth` decorators (results, campaigns, models sections)
- Updated README thin agent architecture description to reflect model resolution, Docker benchmark execution, and heartbeat command dispatch

## 1.2.0

- Agent model workflow: copy models from NFS share to local storage, benchmark, cleanup
- Per-agent settings configurable from the web UI (model storage, share mount, cleanup, heartbeat interval)
- Agent settings synced to agents via heartbeat response
- NFS share mounting support with fstab and explicit mount fallback
- Preflight prerequisite checks (`kitt-agent preflight`) — Docker, GPU, drivers, NFS, disk space, connectivity
- Install script runs preflight before completing installation
- Heartbeat throttling during benchmarks (auto-increases interval to 60s minimum)
- `cleanup_storage` command for remote model cleanup via heartbeat dispatch
- Storage usage reporting in heartbeat payload
- Removed full agent (`src/kitt/agent/`) — thin agent (`agent-package/`) is now the only agent
- `kitt agent` CLI commands now proxy to `kitt-agent` binary
- Agent settings REST API endpoints (`GET`/`PUT /api/v1/agents/<id>/settings`)
- Storage cleanup REST API (`POST /api/v1/agents/<id>/cleanup`)
- DB migration v8: `agent_settings` key-value table per agent
- Daemon refactored — consolidated duplicated run methods into shared helpers
- Version policy: every PR must increment version going forward
- `kitt-agent build` command for native-arch Docker image building
- Docker container is the preferred benchmark execution method (local CLI is fallback)
- Build context API endpoint (`/api/v1/agent/build-context`)
- Install script auto-builds Docker image during agent installation
- Preflight check for KITT Docker image availability

## 1.1.0

- Added composable Docker deployment stacks (`kitt stack`)
- Added web UI and distributed agent architecture
- Added monitoring stack generation and remote deployment
- Added documentation site with MkDocs Material
- Added UI-configurable settings — Model Directory, Devon URL, and Results Directory can be edited from the Settings page with live updates
- Added inline Devon URL setup form on the Devon page
- Added searchable model dropdown to Quick Test — loads from Devon's `manifest.json` with fuzzy search
- Added heartbeat-based command dispatch — agents pull queued quick tests via heartbeat response
- Added live SSE log streaming to Quick Test — real-time output with status progression
- Added Quick Test API endpoints for log forwarding and status updates
- Added Quick Test history page with status filtering and pagination
- Added Quick Test detail page with SSE live logs and stored log retrieval
- Added persistent log storage — log lines are saved to the database for post-run viewing
- Added `kitt-agent test list` and `kitt-agent test stop` CLI commands for managing tests from the agent host
- Fixed thin agent (`kitt-agent`) log forwarding and command dispatch — heartbeat now processes queued commands, `run_test`/`run_container` extract `test_id` and forward logs and status updates to the server
- Added `agent_name` query parameter to the quick test list API endpoint

## 1.0.0

- Initial release
- Multi-engine support: vLLM, TGI, llama.cpp, Ollama
- Quality benchmarks: MMLU, GSM8K, TruthfulQA, HellaSwag
- Performance benchmarks: throughput, latency, memory, warmup
- Hardware fingerprinting
- KARR results storage
- Web dashboard and REST API
- CI integration
