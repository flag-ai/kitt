"""kitt results - Results management commands."""

import json
import subprocess
from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.group()
def results():
    """Manage benchmark results."""


@results.command("init")
@click.option("--path", "-p", type=click.Path(), help="Path for KARR repo")
def init_results(path):
    """Initialize a new KARR results repository."""
    from kitt.git_ops.repo_manager import KARRRepoManager
    from kitt.hardware.fingerprint import HardwareFingerprint

    fingerprint = HardwareFingerprint.generate()

    repo_path = Path(path) if path else Path.cwd() / f"karr-{fingerprint[:40]}"

    if repo_path.exists():
        console.print(f"[yellow]Directory already exists: {repo_path}[/yellow]")
        return

    console.print(f"[cyan]Creating KARR repository at {repo_path}...[/cyan]")
    KARRRepoManager.create_results_repo(repo_path, fingerprint)
    console.print("[green]KARR repository created![/green]")
    console.print(f"  Path: {repo_path}")
    console.print(f"  Fingerprint: {fingerprint}")


@results.command("submit")
@click.option("--repo", type=click.Path(), help="Results repository path")
def submit_results(repo):
    """Submit results via pull request."""
    from kitt.git_ops.pr_creator import PRCreator

    if not PRCreator.check_git_config():
        console.print("[red]Git not configured[/red]")
        console.print("\nConfigure Git with:")
        console.print("  git config --global user.name 'Your Name'")
        console.print("  git config --global user.email 'your.email@example.com'")
        return

    console.print("[cyan]Submitting results...[/cyan]")
    console.print(
        "[yellow]PR submission not yet connected to remote. "
        "Commit your changes and push manually.[/yellow]"
    )


@results.command("list")
@click.option("--model", help="Filter by model")
@click.option("--engine", help="Filter by engine")
@click.option("--karr", type=click.Path(), help="Path to KARR repo")
def list_results(model, engine, karr):
    """List local benchmark results."""
    from rich.table import Table

    table = Table(title="Local Results")
    table.add_column("Model")
    table.add_column("Engine")
    table.add_column("Timestamp")
    table.add_column("Status")
    table.add_column("Source")

    found = 0

    # Search kitt-results/ directory
    results_dirs = list(Path(".").glob("kitt-results/**/metrics.json"))
    for metrics_path in sorted(results_dirs):
        row = _parse_metrics(metrics_path, model, engine)
        if row:
            table.add_row(*row, "local")
            found += 1

    # Search KARR repos
    karr_paths = [Path(karr)] if karr else list(Path(".").glob("karr-*"))
    for karr_path in karr_paths:
        if not karr_path.is_dir():
            continue
        from kitt.git_ops.repo_manager import KARRRepoManager

        for entry in KARRRepoManager.list_results(karr_path):
            if model and model not in entry["model"]:
                continue
            if engine and engine != entry["engine"]:
                continue

            status = "[dim]no metrics[/dim]"
            if entry["has_metrics"]:
                try:
                    with open(entry["path"] / "metrics.json") as f:
                        data = json.load(f)
                    passed = data.get("passed", False)
                    status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
                except Exception:
                    status = "[yellow]?[/yellow]"

            table.add_row(
                entry["model"],
                entry["engine"],
                entry["timestamp"],
                status,
                f"karr:{karr_path.name}",
            )
            found += 1

    if found == 0:
        console.print("[yellow]No results found in current directory[/yellow]")
        console.print("Hint: Run benchmarks with 'kitt run' or look in a KARR repo.")
        return

    console.print(table)


@results.command("compare")
@click.argument("run1")
@click.argument("run2")
@click.option("--additional", multiple=True, help="Additional runs to compare")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
def compare_results(run1, run2, additional, fmt):
    """Compare benchmark results from different runs."""
    runs = [run1, run2] + list(additional)
    console.print(f"[cyan]Comparing {len(runs)} result set(s)...[/cyan]")

    result_data = []
    run_labels = []
    for run_path in runs:
        path = Path(run_path)
        metrics_file = path / "metrics.json" if path.is_dir() else path
        if not metrics_file.exists():
            console.print(f"[red]Not found: {metrics_file}[/red]")
            continue
        with open(metrics_file) as f:
            data = json.load(f)
        result_data.append(data)
        run_labels.append(path.name if path.is_dir() else path.stem)

    if len(result_data) < 2:
        console.print("[red]Need at least 2 valid result sets to compare[/red]")
        raise SystemExit(1)

    from kitt.reporters.comparison import compare_metrics

    comparison = compare_metrics(result_data)

    if fmt == "json":
        console.print_json(json.dumps(comparison, indent=2))
        return

    from rich.table import Table

    table = Table(title="Metrics Comparison")
    table.add_column("Metric", style="cyan")
    table.add_column("Min")
    table.add_column("Max")
    table.add_column("Avg")
    table.add_column("Std Dev")
    table.add_column("CV%")

    for metric, stats in comparison.items():
        std_dev = f"{stats.get('std_dev', 0):.4f}" if "std_dev" in stats else "-"
        cv = f"{stats.get('cv_percent', 0):.1f}%" if "cv_percent" in stats else "-"
        table.add_row(
            metric,
            f"{stats['min']:.4f}",
            f"{stats['max']:.4f}",
            f"{stats['avg']:.4f}",
            std_dev,
            cv,
        )

    console.print(table)


@results.command("import")
@click.argument("source", type=click.Path(exists=True))
@click.option("--karr", type=click.Path(), help="KARR repo to import into")
def import_results(source, karr):
    """Import results from a directory into a KARR repo."""
    from kitt.git_ops.repo_manager import KARRRepoManager
    from kitt.hardware.fingerprint import HardwareFingerprint

    source_path = Path(source)
    metrics_file = source_path / "metrics.json"
    if not metrics_file.exists():
        console.print(f"[red]No metrics.json found in {source_path}[/red]")
        raise SystemExit(1)

    with open(metrics_file) as f:
        data = json.load(f)

    model_name = data.get("model", "unknown")
    engine_name = data.get("engine", "unknown")
    timestamp = data.get("timestamp", "unknown")[:19].replace(":", "")

    # Find or create KARR repo
    if karr:
        karr_path = Path(karr)
    else:
        fingerprint = HardwareFingerprint.generate()
        karr_path = KARRRepoManager.find_results_repo(fingerprint)
        if not karr_path:
            karr_path = Path.cwd() / f"karr-{fingerprint[:40]}"
            KARRRepoManager.create_results_repo(karr_path, fingerprint)

    # Collect files
    files = {}
    for file_path in source_path.rglob("*"):
        if file_path.is_file():
            rel_path = str(file_path.relative_to(source_path))
            if file_path.suffix in (".gz", ".bin"):
                files[rel_path] = file_path.read_bytes()
            else:
                files[rel_path] = file_path.read_text()

    KARRRepoManager.store_results(karr_path, model_name, engine_name, timestamp, files)
    console.print(f"[green]Results imported into {karr_path}[/green]")


@results.command("cleanup")
@click.option("--repo", type=click.Path(), help="Results repository path")
@click.option("--days", default=90, help="Keep objects from last N days")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted")
def cleanup_lfs(repo, days, dry_run):
    """Clean up old Git LFS objects to reduce repository size."""
    repo_path = Path(repo) if repo else Path.cwd()

    console.print(f"[cyan]Cleaning up LFS objects in {repo_path}[/cyan]")
    console.print(f"[yellow]Keeping objects from last {days} days[/yellow]")

    if dry_run:
        console.print("[bold yellow]DRY RUN - No changes will be made[/bold yellow]\n")

    try:
        result = subprocess.run(
            [
                "git",
                "lfs",
                "prune",
                "--dry-run",
                "--verbose",
                "--verify-remote",
                "--recent",
                f"--days={days}",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        console.print(result.stdout)

        if not dry_run and result.returncode == 0:  # noqa: SIM102
            if click.confirm("Proceed with cleanup?"):
                subprocess.run(
                    [
                        "git",
                        "lfs",
                        "prune",
                        "--verbose",
                        "--verify-remote",
                        "--recent",
                        f"--days={days}",
                    ],
                    cwd=repo_path,
                    check=True,
                )
                console.print("[green]Cleanup complete[/green]")

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error during cleanup: {e}[/red]")
    except FileNotFoundError:
        console.print(
            "[red]Git LFS not found. Install from: https://git-lfs.github.com[/red]"
        )


def _parse_metrics(metrics_path, model_filter, engine_filter):
    """Parse a metrics.json and return a table row or None."""
    try:
        with open(metrics_path) as f:
            data = json.load(f)
        m = data.get("model", "unknown")
        e = data.get("engine", "unknown")
        ts = data.get("timestamp", "unknown")

        if model_filter and model_filter not in m:
            return None
        if engine_filter and engine_filter != e:
            return None

        passed = data.get("passed", False)
        status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        return (m, e, ts[:19], status)
    except Exception:
        return None
