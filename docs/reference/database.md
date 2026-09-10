# Database Schema Reference

This is the schema reference for [KARR's](../concepts/karr.md) database backend.
KARR uses a relational database to store benchmark results, agent state, campaign
progress, and event logs. The schema is versioned and managed through an
automatic migration system.

**Current schema version:** 10

## Migration System

The `schema_version` table tracks which migrations have been applied:

| Column | Type | Description |
|--------|------|-------------|
| `version` | INTEGER | Migration version number |
| `applied_at` | TEXT | ISO-8601 timestamp when the migration was applied |

Run `kitt storage migrate` to apply any pending migrations. Migrations are
forward-only; downgrades are not supported.

## Tables

### runs

Primary table for benchmark run results. Each row represents one complete
`kitt run` execution.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Unique run identifier (UUID) |
| `model` | TEXT | | Model path or name |
| `engine` | TEXT | | Inference engine used |
| `suite_name` | TEXT | | Test suite that was executed |
| `timestamp` | TEXT | | ISO-8601 run start time |
| `passed` | INTEGER | | 1 if the run passed overall, 0 otherwise |
| `total_benchmarks` | INTEGER | | Number of benchmarks executed |
| `passed_count` | INTEGER | | Number of benchmarks that passed |
| `failed_count` | INTEGER | | Number of benchmarks that failed |
| `total_time_seconds` | REAL | | Wall-clock duration of the entire run |
| `kitt_version` | TEXT | | KITT version that produced the result |
| `raw_json` | TEXT | | Full JSON output for lossless round-tripping |
| `created_at` | TEXT | | ISO-8601 timestamp when the row was inserted |

### benchmarks

Individual benchmark results within a run.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Row identifier |
| `run_id` | TEXT | FOREIGN KEY -> runs(id) ON DELETE CASCADE | Parent run |
| `test_name` | TEXT | | Benchmark name (e.g., `throughput`, `mmlu`) |
| `test_version` | TEXT | | Benchmark version string |
| `run_number` | INTEGER | | Iteration number within the suite |
| `passed` | INTEGER | | 1 if the benchmark passed, 0 otherwise |
| `timestamp` | TEXT | | ISO-8601 benchmark start time |
| `created_at` | TEXT | | Row insertion timestamp |

### metrics

Numeric metric values attached to a benchmark result.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Row identifier |
| `benchmark_id` | INTEGER | FOREIGN KEY -> benchmarks(id) ON DELETE CASCADE | Parent benchmark |
| `metric_name` | TEXT | | Metric key (e.g., `tokens_per_second`, `accuracy`) |
| `metric_value` | REAL | | Numeric value |

### hardware

Hardware snapshot captured at the time of a run.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Row identifier |
| `run_id` | TEXT | FOREIGN KEY -> runs(id) ON DELETE CASCADE | Parent run |
| `gpu_model` | TEXT | | GPU model name |
| `gpu_vram_gb` | INTEGER | | GPU VRAM in gigabytes |
| `gpu_count` | INTEGER | | Number of GPUs |
| `cpu_model` | TEXT | | CPU model name |
| `cpu_cores` | INTEGER | | Number of CPU cores |
| `ram_gb` | INTEGER | | System RAM in gigabytes |
| `environment_type` | TEXT | | Environment (e.g., `native_linux`, `wsl2`, `dgx`) |
| `fingerprint` | TEXT | | Full hardware fingerprint string |

### agents

Registered agent daemons for distributed execution.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Agent identifier (UUID) |
| `name` | TEXT | UNIQUE | Human-readable agent name |
| `hostname` | TEXT | | Agent hostname or IP |
| `port` | INTEGER | | Agent listen port |
| `token` | TEXT | | Legacy raw token (migrated to hash) |
| `token_hash` | TEXT | | SHA-256 hash of authentication token (v4) |
| `token_prefix` | TEXT | | First 8 chars of raw token for display (v4) |
| `status` | TEXT | | Current status (`online`, `offline`, `busy`) |
| `gpu_info` | TEXT | | GPU description string |
| `gpu_count` | INTEGER | | Number of GPUs on the agent |
| `cpu_info` | TEXT | | CPU description string |
| `ram_gb` | INTEGER | | System RAM in gigabytes |
| `environment_type` | TEXT | | Environment type |
| `fingerprint` | TEXT | | Hardware fingerprint |
| `kitt_version` | TEXT | | KITT version running on the agent |
| `hardware_details` | TEXT | | Detailed hardware JSON blob (v5) |
| `last_heartbeat` | TEXT | | ISO-8601 timestamp of last heartbeat |
| `registered_at` | TEXT | | ISO-8601 registration timestamp |
| `notes` | TEXT | | Free-form notes |
| `tags` | TEXT | | JSON array of tags for filtering |
| `cpu_arch` | TEXT | | CPU architecture (`amd64`, `arm64`) (v9) |

### web_campaigns

Campaign definitions and progress tracking for the web dashboard.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Campaign identifier (UUID) |
| `name` | TEXT | | Campaign display name |
| `description` | TEXT | | Human-readable description |
| `config_json` | TEXT | | Full campaign configuration as JSON |
| `status` | TEXT | | Current status (`draft`, `queued`, `running`, `completed`, `failed`, `cancelled`) |
| `agent_id` | TEXT | FOREIGN KEY -> agents(id) | Assigned agent |
| `created_at` | TEXT | | Creation timestamp |
| `started_at` | TEXT | | Execution start timestamp |
| `completed_at` | TEXT | | Completion timestamp |
| `total_runs` | INTEGER | | Total runs planned |
| `succeeded` | INTEGER | | Runs that succeeded |
| `failed` | INTEGER | | Runs that failed |
| `skipped` | INTEGER | | Runs that were skipped |
| `error` | TEXT | | Error message if the campaign failed |

### quick_tests

Single benchmark dispatches from the web UI.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Quick test identifier (UUID) |
| `agent_id` | TEXT | FOREIGN KEY -> agents(id) | Target agent |
| `model_path` | TEXT | | Model path or name |
| `engine_name` | TEXT | | Inference engine |
| `benchmark_name` | TEXT | | Benchmark to run |
| `suite_name` | TEXT | | Suite name (if applicable) |
| `status` | TEXT | | Current status |
| `command_id` | TEXT | | Command ID for heartbeat dispatch (v6) |
| `created_at` | TEXT | | Creation timestamp |
| `started_at` | TEXT | | Execution start timestamp |
| `completed_at` | TEXT | | Completion timestamp |
| `result_id` | TEXT | FOREIGN KEY -> runs(id) | Associated run result |
| `error` | TEXT | | Error message on failure |

### events

Append-only event log for auditing and real-time feeds.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Event sequence number |
| `event_type` | TEXT | | Event category (e.g., `run.started`, `agent.registered`) |
| `source_id` | TEXT | | ID of the entity that produced the event |
| `data` | TEXT | | JSON payload with event-specific details |
| `created_at` | TEXT | | ISO-8601 event timestamp |

### web_settings

Server-wide key-value settings (v3).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `key` | TEXT | PRIMARY KEY | Setting key |
| `value` | TEXT | | Setting value |

### quick_test_logs

Persistent log storage for quick test output (v7).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Row identifier |
| `test_id` | TEXT | FOREIGN KEY -> quick_tests(id) | Parent quick test |
| `line` | TEXT | | Log line content |
| `created_at` | TEXT | | ISO-8601 timestamp |

### agent_settings

Per-agent configurable settings, synced to agents via heartbeat (v8).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Row identifier |
| `agent_id` | TEXT | FOREIGN KEY -> agents(id) ON DELETE CASCADE | Parent agent |
| `key` | TEXT | UNIQUE(agent_id, key) | Setting key |
| `value` | TEXT | | Setting value |

### campaign_logs

Persistent log storage for campaign execution output (v10).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Row identifier |
| `campaign_id` | TEXT | FOREIGN KEY -> web_campaigns(id) | Parent campaign |
| `line` | TEXT | | Log line content |
| `created_at` | TEXT | | ISO-8601 timestamp |

## Indexes

The following indexes are created to accelerate common query patterns:

| Index | Table | Columns |
|-------|-------|---------|
| `idx_runs_model` | runs | `model` |
| `idx_runs_engine` | runs | `engine` |
| `idx_runs_suite_name` | runs | `suite_name` |
| `idx_runs_timestamp` | runs | `timestamp` |
| `idx_benchmarks_run_id` | benchmarks | `run_id` |
| `idx_benchmarks_test_name` | benchmarks | `test_name` |
| `idx_metrics_benchmark_id` | metrics | `benchmark_id` |
| `idx_metrics_name` | metrics | `metric_name` |
| `idx_hardware_run_id` | hardware | `run_id` |
| `idx_agents_name` | agents | `name` |
| `idx_agents_status` | agents | `status` |
| `idx_web_campaigns_status` | web_campaigns | `status` |
| `idx_web_campaigns_agent` | web_campaigns | `agent_id` |
| `idx_quick_tests_agent` | quick_tests | `agent_id` |
| `idx_quick_tests_status` | quick_tests | `status` |
| `idx_events_type` | events | `event_type` |
| `idx_events_source` | events | `source_id` |
| `idx_quick_test_logs_test` | quick_test_logs | `test_id` |
| `idx_campaign_logs_campaign` | campaign_logs | `campaign_id` |
| `idx_agent_settings_agent` | agent_settings | `agent_id` |

## PostgreSQL Differences

When using PostgreSQL instead of SQLite, the following type mappings apply:

| SQLite | PostgreSQL | Affected columns |
|--------|------------|------------------|
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL PRIMARY KEY` | `benchmarks.id`, `metrics.id`, `hardware.id`, `events.id` |
| `TEXT` (timestamps) | `TIMESTAMPTZ` | All `*_at` and `timestamp` columns |
| `TEXT` (JSON) | `JSONB` | `runs.raw_json`, `web_campaigns.config_json`, `events.data` |
| `INTEGER` (booleans) | `BOOLEAN` | `runs.passed`, `benchmarks.passed` |
| `REAL` | `DOUBLE PRECISION` | `runs.total_time_seconds`, `metrics.metric_value` |

PostgreSQL's `JSONB` type enables indexing and querying inside JSON columns
directly with operators like `->`, `->>`, and `@>`.
