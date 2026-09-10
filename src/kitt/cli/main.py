"""KITT CLI - Main entry point."""

import click
from rich.console import Console

from kitt import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="KITT")
def cli():
    """KITT - Kirizan's Inference Testing Tools

    End-to-end testing suite for LLM inference engines.
    """


from .agent_commands import agent  # noqa: E402
from .bot_commands import bot  # noqa: E402
from .campaign_commands import campaign  # noqa: E402
from .charts_commands import charts  # noqa: E402
from .ci_commands import ci  # noqa: E402
from .engine_commands import engines  # noqa: E402
from .monitoring_commands import monitoring  # noqa: E402
from .plugin_commands import plugin  # noqa: E402
from .recommend_commands import recommend  # noqa: E402
from .remote_commands import remote  # noqa: E402
from .results_commands import results  # noqa: E402
from .run import run  # noqa: E402
from .stack_commands import stack  # noqa: E402
from .storage_commands import storage  # noqa: E402
from .test_commands import test  # noqa: E402

cli.add_command(run)
cli.add_command(test)
cli.add_command(engines)
cli.add_command(results)
cli.add_command(campaign)
cli.add_command(monitoring)
cli.add_command(storage)
cli.add_command(plugin)
cli.add_command(ci)
cli.add_command(bot)
cli.add_command(remote)
cli.add_command(recommend)
cli.add_command(charts)
cli.add_command(agent)
cli.add_command(stack)


@cli.command()
@click.option("--verbose", is_flag=True, help="Show detailed hardware info")
def fingerprint(verbose):
    """Display hardware fingerprint for this system."""
    from kitt.hardware.fingerprint import HardwareFingerprint

    if verbose:
        info = HardwareFingerprint.detect_system()
        console.print()
        console.print("[bold]System Information[/bold]")
        console.print(f"  Environment: {info.environment_type}")
        console.print(f"  OS: {info.os}")
        console.print(f"  Kernel: {info.kernel}")
        if info.gpu:
            if info.gpu.vram_gb > 0:
                gpu_str = f"{info.gpu.model} ({info.gpu.vram_gb}GB)"
            else:
                gpu_str = f"{info.gpu.model} (unified memory, {info.ram_gb}GB shared)"
            if info.gpu.count > 1:
                gpu_str += f" x{info.gpu.count}"
            console.print(f"  GPU: {gpu_str}")
        elif info.environment_type in ("dgx_spark", "dgx"):
            console.print(
                "  GPU: [red]Not detected[/red] "
                "(expected on this system — check NVIDIA drivers and permissions)"
            )
        else:
            console.print("  GPU: [yellow]None detected[/yellow]")
        console.print(
            f"  CPU: {info.cpu.model} ({info.cpu.cores}c/{info.cpu.threads}t)"
        )
        console.print(f"  RAM: {info.ram_gb}GB {info.ram_type}")
        console.print(
            f"  Storage: {info.storage.brand} {info.storage.model} ({info.storage.type})"
        )
        if info.cuda_version:
            console.print(f"  CUDA: {info.cuda_version}")
        if info.driver_version:
            console.print(f"  Driver: {info.driver_version}")

    fp = HardwareFingerprint.generate()
    console.print(f"\n[bold green]Hardware Fingerprint:[/bold green] {fp}")


@cli.command()
@click.argument("runs", nargs=-1, required=True)
def compare(runs):
    """Launch TUI for comparing benchmark results.

    Pass paths to result directories or metrics.json files.

    Example: kitt compare ./result-1 ./result-2
    """
    from kitt.cli.compare_tui import check_textual_available, launch_comparison_tui

    if not check_textual_available():
        console.print("[red]Textual is not installed.[/red]")
        console.print("Install with: pip install kitt[cli_ui]")
        raise SystemExit(1)

    launch_comparison_tui(list(runs))


@cli.command()
@click.option("--port", default=8080, help="Port for web UI")
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--results-dir", type=click.Path(exists=True), help="Results directory")
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.option("--legacy", is_flag=True, help="Use legacy read-only dashboard")
@click.option("--insecure", is_flag=True, help="Disable TLS (development only)")
@click.option("--tls-cert", type=click.Path(), help="Path to TLS certificate")
@click.option("--tls-key", type=click.Path(), help="Path to TLS private key")
@click.option("--tls-ca", type=click.Path(), help="Path to CA certificate")
@click.option("--auth-token", help="Bearer token for API auth")
def web(
    port,
    host,
    results_dir,
    debug,
    legacy,
    insecure,
    tls_cert,
    tls_key,
    tls_ca,
    auth_token,
):
    """Launch web dashboard for viewing results."""
    try:
        from kitt.web.app import create_app
    except ImportError:
        console.print("[red]Flask is not installed.[/red]")
        console.print("Install with: pip install kitt[web]")
        raise SystemExit(1) from None

    app = create_app(
        results_dir=results_dir,
        insecure=insecure,
        legacy=legacy,
        auth_token=auth_token,
    )

    ssl_ctx = None
    scheme = "http"

    if not insecure and not legacy:
        try:
            from kitt.security.cert_manager import (
                ensure_server_certs,
                get_ca_fingerprint,
            )

            if tls_cert and tls_key:
                ssl_ctx = (tls_cert, tls_key)
                scheme = "https"
            else:
                ca_path, cert_path, key_path = ensure_server_certs()
                ssl_ctx = (str(cert_path), str(key_path))
                scheme = "https"
                fingerprint = get_ca_fingerprint(ca_path)
                console.print(f"  CA Fingerprint: [dim]{fingerprint}[/dim]")
        except ImportError:
            console.print(
                "[yellow]cryptography not installed — running without TLS[/yellow]"
            )
            console.print("Install with: pip install 'kitt[web]'")

    console.print("[bold]KITT Web Dashboard[/bold]")
    console.print(f"  URL: {scheme}://{host}:{port}")
    console.print(f"  Results: {results_dir or 'current directory'}")
    if legacy:
        console.print("  Mode: legacy (read-only)")
    if insecure:
        console.print("  [yellow]WARNING: Running without TLS (--insecure)[/yellow]")
    console.print()

    app.run(host=host, port=port, debug=debug, ssl_context=ssl_ctx)


if __name__ == "__main__":
    cli()
