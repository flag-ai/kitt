"""kitt test - Benchmark management commands."""

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def test():
    """Manage benchmarks and test definitions."""


@test.command("list")
@click.option("--category", "-c", help="Filter by category")
def list_tests(category):
    """List available benchmarks."""
    from pathlib import Path

    from kitt.benchmarks.loader import BenchmarkLoader
    from kitt.benchmarks.registry import BenchmarkRegistry

    # Auto-discover built-in benchmarks
    BenchmarkRegistry.auto_discover()

    table = Table(title="Available Benchmarks")
    table.add_column("Name", style="cyan")
    table.add_column("Category")
    table.add_column("Version")
    table.add_column("Source")

    # Built-in benchmarks
    for name in sorted(BenchmarkRegistry.list_all()):
        bench_cls = BenchmarkRegistry.get_benchmark(name)
        if category and bench_cls.category != category:
            continue
        table.add_row(name, bench_cls.category, bench_cls.version, "built-in")

    # YAML-defined benchmarks from configs/
    config_dirs = [
        Path("configs/tests"),
        Path(__file__).parent.parent.parent.parent / "configs" / "tests",
    ]

    seen_yaml = set()
    for config_dir in config_dirs:
        config_dir = config_dir.resolve()
        if config_dir.exists():
            yaml_benchmarks = BenchmarkLoader.discover_benchmarks(config_dir)
            for bench in yaml_benchmarks:
                if bench.name in seen_yaml:
                    continue
                seen_yaml.add(bench.name)
                if category and bench.category != category:
                    continue
                if bench.name not in BenchmarkRegistry.list_all():
                    table.add_row(bench.name, bench.category, bench.version, "yaml")

    console.print(table)


@test.command("new")
@click.argument("name")
@click.option("--category", "-c", default="quality_custom", help="Benchmark category")
def new_test(name, category):
    """Create a new benchmark definition from template."""
    from pathlib import Path

    output_dir = Path("configs/tests/quality/custom")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{name}.yaml"
    if output_path.exists():
        console.print(f"[red]Benchmark '{name}' already exists at {output_path}[/red]")
        raise SystemExit(1)

    template = f"""name: {name}
version: "1.0.0"
category: {category}
description: "Custom benchmark: {name}"

warmup:
  enabled: true
  iterations: 5

dataset:
  # Use one of:
  # source: huggingface/dataset-id    # HuggingFace dataset
  # local_path: /path/to/data          # Local directory
  source: null
  local_path: null
  split: test
  sample_size: null

sampling:
  temperature: 0.0
  top_p: 1.0
  max_tokens: 2048

runs: 3
"""
    output_path.write_text(template)
    console.print(f"[green]Created benchmark template: {output_path}[/green]")
    console.print("[cyan]Edit the YAML file to configure your benchmark.[/cyan]")
