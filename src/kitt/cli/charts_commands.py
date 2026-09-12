"""Chart generation CLI commands."""

import logging

import click
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)


@click.group()
def charts():
    """Generate charts and visualizations."""


@charts.command("quant-curves")
@click.option(
    "--model-family", default=None, help="Filter by model family (e.g. Llama-3)"
)
@click.option("--output", "-o", default="quant_curves.svg", help="Output file path")
@click.option("--csv", "export_csv", is_flag=True, help="Export data as CSV instead")
def quant_curves(model_family, output, export_csv):
    """Generate quantization quality tradeoff curves."""
    # Get result store
    try:
        from kitt.storage.sqlite_store import SQLiteStore

        store = SQLiteStore()
    except Exception:
        try:
            from kitt.storage.json_store import JsonStore

            store = JsonStore()
        except Exception:
            console.print("[red]No storage backend available.[/red]")
            raise SystemExit(1) from None

    from kitt.reporters.quant_curves import QuantCurveGenerator

    gen = QuantCurveGenerator(result_store=store)

    if export_csv:
        csv_path = gen.export_csv(
            model_family=model_family, output_path=output.replace(".svg", ".csv")
        )
        console.print(f"[green]CSV exported to {csv_path}[/green]")
    else:
        result = gen.generate_curve(model_family=model_family, output_path=output)
        if result:
            console.print(f"[green]Chart saved to {result}[/green]")
        else:
            console.print("[yellow]No data available for chart generation.[/yellow]")
