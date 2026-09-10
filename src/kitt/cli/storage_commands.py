"""Storage CLI commands."""

import logging
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()
logger = logging.getLogger(__name__)


@click.group()
def storage():
    """Manage the KITT result storage backend."""


@storage.command()
@click.option(
    "--db-path",
    type=click.Path(),
    default=None,
    help="SQLite database path (default: ~/.kitt/kitt.db)",
)
def init(db_path):
    """Initialize the SQLite storage database."""
    from kitt.storage.sqlite_store import SQLiteStore

    path = Path(db_path) if db_path else None
    store = SQLiteStore(db_path=path)
    console.print(f"[green]Database initialized at {store.db_path}[/green]")
    store.close()


@storage.command()
@click.option(
    "--db-path",
    type=click.Path(),
    default=None,
    help="SQLite database path",
)
def migrate(db_path):
    """Run pending database migrations."""
    from kitt.storage.sqlite_store import SQLiteStore

    path = Path(db_path) if db_path else None
    store = SQLiteStore(db_path=path)
    console.print("[green]Migrations complete.[/green]")
    store.close()


@storage.command("import")
@click.argument("source", type=click.Path(exists=True))
@click.option(
    "--db-path",
    type=click.Path(),
    default=None,
    help="SQLite database path",
)
def import_results(source, db_path):
    """Import results from a directory or JSON file into the database."""
    from kitt.storage.sqlite_store import SQLiteStore

    path = Path(db_path) if db_path else None
    store = SQLiteStore(db_path=path)

    source_path = Path(source)
    if source_path.is_file() and source_path.suffix == ".json":
        run_id = store.import_json(source_path)
        console.print(f"Imported 1 result (ID: {run_id})")
    elif source_path.is_dir():
        count = store.import_directory(source_path)
        console.print(f"[green]Imported {count} result(s) into {store.db_path}[/green]")
    else:
        console.print("[red]Source must be a .json file or directory.[/red]")
        raise SystemExit(1)

    store.close()


@storage.command("export")
@click.argument("result_id")
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    required=True,
    help="Output JSON path",
)
@click.option("--db-path", type=click.Path(), default=None)
def export_result(result_id, output, db_path):
    """Export a result from the database to a JSON file."""
    from kitt.storage.sqlite_store import SQLiteStore

    path = Path(db_path) if db_path else None
    store = SQLiteStore(db_path=path)

    out = store.export_result(result_id, Path(output))
    if out:
        console.print(f"[green]Exported to {out}[/green]")
    else:
        console.print(f"[red]Result not found: {result_id}[/red]")
        raise SystemExit(1)
    store.close()


@storage.command("list")
@click.option("--db-path", type=click.Path(), default=None)
@click.option("--model", default=None, help="Filter by model")
@click.option("--engine", default=None, help="Filter by engine")
@click.option("--limit", type=int, default=50, help="Max results to show")
def list_results(db_path, model, engine, limit):
    """List results stored in the database."""
    from kitt.storage.sqlite_store import SQLiteStore

    path = Path(db_path) if db_path else None
    store = SQLiteStore(db_path=path)

    filters = {}
    if model:
        filters["model"] = model
    if engine:
        filters["engine"] = engine

    results = store.query(filters=filters or None, order_by="-timestamp", limit=limit)

    table = Table(title=f"Stored Results ({len(results)} shown)")
    table.add_column("Model", style="cyan")
    table.add_column("Engine")
    table.add_column("Suite")
    table.add_column("Status")
    table.add_column("Benchmarks")
    table.add_column("Timestamp")

    for r in results:
        status = "[green]PASS[/green]" if r.get("passed") else "[red]FAIL[/red]"
        table.add_row(
            r.get("model", "")[:40],
            r.get("engine", ""),
            r.get("suite_name", ""),
            status,
            f"{r.get('passed_count', 0)}/{r.get('total_benchmarks', 0)}",
            str(r.get("timestamp", ""))[:19],
        )

    console.print(table)
    total = store.count()
    console.print(f"Total results in database: {total}")
    store.close()


@storage.command()
@click.option("--db-path", type=click.Path(), default=None)
def stats(db_path):
    """Show storage statistics."""
    from kitt.storage.sqlite_store import SQLiteStore

    path = Path(db_path) if db_path else None
    store = SQLiteStore(db_path=path)

    total = store.count()
    passed = store.count({"passed": True})
    failed = store.count({"passed": False})

    console.print("[bold]Storage Statistics[/bold]")
    console.print(f"  Database: {store.db_path}")
    console.print(f"  Total results: {total}")
    console.print(f"  Passed: [green]{passed}[/green]")
    console.print(f"  Failed: [red]{failed}[/red]")

    by_engine = store.aggregate("engine")
    if by_engine:
        console.print("\n  [bold]By Engine:[/bold]")
        for row in by_engine:
            console.print(f"    {row['engine']}: {row['count']} runs")

    by_model = store.aggregate("model")
    if by_model:
        console.print(f"\n  [bold]By Model:[/bold] ({len(by_model)} distinct)")

    store.close()
