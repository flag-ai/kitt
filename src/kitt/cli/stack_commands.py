"""CLI commands for composable Docker stack generation."""

import shutil
import subprocess
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def stack():
    """Generate and manage composable Docker deployment stacks."""


@stack.command()
@click.argument("name")
@click.option("--web", is_flag=True, help="Include web UI + REST API service.")
@click.option(
    "--reporting", is_flag=True, help="Include lightweight read-only dashboard."
)
@click.option("--agent", is_flag=True, help="Include agent daemon for GPU servers.")
@click.option("--postgres", is_flag=True, help="Include PostgreSQL database.")
@click.option(
    "--monitoring", is_flag=True, help="Include Prometheus + Grafana + InfluxDB."
)
@click.option(
    "--port", "web_port", default=8080, help="Web/reporting port (default: 8080)."
)
@click.option("--agent-port", default=8090, help="Agent port (default: 8090).")
@click.option("--postgres-port", default=5432, help="PostgreSQL port (default: 5432).")
@click.option("--grafana-port", default=3000, help="Grafana port (default: 3000).")
@click.option(
    "--prometheus-port", default=9090, help="Prometheus port (default: 9090)."
)
@click.option("--influxdb-port", default=8086, help="InfluxDB port (default: 8086).")
@click.option("--auth-token", default="changeme", help="Bearer token for API auth.")
@click.option("--secret-key", default="", help="Flask secret key.")
@click.option(
    "--postgres-password", default="kitt", help="PostgreSQL password (default: kitt)."
)
@click.option(
    "--server-url", default="", help="KITT server URL (for agent registration)."
)
def generate(
    name,
    web,
    reporting,
    agent,
    postgres,
    monitoring,
    web_port,
    agent_port,
    postgres_port,
    grafana_port,
    prometheus_port,
    influxdb_port,
    auth_token,
    secret_key,
    postgres_password,
    server_url,
):
    """Generate a composable Docker deployment stack.

    Creates a docker-compose stack at ~/.kitt/stacks/<NAME>/ with the
    selected components.
    """
    # Validate mutual exclusivity
    if web and reporting:
        console.print("[red]--web and --reporting are mutually exclusive.[/red]")
        raise SystemExit(1)

    # At least one component required
    if not any([web, reporting, agent, postgres, monitoring]):
        console.print("[red]At least one component flag is required.[/red]")
        console.print("Use --web, --reporting, --agent, --postgres, or --monitoring.")
        raise SystemExit(1)

    from kitt.stack.config import StackConfig
    from kitt.stack.generator import StackGenerator

    config = StackConfig(
        name=name,
        web=web,
        reporting=reporting,
        agent=agent,
        postgres=postgres,
        monitoring=monitoring,
        web_port=web_port,
        agent_port=agent_port,
        postgres_port=postgres_port,
        grafana_port=grafana_port,
        prometheus_port=prometheus_port,
        influxdb_port=influxdb_port,
        auth_token=auth_token,
        secret_key=secret_key,
        postgres_password=postgres_password,
        server_url=server_url,
    )

    generator = StackGenerator(config)

    console.print(f"[bold]Generating stack '{name}'...[/bold]")
    stack_dir = generator.generate()
    console.print(f"[green]Stack generated at {stack_dir}[/green]")

    # Print component summary
    components = []
    if web:
        components.append(f"web (:{web_port})")
    if reporting:
        components.append(f"reporting (:{web_port})")
    if agent:
        components.append(f"agent (:{agent_port})")
    if postgres:
        components.append(f"postgres (:{postgres_port})")
    if monitoring:
        components.append(
            f"monitoring (grafana:{grafana_port}, "
            f"prometheus:{prometheus_port}, influxdb:{influxdb_port})"
        )
    console.print(f"  Components: {', '.join(components)}")


@stack.command()
@click.option("--name", required=True, help="Name of the stack to start.")
def start(name):
    """Start a generated stack."""
    stack_dir = _resolve_stack_dir(name)
    if not stack_dir:
        return

    result = subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=str(stack_dir),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        console.print(f"[red]Failed to start stack '{name}':[/red]")
        if result.stderr:
            console.print(result.stderr)
        raise SystemExit(1)

    console.print(f"[green]Stack '{name}' started.[/green]")

    # Print access URLs
    from kitt.stack.config import StackConfigManager

    config = StackConfigManager().get(name)
    if config:
        if config.web:
            console.print(f"  Web UI: https://localhost:{config.web_port}")
        if config.reporting:
            console.print(f"  Dashboard: http://localhost:{config.web_port}")
        if config.monitoring:
            console.print(f"  Grafana: http://localhost:{config.grafana_port}")


@stack.command()
@click.option("--name", required=True, help="Name of the stack to stop.")
def stop(name):
    """Stop a running stack."""
    stack_dir = _resolve_stack_dir(name)
    if not stack_dir:
        return

    result = subprocess.run(
        ["docker", "compose", "down"],
        cwd=str(stack_dir),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        console.print(f"[red]Failed to stop stack '{name}':[/red]")
        if result.stderr:
            console.print(result.stderr)
        raise SystemExit(1)

    console.print(f"[green]Stack '{name}' stopped.[/green]")


@stack.command()
@click.option("--name", required=True, help="Name of the stack to check.")
def status(name):
    """Show stack status."""
    stack_dir = _resolve_stack_dir(name)
    if not stack_dir:
        return

    result = subprocess.run(
        ["docker", "compose", "ps", "--format", "table"],
        cwd=str(stack_dir),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        console.print(f"[yellow]Stack '{name}' is not running.[/yellow]")
        return

    if result.stdout.strip():
        console.print(f"[bold]Stack '{name}' Status:[/bold]")
        console.print(result.stdout)
    else:
        console.print(f"[yellow]No containers running for stack '{name}'.[/yellow]")


@stack.command("list")
def list_stacks():
    """List all generated stacks."""
    from kitt.stack.config import StackConfigManager

    manager = StackConfigManager()
    stacks = manager.list_stacks()

    if not stacks:
        console.print("[yellow]No stacks configured.[/yellow]")
        return

    table = Table(title="Deployment Stacks")
    table.add_column("Name", style="bold")
    table.add_column("Components")
    table.add_column("Ports")
    table.add_column("Local Dir")

    for s in stacks:
        components = []
        ports = []
        if s.web:
            components.append("web")
            ports.append(f"web:{s.web_port}")
        if s.reporting:
            components.append("reporting")
            ports.append(f"report:{s.web_port}")
        if s.agent:
            components.append("agent")
            ports.append(f"agent:{s.agent_port}")
        if s.postgres:
            components.append("postgres")
            ports.append(f"pg:{s.postgres_port}")
        if s.monitoring:
            components.append("monitoring")
            ports.append(f"grafana:{s.grafana_port}")

        table.add_row(
            s.name,
            ", ".join(components) or "-",
            ", ".join(ports) or "-",
            s.local_dir or "-",
        )

    console.print(table)


@stack.command()
@click.argument("name")
@click.option(
    "--delete-files", is_flag=True, help="Also delete generated files on disk."
)
def remove(name, delete_files):
    """Remove a stack configuration."""
    from kitt.stack.config import StackConfigManager

    manager = StackConfigManager()
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


def _resolve_stack_dir(name: str) -> Path | None:
    """Resolve the stack directory from a stack name."""
    from kitt.stack.config import StackConfigManager

    config = StackConfigManager().get(name)
    if not config or not config.local_dir:
        console.print(f"[red]Stack '{name}' not found. Generate it first.[/red]")
        raise SystemExit(1)

    stack_dir = Path(config.local_dir)
    if not stack_dir.exists():
        console.print(f"[red]Stack directory missing: {stack_dir}[/red]")
        raise SystemExit(1)

    return stack_dir
