"""Remote execution CLI commands."""

import logging

import click
from rich.console import Console
from rich.table import Table

console = Console()
logger = logging.getLogger(__name__)


@click.group()
def remote():
    """Remote host management and execution."""


@remote.command()
@click.argument("host_spec")
@click.option("--name", default=None, help="Friendly name for the host")
@click.option("--ssh-key", default=None, help="Path to SSH key")
@click.option("--no-install", is_flag=True, help="Skip KITT installation")
def setup(host_spec, name, ssh_key, no_install):
    """Set up a remote host for KITT execution.

    HOST_SPEC: user@hostname or hostname
    """
    from kitt.remote.host_config import HostManager
    from kitt.remote.setup import RemoteSetup
    from kitt.remote.ssh_connection import SSHConnection

    # Parse host spec
    if "@" in host_spec:
        user, hostname = host_spec.split("@", 1)
    else:
        user, hostname = None, host_spec

    host_name = name or hostname

    conn = SSHConnection(host=hostname, user=user, ssh_key=ssh_key)
    setup_tool = RemoteSetup(conn)

    console.print(f"[bold]Setting up remote host:[/bold] {host_spec}")

    with console.status("Checking prerequisites..."):
        prereqs = setup_tool.check_prerequisites()

    if not prereqs.get("ssh"):
        console.print("[red]Cannot connect to remote host.[/red]")
        raise SystemExit(1)

    console.print(f"  Python: {prereqs.get('python_version', 'not found')}")
    console.print(f"  Docker: {'yes' if prereqs.get('docker') else 'no'}")
    console.print(f"  GPU: {prereqs.get('gpu_info', 'not detected')}")

    mgr = HostManager()
    result = setup_tool.setup_host(host_name, host_manager=mgr, install=not no_install)

    if result:
        console.print(f"\n[green]Host '{host_name}' configured successfully.[/green]")
    else:
        console.print("[red]Setup failed.[/red]")
        raise SystemExit(1)


@remote.command("list")
def list_hosts():
    """List configured remote hosts."""
    from kitt.remote.host_config import HostManager

    mgr = HostManager()
    hosts = mgr.list_hosts()

    if not hosts:
        console.print("No remote hosts configured.")
        return

    table = Table(title="Remote Hosts")
    table.add_column("Name", style="cyan")
    table.add_column("Host")
    table.add_column("User")
    table.add_column("GPU")
    table.add_column("Python")

    for h in hosts:
        table.add_row(
            h.name,
            h.hostname,
            h.user or "-",
            h.gpu_info or "-",
            h.python_version or "-",
        )

    console.print(table)


@remote.command()
@click.argument("name")
def test(name):
    """Test connectivity to a remote host."""
    from kitt.remote.host_config import HostManager
    from kitt.remote.ssh_connection import SSHConnection

    mgr = HostManager()
    host = mgr.get(name)
    if not host:
        console.print(f"[red]Host not found: {name}[/red]")
        raise SystemExit(1)

    conn = SSHConnection(
        host=host.hostname,
        user=host.user or None,
        ssh_key=host.ssh_key or None,
        port=host.port,
    )

    with console.status("Testing connection..."):
        ok = conn.check_connection()

    if ok:
        console.print(f"[green]Connection to '{name}' successful.[/green]")
    else:
        console.print(f"[red]Cannot connect to '{name}'.[/red]")
        raise SystemExit(1)


@remote.command()
@click.argument("name")
def remove(name):
    """Remove a configured remote host."""
    from kitt.remote.host_config import HostManager

    mgr = HostManager()
    if mgr.remove(name):
        console.print(f"[green]Host '{name}' removed.[/green]")
    else:
        console.print(f"[red]Host not found: {name}[/red]")


@remote.group("engines")
def remote_engines():
    """Manage engine images on remote hosts."""


@remote_engines.command("setup")
@click.argument("engine_name")
@click.option("--host", required=True, help="Remote host name")
@click.option("--dry-run", is_flag=True, help="Show commands without executing them")
def remote_engines_setup(engine_name, host, dry_run):
    """Pull or build an engine image on a remote host.

    ENGINE_NAME: Engine to set up (vllm, llama_cpp, ollama, exllamav2)
    """
    from kitt.remote.host_config import HostManager
    from kitt.remote.setup import RemoteSetup
    from kitt.remote.ssh_connection import SSHConnection

    mgr = HostManager()
    host_config = mgr.get(host)
    if not host_config:
        console.print(f"[red]Host not found: {host}[/red]")
        raise SystemExit(1)

    conn = SSHConnection(
        host=host_config.hostname,
        user=host_config.user or None,
        ssh_key=host_config.ssh_key or None,
        port=host_config.port,
    )

    setup_tool = RemoteSetup(conn)

    action = "Dry run:" if dry_run else "Setting up"
    console.print(f"[bold]{action} engine '{engine_name}' on '{host}'...[/bold]")

    results = setup_tool.setup_engines([engine_name], dry_run=dry_run)

    if results.get(engine_name):
        console.print(f"[green]Engine '{engine_name}' ready on '{host}'.[/green]")
    else:
        console.print(
            f"[red]Engine setup failed for '{engine_name}' on '{host}'.[/red]"
        )
        raise SystemExit(1)


@remote.command("run")
@click.argument("config_path", type=click.Path(exists=True))
@click.option("--host", required=True, help="Remote host name")
@click.option("--dry-run", is_flag=True, help="Dry run mode")
@click.option("--wait", is_flag=True, help="Wait for completion")
def run_remote(config_path, host, dry_run, wait):
    """Run a campaign on a remote host."""
    from kitt.remote.executor import RemoteCampaignExecutor
    from kitt.remote.host_config import HostManager

    mgr = HostManager()
    host_config = mgr.get(host)
    if not host_config:
        console.print(f"[red]Host not found: {host}[/red]")
        raise SystemExit(1)

    executor = RemoteCampaignExecutor(host_config)

    if wait:
        console.print(
            f"[bold]Running campaign on '{host}' (waiting for completion)...[/bold]"
        )
        success = executor.run_and_wait(config_path, dry_run=dry_run)
        if success:
            console.print("[green]Campaign completed.[/green]")
        else:
            console.print("[red]Campaign failed or timed out.[/red]")
            raise SystemExit(1)
    else:
        remote_path = executor.upload_config(config_path)
        if not remote_path:
            console.print("[red]Failed to upload config.[/red]")
            raise SystemExit(1)

        if executor.start_campaign(remote_path, dry_run=dry_run):
            console.print(f"[green]Campaign started on '{host}'.[/green]")
            console.print("Use 'kitt remote status' or 'kitt remote logs' to monitor.")
        else:
            console.print("[red]Failed to start campaign.[/red]")
            raise SystemExit(1)


@remote.command()
@click.option("--host", required=True, help="Remote host name")
def status(host):
    """Check campaign status on a remote host."""
    from kitt.remote.executor import RemoteCampaignExecutor
    from kitt.remote.host_config import HostManager

    mgr = HostManager()
    host_config = mgr.get(host)
    if not host_config:
        console.print(f"[red]Host not found: {host}[/red]")
        raise SystemExit(1)

    executor = RemoteCampaignExecutor(host_config)
    status_str = executor.check_status()
    console.print(f"Campaign status on '{host}': [bold]{status_str}[/bold]")


@remote.command()
@click.option("--host", required=True, help="Remote host name")
@click.option("--tail", default=50, help="Number of log lines")
def logs(host, tail):
    """View campaign logs from a remote host."""
    from kitt.remote.executor import RemoteCampaignExecutor
    from kitt.remote.host_config import HostManager

    mgr = HostManager()
    host_config = mgr.get(host)
    if not host_config:
        console.print(f"[red]Host not found: {host}[/red]")
        raise SystemExit(1)

    executor = RemoteCampaignExecutor(host_config)
    log_output = executor.get_logs(tail=tail)
    console.print(log_output)


@remote.command()
@click.option("--host", required=True, help="Remote host name")
@click.option(
    "--output", "-o", type=click.Path(), default=None, help="Local results directory"
)
def sync(host, output):
    """Sync results from a remote host."""
    from pathlib import Path

    from kitt.remote.host_config import HostManager
    from kitt.remote.result_sync import ResultSync

    mgr = HostManager()
    host_config = mgr.get(host)
    if not host_config:
        console.print(f"[red]Host not found: {host}[/red]")
        raise SystemExit(1)

    local_dir = Path(output) if output else None
    syncer = ResultSync(host_config, local_results_dir=local_dir)

    with console.status("Syncing results..."):
        count = syncer.sync()

    console.print(f"[green]Synced {count} result(s) from '{host}'.[/green]")
