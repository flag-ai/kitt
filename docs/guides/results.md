# Results & KARR

KARR (Kitt's AI Results Repository) persists all benchmark results. The
current backend is a relational database (SQLite by default, PostgreSQL for
production). Flat JSON files are still written for convenience, and the legacy
Git-backed backend remains available.

## Database Storage (Default)

### Initialize the Database

Create tables in the default SQLite database (`~/.kitt/kitt.db`) or in a
PostgreSQL instance pointed to by `KITT_DB_DSN`:

```bash
kitt storage init
```

Results are saved to the database automatically after every `kitt run`. No extra
flags are needed.

### Import Existing JSON Results

Bring previously exported or flat-file results into KARR:

```bash
kitt storage import ./kitt-results/run1/metrics.json
kitt storage import ./kitt-results/               # imports all runs found
```

### Export Results

Export runs from KARR back to JSON files:

```bash
kitt storage export --output ./export/
kitt storage export --model llama --engine vllm --output ./export/
```

### List Stored Runs

Browse what is stored in KARR with optional filters:

```bash
kitt storage list
kitt storage list --model llama --engine vllm --limit 20
```

Output includes run ID, model, engine, suite, timestamp, and pass/fail counts.

### Database Statistics

Get a high-level summary of KARR contents:

```bash
kitt storage stats
```

This shows total runs, unique models, unique engines, date range, and storage
size.

## Querying Results

The `ResultStore` interface supports filtered queries and aggregation from the
CLI or programmatically.

### Filter by Model, Engine, or Suite

```bash
kitt storage list --model "Llama-3.1-8B" --engine vllm
kitt storage list --suite performance --limit 5
```

### Aggregation

Group results by model or engine to compare averages:

```bash
kitt storage stats --group-by model
kitt storage stats --group-by engine
```

This is useful for spotting regressions across a fleet of models or engines.

## Schema Migrations

When upgrading KITT, apply any pending database migrations:

```bash
kitt storage migrate
```

The current schema version is **2**. See the
[Database Schema Reference](../reference/database.md) for full table
documentation.

## Flat File Output

Every `kitt run` writes JSON results to a `kitt-results/` directory in the
current working directory, regardless of database settings. These files are
handy for:

- Quick inspection with `jq` or a text editor
- Archiving to external storage
- Sharing individual run data without database access

The flat files mirror the content stored in `runs.raw_json` in the database.

## Comparing Results

### CLI Comparison

Compare metrics across two or more benchmark runs:

```bash
kitt results compare ./run1 ./run2
kitt results compare ./run1 ./run2 --additional ./run3 --format json
```

The table output shows min, max, average, standard deviation, and coefficient
of variation for each metric. Paths can point to flat-file result directories
or exported database runs.

### Interactive TUI

Launch a side-by-side terminal comparison (requires the `cli_ui` extra):

```bash
kitt compare ./run1 ./run2
```

Both `kitt results compare` and `kitt compare` work with flat-file directories
and database-exported results interchangeably.

## Git-Backed Storage (Legacy)

!!! note "Legacy Backend"
    Git-backed KARR storage is the previous generation (Gen 2). It remains
    available via `--store-karr` for backward compatibility, but the database
    backend is recommended for all new deployments.

The previous generation of KARR stored results in a Git repository with LFS
tracking. To use it, add `--store-karr` to a run:

```bash
kitt results init --path ./my-results
kitt run -m /models/llama-7b -e vllm -s standard --store-karr ./my-results
kitt results list --karr ./my-results
```

### Directory Structure (Gen 2)

```
karr-<fingerprint>/
  <model>/
    <engine>/
      <timestamp>/
        metrics.json
        summary.md
        hardware.json
        config.json
        outputs/          # compressed .jsonl.gz, tracked by Git LFS
```

For Docker-based deployments, Git repos are cumbersome to mount and manage.
The database backend removes this friction entirely.

## Next Steps

- [KARR — Results Storage](../concepts/karr.md) -- architecture and design decisions
- [Database Schema Reference](../reference/database.md) -- full table and column documentation
- [Hardware Fingerprinting](../concepts/hardware-fingerprinting.md) -- how system identity is captured
