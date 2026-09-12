"""CI/CD CLI commands."""

import json
import logging
from pathlib import Path

import click
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)


@click.group()
def ci():
    """CI/CD integration commands."""


@ci.command()
@click.option(
    "--results-dir",
    type=click.Path(exists=True),
    required=True,
    help="Results directory",
)
@click.option(
    "--baseline-dir",
    type=click.Path(exists=True),
    default=None,
    help="Baseline results for comparison",
)
@click.option("--github-token", default=None, help="GitHub API token")
@click.option("--repo", default=None, help="GitHub repo (owner/repo)")
@click.option("--pr", type=int, default=None, help="Pull request number")
@click.option(
    "--output", "-o", default=None, help="Write report to file instead of posting"
)
def report(results_dir, baseline_dir, github_token, repo, pr, output):
    """Generate CI report from benchmark results."""
    from kitt.ci.report_formatter import CIReportFormatter

    # Find latest result
    results_path = Path(results_dir)
    metrics_files = sorted(results_path.glob("**/metrics.json"))
    if not metrics_files:
        console.print("[red]No results found.[/red]")
        raise SystemExit(1)

    latest = json.loads(metrics_files[-1].read_text())

    baseline = None
    if baseline_dir:
        baseline_files = sorted(Path(baseline_dir).glob("**/metrics.json"))
        if baseline_files:
            baseline = json.loads(baseline_files[-1].read_text())

    formatter = CIReportFormatter()
    report_md = formatter.format_summary(latest, baseline=baseline)

    if output:
        Path(output).write_text(report_md)
        console.print(f"Report saved to [green]{output}[/green]")
    elif github_token and repo and pr:
        from kitt.ci.github import GitHubReporter

        reporter = GitHubReporter(token=github_token, repo=repo, pr_number=pr)
        if reporter.update_or_create_comment(report_md):
            console.print("[green]Report posted to PR.[/green]")
        else:
            console.print("[red]Failed to post report.[/red]")
            raise SystemExit(1)
    else:
        console.print(report_md)
