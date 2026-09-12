"""Campaign CLI commands."""

import json
import logging
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()
logger = logging.getLogger(__name__)


@click.group()
def campaign():
    """Manage benchmark campaigns."""


@campaign.command()
@click.argument("config_path", type=click.Path(exists=True))
@click.option("--resume", is_flag=True, help="Resume a previous campaign run")
@click.option("--dry-run", is_flag=True, help="Print planned runs without executing")
@click.option("--campaign-id", default=None, help="Explicit campaign ID (for resume)")
def run(config_path, resume, dry_run, campaign_id):
    """Run a benchmark campaign from a YAML config file."""
    from kitt.campaign.runner import CampaignRunner
    from kitt.config.loader import load_campaign_config

    config = load_campaign_config(Path(config_path))

    console.print(f"[bold]Campaign:[/bold] {config.campaign_name}")
    console.print(f"  Models: {len(config.models)}")
    console.print(f"  Engines: {len(config.engines)}")
    console.print(f"  Dry run: {dry_run}")
    if resume:
        console.print(f"  Resuming: {campaign_id or 'latest'}")
    console.print()

    runner = CampaignRunner(config, dry_run=dry_run)
    result = runner.run(campaign_id=campaign_id, resume=resume)

    # Summary
    console.print()
    console.print("[bold]Campaign Complete[/bold]")
    console.print(f"  Total runs:  {result.total}")
    console.print(f"  Succeeded:   [green]{result.succeeded}[/green]")
    if result.failed > 0:
        console.print(f"  Failed:      [red]{result.failed}[/red]")
    if result.skipped > 0:
        console.print(f"  Skipped:     [yellow]{result.skipped}[/yellow]")
    hours = result.total_duration_s / 3600
    console.print(f"  Duration:    {hours:.1f}h")

    if result.failed > 0:
        console.print()
        console.print("[bold red]Failed Runs:[/bold red]")
        for r in result.runs:
            if r.status == "failed":
                console.print(
                    f"  {r.model_name} / {r.engine_name} / {r.quant}: {r.error[:100]}"
                )


@campaign.command()
@click.argument("campaign_id", required=False)
def status(campaign_id):
    """Show status of a campaign."""
    from kitt.campaign.state_manager import CampaignStateManager

    mgr = CampaignStateManager()

    if campaign_id:
        state = mgr.load(campaign_id)
        if not state:
            console.print(f"[red]Campaign not found: {campaign_id}[/red]")
            raise SystemExit(1)

        console.print(f"[bold]Campaign:[/bold] {state.campaign_name}")
        console.print(f"  ID: {state.campaign_id}")
        console.print(f"  Status: {state.status}")
        console.print(f"  Started: {state.started_at}")
        if state.completed_at:
            console.print(f"  Completed: {state.completed_at}")
        console.print()
        console.print(
            f"  Total: {state.total} | "
            f"[green]Success: {state.succeeded}[/green] | "
            f"[red]Failed: {state.failed}[/red] | "
            f"[yellow]Skipped: {state.skipped}[/yellow] | "
            f"Pending: {state.pending}"
        )

        if state.failed > 0:
            console.print()
            console.print("[bold]Failed runs:[/bold]")
            for r in state.runs:
                if r.status == "failed":
                    console.print(f"  {r.key}: {r.error[:80]}")
    else:
        # Show latest campaign
        campaigns = mgr.list_campaigns()
        if not campaigns:
            console.print("No campaigns found.")
            return
        latest = campaigns[-1]
        console.print(f"Latest: {latest['campaign_name']} ({latest['campaign_id']})")
        console.print(
            f"  Status: {latest['status']} | "
            f"Runs: {latest['total_runs']} | "
            f"Success: {latest['succeeded']} | "
            f"Failed: {latest['failed']}"
        )


@campaign.command("list")
def list_campaigns():
    """List all campaigns."""
    from kitt.campaign.state_manager import CampaignStateManager

    mgr = CampaignStateManager()
    campaigns = mgr.list_campaigns()

    if not campaigns:
        console.print("No campaigns found.")
        return

    table = Table(title="Campaigns")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Total")
    table.add_column("Success", style="green")
    table.add_column("Failed", style="red")
    table.add_column("Started")

    for c in campaigns:
        table.add_row(
            c["campaign_id"],
            c["campaign_name"],
            c["status"],
            str(c["total_runs"]),
            str(c["succeeded"]),
            str(c["failed"]),
            c.get("started_at", "")[:19],
        )

    console.print(table)


@campaign.command("create")
@click.option(
    "--from-results",
    type=click.Path(exists=True),
    required=True,
    help="Generate campaign config from existing results directory",
)
@click.option("--output", "-o", default=None, help="Output YAML path")
def create(from_results, output):
    """Generate a campaign config from existing benchmark results."""
    import yaml

    results_dir = Path(from_results)
    models = {}
    engines = set()

    # Scan metrics.json files
    for metrics_file in results_dir.glob("**/metrics.json"):
        try:
            data = json.loads(metrics_file.read_text())
            model = data.get("model", "unknown")
            engine = data.get("engine", "unknown")

            if model not in models:
                models[model] = {"name": model, "params": ""}
            engines.add(engine)
        except Exception:
            continue

    if not models:
        console.print("[red]No results found in the specified directory.[/red]")
        raise SystemExit(1)

    config_data = {
        "campaign_name": f"replay-{results_dir.name}",
        "description": f"Generated from results in {results_dir}",
        "models": [{"name": m["name"], "params": m["params"]} for m in models.values()],
        "engines": [{"name": e, "suite": "standard"} for e in sorted(engines)],
        "disk": {"reserve_gb": 100.0, "cleanup_after_run": True},
    }

    yaml_str = yaml.dump(config_data, default_flow_style=False, sort_keys=False)

    if output:
        Path(output).write_text(yaml_str)
        console.print(f"Campaign config saved to [green]{output}[/green]")
    else:
        console.print(yaml_str)


@campaign.command("schedule")
@click.argument("config_path", type=click.Path(exists=True))
@click.option("--cron", required=True, help='Cron expression (e.g. "0 2 * * *")')
@click.option("--id", "schedule_id", default=None, help="Schedule identifier")
def schedule(config_path, cron, schedule_id):
    """Schedule a campaign to run on a cron schedule."""
    from kitt.campaign.scheduler_cron import CronScheduler

    scheduler = CronScheduler()
    if scheduler.schedule(config_path, cron, campaign_id=schedule_id):
        console.print(f"[green]Scheduled:[/green] {cron}")
    else:
        console.print("[red]Failed to schedule campaign.[/red]")
        raise SystemExit(1)


@campaign.command("unschedule")
@click.argument("schedule_id")
def unschedule(schedule_id):
    """Remove a scheduled campaign."""
    from kitt.campaign.scheduler_cron import CronScheduler

    scheduler = CronScheduler()
    scheduler.unschedule(schedule_id)
    console.print(f"[green]Unscheduled:[/green] {schedule_id}")


@campaign.command("wizard")
def wizard():
    """Interactive campaign builder wizard."""
    from kitt.tui.campaign_builder import CampaignBuilderApp

    builder = CampaignBuilderApp()

    try:
        config = builder.run_tui()
    except Exception:
        config = builder.run_simple()

    if config:
        yaml_str = builder.to_yaml()
        console.print("\n[bold]Generated Campaign Config:[/bold]\n")
        console.print(yaml_str)

        import click as clk

        save_path = clk.prompt(
            "Save to file? (blank to skip)", default="", show_default=False
        )
        if save_path:
            builder.save(save_path)
            console.print(f"[green]Saved to {save_path}[/green]")


@campaign.command("cron-status")
def cron_status():
    """Show scheduled campaigns."""
    from kitt.campaign.scheduler_cron import CronScheduler

    scheduler = CronScheduler()
    schedules = scheduler.list_scheduled()

    if not schedules:
        console.print("No scheduled campaigns.")
        return

    table = Table(title="Scheduled Campaigns")
    table.add_column("ID", style="cyan")
    table.add_column("Cron")
    table.add_column("Config")
    table.add_column("Enabled")

    for s in schedules:
        table.add_row(
            s.get("schedule_id", ""),
            s.get("cron_expr", ""),
            s.get("campaign_config", ""),
            str(s.get("enabled", True)),
        )

    console.print(table)
