"""CLI commands for managing the monitoring stack."""

import logging
import shutil
import subprocess
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)
console = Console()

COMPOSE_DIR = Path(__file__).parent.parent.parent.parent / "docker" / "monitoring"


def _resolve_compose_dir(
    compose_dir: str | None,
    name: str | None,
) -> Path | None:
    """Resolve the compose directory from --compose-dir or --name."""
    if compose_dir:
        return Path(compose_dir)

    if name:
        from kitt.monitoring.config import MonitoringConfigManager

        manager = MonitoringConfigManager()
        config = manager.get(name)
        if config and config.local_dir:
            path = Path(config.local_dir)
            if path.exists():
                return path
        return None

    return _find_compose_dir()


@click.group()
def monitoring():
    """Manage the Grafana/Prometheus monitoring stack."""


@monitoring.command()
@click.option(
    "--compose-dir",
    type=click.Path(exists=True),
    default=None,
    help="Path to docker-compose directory (auto-detected by default).",
)
@click.option(
    "--name",
    default=None,
    help="Name of a generated monitoring stack to start.",
)
def start(compose_dir, name):
    """Start the monitoring stack (Prometheus, Grafana, InfluxDB)."""
    compose_path = _resolve_compose_dir(compose_dir, name)
    if not compose_path:
        console.print("[red]Could not find docker/monitoring/ directory.[/red]")
        console.print(
            "Specify with --compose-dir, --name, or run from the KITT project root."
        )
        raise SystemExit(1)

    console.print("[bold]Starting KITT monitoring stack...[/bold]")
    result = subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=str(compose_path),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        console.print("[red]Failed to start monitoring stack:[/red]")
        console.print(result.stderr)
        raise SystemExit(1)

    console.print("[green]Monitoring stack started:[/green]")
    console.print("  Grafana:    http://localhost:3000  (admin/kitt)")
    console.print("  Prometheus: http://localhost:9090")
    console.print("  InfluxDB:   http://localhost:8086")


@monitoring.command()
@click.option(
    "--compose-dir",
    type=click.Path(exists=True),
    default=None,
    help="Path to docker-compose directory.",
)
@click.option(
    "--name",
    default=None,
    help="Name of a generated monitoring stack to stop.",
)
def stop(compose_dir, name):
    """Stop the monitoring stack."""
    compose_path = _resolve_compose_dir(compose_dir, name)
    if not compose_path:
        console.print("[red]Could not find docker/monitoring/ directory.[/red]")
        raise SystemExit(1)

    console.print("[bold]Stopping KITT monitoring stack...[/bold]")
    result = subprocess.run(
        ["docker", "compose", "down"],
        cwd=str(compose_path),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        console.print("[red]Failed to stop monitoring stack:[/red]")
        console.print(result.stderr)
        raise SystemExit(1)

    console.print("[green]Monitoring stack stopped.[/green]")


@monitoring.command()
@click.option(
    "--compose-dir",
    type=click.Path(exists=True),
    default=None,
    help="Path to docker-compose directory.",
)
@click.option(
    "--name",
    default=None,
    help="Name of a generated monitoring stack to check.",
)
def status(compose_dir, name):
    """Show monitoring stack status."""
    compose_path = _resolve_compose_dir(compose_dir, name)
    if not compose_path:
        console.print("[red]Could not find docker/monitoring/ directory.[/red]")
        raise SystemExit(1)

    result = subprocess.run(
        ["docker", "compose", "ps", "--format", "table"],
        cwd=str(compose_path),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        console.print("[yellow]Monitoring stack is not running.[/yellow]")
        return

    if result.stdout.strip():
        console.print("[bold]Monitoring Stack Status:[/bold]")
        console.print(result.stdout)
    else:
        console.print("[yellow]No monitoring containers running.[/yellow]")


@monitoring.command()
@click.argument("name")
@click.option(
    "-t",
    "--target",
    multiple=True,
    required=True,
    help="Scrape target host:port (repeatable).",
)
@click.option("--grafana-port", default=3000, help="Grafana port (default: 3000).")
@click.option(
    "--prometheus-port", default=9090, help="Prometheus port (default: 9090)."
)
@click.option("--influxdb-port", default=8086, help="InfluxDB port (default: 8086).")
@click.option("--grafana-password", default="kitt", help="Grafana admin password.")
@click.option(
    "--influxdb-token", default="kitt-influx-token", help="InfluxDB admin token."
)
@click.option("--deploy", is_flag=True, help="Deploy to remote host after generation.")
@click.option(
    "--host", default=None, help="Remote host name (from ~/.kitt/hosts.yaml)."
)
def generate(
    name,
    target,
    grafana_port,
    prometheus_port,
    influxdb_port,
    grafana_password,
    influxdb_token,
    deploy,
    host,
):
    """Generate a customized monitoring stack.

    Creates a docker-compose stack at ~/.kitt/monitoring/<NAME>/ with
    Prometheus, Grafana, and InfluxDB configured for the given scrape targets.
    """
    from kitt.monitoring.generator import MonitoringStackGenerator

    generator = MonitoringStackGenerator(
        name=name,
        scrape_targets=list(target),
        grafana_port=grafana_port,
        prometheus_port=prometheus_port,
        influxdb_port=influxdb_port,
        grafana_password=grafana_password,
        influxdb_token=influxdb_token,
    )

    console.print(f"[bold]Generating monitoring stack '{name}'...[/bold]")
    stack_dir = generator.generate()
    console.print(f"[green]Stack generated at {stack_dir}[/green]")
    console.print(f"  Scrape targets: {', '.join(target)}")
    console.print(f"  Grafana port:    {grafana_port}")
    console.print(f"  Prometheus port: {prometheus_port}")
    console.print(f"  InfluxDB port:   {influxdb_port}")

    if deploy:
        if not host:
            console.print("[red]--host is required with --deploy[/red]")
            raise SystemExit(1)
        _do_deploy(name, host)


@monitoring.command()
@click.argument("name")
@click.option(
    "--host", required=True, help="Remote host name (from ~/.kitt/hosts.yaml)."
)
def deploy(name, host):
    """Deploy a generated monitoring stack to a remote host."""
    _do_deploy(name, host)


@monitoring.command("remote-start")
@click.argument("name")
@click.option(
    "--host", required=True, help="Remote host name (from ~/.kitt/hosts.yaml)."
)
def remote_start(name, host):
    """Start a deployed monitoring stack on a remote host."""
    deployer, stack_config = _get_deployer_and_config(name, host)
    if not deployer or not stack_config:
        return

    console.print(f"[bold]Starting stack '{name}' on {host}...[/bold]")
    rc, stdout, stderr = deployer.start(stack_config.remote_dir)
    if rc != 0:
        console.print(f"[red]Failed to start:[/red] {stderr}")
        raise SystemExit(1)
    console.print("[green]Stack started.[/green]")
    if stdout.strip():
        console.print(stdout)


@monitoring.command("remote-stop")
@click.argument("name")
@click.option(
    "--host", required=True, help="Remote host name (from ~/.kitt/hosts.yaml)."
)
def remote_stop(name, host):
    """Stop a deployed monitoring stack on a remote host."""
    deployer, stack_config = _get_deployer_and_config(name, host)
    if not deployer or not stack_config:
        return

    console.print(f"[bold]Stopping stack '{name}' on {host}...[/bold]")
    rc, stdout, stderr = deployer.stop(stack_config.remote_dir)
    if rc != 0:
        console.print(f"[red]Failed to stop:[/red] {stderr}")
        raise SystemExit(1)
    console.print("[green]Stack stopped.[/green]")


@monitoring.command("remote-status")
@click.argument("name")
@click.option(
    "--host", required=True, help="Remote host name (from ~/.kitt/hosts.yaml)."
)
def remote_status(name, host):
    """Check status of a deployed monitoring stack on a remote host."""
    deployer, stack_config = _get_deployer_and_config(name, host)
    if not deployer or not stack_config:
        return

    rc, stdout, stderr = deployer.status(stack_config.remote_dir)
    if rc != 0:
        console.print("[yellow]Stack is not running or unreachable.[/yellow]")
        if stderr.strip():
            console.print(stderr)
        return

    if stdout.strip():
        console.print(f"[bold]Stack '{name}' on {host}:[/bold]")
        console.print(stdout)
    else:
        console.print("[yellow]No containers running.[/yellow]")


@monitoring.command("list-stacks")
def list_stacks():
    """List all generated monitoring stacks."""
    from kitt.monitoring.config import MonitoringConfigManager

    manager = MonitoringConfigManager()
    stacks = manager.list_stacks()

    if not stacks:
        console.print("[yellow]No monitoring stacks configured.[/yellow]")
        return

    table = Table(title="Monitoring Stacks")
    table.add_column("Name", style="bold")
    table.add_column("Targets")
    table.add_column("Ports (G/P/I)")
    table.add_column("Deployed To")
    table.add_column("Local Dir")

    for s in stacks:
        table.add_row(
            s.name,
            ", ".join(s.scrape_targets) if s.scrape_targets else "-",
            f"{s.grafana_port}/{s.prometheus_port}/{s.influxdb_port}",
            s.deployed_to or "-",
            s.local_dir or "-",
        )

    console.print(table)


@monitoring.command("remove-stack")
@click.argument("name")
@click.option(
    "--delete-files", is_flag=True, help="Also delete generated files on disk."
)
def remove_stack(name, delete_files):
    """Remove a monitoring stack configuration."""
    from kitt.monitoring.config import MonitoringConfigManager

    manager = MonitoringConfigManager()
    config = manager.get(name)

    if not config:
        console.print(f"[red]Stack '{name}' not found.[/red]")
        raise SystemExit(1)

    if delete_files and config.local_dir:
        local_path = Path(config.local_dir)
        if local_path.exists():
            shutil.rmtree(local_path)
            console.print(f"Deleted {local_path}")

    manager.remove(name)
    console.print(f"[green]Stack '{name}' removed.[/green]")


# --- Internal helpers ---


def _find_compose_dir() -> Path | None:
    """Find the docker/monitoring directory relative to the project."""
    # Try relative to this file (installed package)
    if COMPOSE_DIR.exists():
        return COMPOSE_DIR

    # Try current working directory
    cwd_path = Path.cwd() / "docker" / "monitoring"
    if cwd_path.exists():
        return cwd_path

    return None


def _do_deploy(name: str, host: str) -> None:
    """Shared deploy logic for generate --deploy and deploy command."""
    from kitt.monitoring.config import MonitoringConfigManager
    from kitt.monitoring.deployer import MonitoringDeployer
    from kitt.remote.host_config import HostManager

    host_manager = HostManager()
    host_config = host_manager.get(host)
    if not host_config:
        console.print(f"[red]Host '{host}' not found in ~/.kitt/hosts.yaml[/red]")
        raise SystemExit(1)

    config_manager = MonitoringConfigManager()
    stack_config = config_manager.get(name)
    if not stack_config:
        console.print(f"[red]Stack '{name}' not found. Generate it first.[/red]")
        raise SystemExit(1)

    deployer = MonitoringDeployer(host_config, config_manager)
    console.print(f"[bold]Deploying '{name}' to {host}...[/bold]")

    if deployer.deploy(stack_config):
        console.print(f"[green]Stack '{name}' deployed to {host}.[/green]")
    else:
        console.print("[red]Deployment failed.[/red]")
        raise SystemExit(1)


def _get_deployer_and_config(name, host):
    """Load deployer and stack config for remote commands."""
    from kitt.monitoring.config import MonitoringConfigManager
    from kitt.monitoring.deployer import MonitoringDeployer
    from kitt.remote.host_config import HostManager

    host_manager = HostManager()
    host_config = host_manager.get(host)
    if not host_config:
        console.print(f"[red]Host '{host}' not found in ~/.kitt/hosts.yaml[/red]")
        raise SystemExit(1)

    config_manager = MonitoringConfigManager()
    stack_config = config_manager.get(name)
    if not stack_config:
        console.print(f"[red]Stack '{name}' not found.[/red]")
        raise SystemExit(1)

    if not stack_config.remote_dir:
        console.print(
            f"[red]Stack '{name}' has not been deployed. Deploy it first.[/red]"
        )
        raise SystemExit(1)

    deployer = MonitoringDeployer(host_config, config_manager)
    return deployer, stack_config
