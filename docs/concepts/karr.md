# KARR — Results Storage

KARR (Kitt's AI Results Repository) is KITT's results storage system. Every benchmark run, hardware snapshot, and metric is persisted through KARR, giving you a queryable history of all testing activity.

KARR has evolved alongside KITT through multiple generations:

| Generation | Backend | Status |
|------------|---------|--------|
| Gen 1 | Flat JSON files | Still written for convenience |
| Gen 2 | Git repository with LFS | Legacy, available via `--store-karr` |
| Gen 3 | Relational database (SQLite / PostgreSQL) | **Current default** |

The underlying storage mechanism has changed, but the purpose has not: KARR is where your results live.

## Current Backend — Database

The current generation of KARR uses a relational database accessed through the abstract `ResultStore` interface. This makes the backend pluggable while keeping the API consistent.

```
ResultStore (abstract interface)
├── SQLiteResultStore   -- default, ~/.kitt/kitt.db
└── PostgresResultStore -- optional, requires psycopg2
```

The `ResultStore` interface exposes a small, consistent API:

| Method | Purpose |
|--------|---------|
| `save_result()` | Persist a completed benchmark run |
| `get_result()` | Retrieve a single run by ID |
| `query()` | Filter runs by model, engine, date range, etc. |
| `list_results()` | List runs with optional filters and pagination |
| `aggregate()` | Group-by aggregation (e.g., average throughput per engine) |
| `delete_result()` | Remove a run and its related rows (CASCADE) |
| `count()` | Return the total number of stored runs |

### SQLite (Default)

SQLite is the default backend. No configuration is required -- KITT creates `~/.kitt/kitt.db` on first use.

Key characteristics:

- **WAL mode** -- concurrent readers do not block writers, so the web dashboard can query while a benchmark is running.
- **Foreign keys with CASCADE DELETE** -- deleting a run automatically removes its benchmarks, metrics, and hardware rows.
- **Indexes on common query columns** -- model, engine, suite name, and timestamp are indexed for fast filtering.

### PostgreSQL (Production / Distributed)

For multi-agent or web-scale deployments, KARR supports PostgreSQL. Install the extra dependency and provide a DSN connection string:

```bash
poetry install -E postgres        # installs psycopg2
export KITT_DB_DSN="postgresql://user:pass@db-host:5432/kitt"
kitt storage init                  # creates tables in the target database
```

PostgreSQL uses native types where SQLite uses text approximations -- `TIMESTAMPTZ` instead of `TEXT` for timestamps, `JSONB` instead of `TEXT` for raw JSON, `BOOLEAN` instead of `INTEGER`, and `DOUBLE PRECISION` instead of `REAL`.

## Hybrid Data Model

Every run is stored in **two complementary forms**:

1. **Normalized tables** -- `runs`, `benchmarks`, `metrics`, and `hardware` break each run into queryable columns with proper types and foreign-key relationships. This powers filtered listing, cross-run comparison, and group-by aggregation.
2. **`runs.raw_json`** -- the full JSON output produced by KITT is stored verbatim in a single column. This guarantees lossless round-tripping: export always returns exactly what was originally recorded, even if the schema evolves.

## Schema Versioning & Migrations

The database tracks its schema version in the `schema_version` table. KITT ships with an ordered set of migration scripts and applies any that are newer than the recorded version:

```bash
kitt storage migrate              # apply pending migrations
```

The current schema version is **2**. Migrations are forward-only; downgrades are not supported.

## CLI Quick Reference

| Command | Description |
|---------|-------------|
| `kitt storage init` | Create tables (SQLite file or PostgreSQL schema) |
| `kitt storage migrate` | Apply pending schema migrations |
| `kitt storage import` | Import JSON result files into the database |
| `kitt storage export` | Export runs from the database as JSON |
| `kitt storage list` | List stored runs with optional filters |
| `kitt storage stats` | Show summary statistics (run count, models, engines) |

## Flat File Output (Gen 1)

When you run `kitt run`, JSON result files are still written to the `kitt-results/` directory in the current working directory. These files are useful for quick inspection, piping into `jq`, or archiving. The database is the primary storage mechanism and source of truth, but flat files remain as a convenience layer.

## Git-Backed Storage (Gen 2)

!!! note "Legacy"
    Git-backed KARR storage is the previous generation. It remains functional
    and may suit single-machine dev/test workflows, but the database backend
    (Gen 3) is recommended for all new deployments.

The second generation of KARR stored results in a Git repository with LFS tracking. You can still enable it with `--store-karr`.

### Directory Structure (Gen 2)

```
karr-{fingerprint[:40]}/
  {model}/
    {engine}/
      {timestamp}/
        metrics.json
        summary.md
        hardware.json
        config.json
        outputs/
          *.jsonl.gz
```

Large output files in `outputs/` were compressed in 50 MB chunks and tracked by Git LFS. For Docker-based production deployments this approach introduces unnecessary complexity -- mounting Git repos, configuring LFS, and managing repository growth -- that the database backend eliminates entirely.

## Next Steps

- [Database Schema Reference](../reference/database.md) -- full table and column documentation
- [Results Guide](../guides/results.md) -- practical workflows for storing, querying, and comparing results
- [Hardware Fingerprinting](hardware-fingerprinting.md) -- how system identity is captured alongside results
