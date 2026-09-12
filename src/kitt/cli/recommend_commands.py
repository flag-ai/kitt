"""Model recommendation CLI commands."""

import logging

import click
from rich.console import Console
from rich.table import Table

console = Console()
logger = logging.getLogger(__name__)


@click.command()
@click.option("--max-vram", type=float, default=None, help="Maximum VRAM in GB")
@click.option("--max-ram", type=float, default=None, help="Maximum RAM in GB")
@click.option(
    "--min-throughput", type=float, default=None, help="Minimum throughput (tokens/sec)"
)
@click.option("--min-accuracy", type=float, default=None, help="Minimum accuracy (0-1)")
@click.option("--max-latency", type=float, default=None, help="Maximum latency (ms)")
@click.option("--engine", default=None, help="Restrict to engine")
@click.option(
    "--sort", type=click.Choice(["score", "throughput", "accuracy"]), default="score"
)
@click.option("--pareto", is_flag=True, help="Show only Pareto-optimal models")
@click.option("--limit", default=10, help="Number of recommendations")
def recommend(
    max_vram,
    max_ram,
    min_throughput,
    min_accuracy,
    max_latency,
    engine,
    sort,
    pareto,
    limit,
):
    """Recommend models based on benchmark history."""
    from kitt.recommend.constraints import HardwareConstraints
    from kitt.recommend.engine import ModelRecommender

    # Try to get a result store
    try:
        from kitt.storage.sqlite_store import SQLiteStore

        store = SQLiteStore()
    except Exception:
        try:
            from kitt.storage.json_store import JsonStore

            store = JsonStore()
        except Exception:
            console.print("[red]No storage backend available.[/red]")
            console.print("Run 'kitt storage init' first.")
            raise SystemExit(1) from None

    constraints = HardwareConstraints(
        max_vram_gb=max_vram,
        max_ram_gb=max_ram,
        min_throughput_tps=min_throughput,
        min_accuracy=min_accuracy,
        max_latency_ms=max_latency,
        engine=engine,
    )

    recommender = ModelRecommender(store)

    if pareto:
        results = recommender.pareto_frontier(constraints=constraints)
        title = "Pareto-Optimal Models"
    else:
        results = recommender.recommend(
            constraints=constraints, limit=limit, sort_by=sort
        )
        title = "Model Recommendations"

    if not results:
        console.print("No models match the specified constraints.")
        return

    table = Table(title=title)
    table.add_column("Rank", style="dim")
    table.add_column("Model", style="cyan")
    table.add_column("Engine")
    table.add_column("Score", justify="right")
    table.add_column("Accuracy", justify="right")
    table.add_column("Throughput", justify="right")

    for i, r in enumerate(results, 1):
        table.add_row(
            str(i),
            r.get("model", "?"),
            r.get("engine", "?"),
            f"{r.get('score', 0):.3f}",
            f"{r.get('accuracy', 0):.3f}",
            f"{r.get('throughput', 0):.1f} tps",
        )

    console.print(table)
