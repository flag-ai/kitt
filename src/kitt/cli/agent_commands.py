"""CLI commands for the KITT agent daemon.

These commands proxy to the thin agent (kitt-agent) binary.
The full agent (src/kitt/agent/) was removed in v1.2.0.
"""

import logging
import os
import signal
import sys
from pathlib import Path

import click
import yaml
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)


def _find_kitt_agent() -> str | None:
    """Locate the kitt-agent binary in the current venv or PATH."""
    # Check the current venv first
    venv_bin = Path(sys.prefix) / "bin" / "kitt-agent"
    if venv_bin.exists():
        return str(venv_bin)
    # Check PATH
    import shutil

    return shutil.which("kitt-agent")


@click.group()
def agent():
    """Manage the KITT agent daemon.

    These commands proxy to the thin agent (kitt-agent).
    Install the agent package first: pip install kitt-agent
    """


@agent.command()
@click.option(
    "--server", required=True, help="KITT server URL (e.g., https://server:8080)"
)
@click.option("--token", default="", help="Bearer token for authentication (optional)")
@click.option("--name", default="", help="Agent name (defaults to hostname)")
@click.option("--port", default=8090, help="Agent listening port")
def init(server, token, name, port):
    """Initialize agent configuration.

    Proxies to: kitt-agent init
    """
    binary = _find_kitt_agent()
    if not binary:
        console.print("[red]kitt-agent not found.[/red]")
        console.print("Install with: pip install kitt-agent")
        raise SystemExit(1)

    args = [binary, "init", "--server", server, "--port", str(port)]
    if token:
        args.extend(["--token", token])
    if name:
        args.extend(["--name", name])

    os.execv(binary, args)


@agent.command()
@click.option("--config", "config_path", type=click.Path(), help="Path to agent.yaml")
@click.option("--insecure", is_flag=True, help="Disable TLS verification")
def start(config_path, insecure):
    """Start the KITT agent daemon.

    Proxies to: kitt-agent start
    """
    binary = _find_kitt_agent()
    if not binary:
        console.print("[red]kitt-agent not found.[/red]")
        console.print("Install with: pip install kitt-agent")
        raise SystemExit(1)

    args = [binary, "start"]
    if config_path:
        args.extend(["--config", config_path])
    if insecure:
        args.append("--insecure")

    os.execv(binary, args)


@agent.command()
def status():
    """Check agent status."""
    config_file = Path.home() / ".kitt" / "agent.yaml"

    if not config_file.exists():
        console.print("[yellow]Agent not configured[/yellow]")
        return

    with open(config_file) as f:
        config = yaml.safe_load(f)

    console.print("[bold]KITT Agent Status[/bold]")
    console.print(f"  Name: {config.get('name', 'unknown')}")
    console.print(f"  Server: {config.get('server_url', 'not set')}")
    console.print(f"  Port: {config.get('port', 8090)}")

    # Try to reach the local agent
    import urllib.request

    port = config.get("port", 8090)
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/status", timeout=2
        ) as resp:
            import json

            data = json.loads(resp.read())
            console.print("  Running: [green]yes[/green]")
            console.print(f"  Active containers: {data.get('active_containers', 0)}")
    except Exception:
        console.print("  Running: [red]no[/red]")


@agent.command()
@click.option("--config", "config_path", type=click.Path(), help="Path to agent.yaml")
@click.option("--restart", is_flag=True, help="Restart the agent after update")
def update(config_path, restart):
    """Update the agent to the latest version from the server.

    Proxies to: kitt-agent update
    """
    binary = _find_kitt_agent()
    if not binary:
        console.print("[red]kitt-agent not found.[/red]")
        console.print("Install with: pip install kitt-agent")
        raise SystemExit(1)

    args = [binary, "update"]
    if config_path:
        args.extend(["--config", config_path])
    if restart:
        args.append("--restart")

    os.execv(binary, args)


@agent.command()
def stop():
    """Stop the KITT agent daemon."""
    pid_file = Path.home() / ".kitt" / "agent.pid"
    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, signal.SIGTERM)
            console.print(f"[green]Agent stopped (PID {pid})[/green]")
            pid_file.unlink()
        except ProcessLookupError:
            console.print("[yellow]Agent process not found[/yellow]")
            pid_file.unlink()
    else:
        console.print("[yellow]No PID file found — agent may not be running[/yellow]")
