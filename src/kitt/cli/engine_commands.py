"""kitt engines - Engine management commands."""

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def engines():
    """Manage inference engines."""


@engines.command("list")
def list_engines():
    """List all registered inference engines and their availability."""
    from kitt.engines.image_resolver import is_kitt_managed_image
    from kitt.engines.lifecycle import EngineMode
    from kitt.engines.registry import EngineRegistry

    EngineRegistry.auto_discover()

    table = Table(title="Inference Engines")
    table.add_column("Engine", style="cyan")
    table.add_column("Modes")
    table.add_column("Image")
    table.add_column("Source")
    table.add_column("Status", style="bold")
    table.add_column("Formats")

    for name in sorted(EngineRegistry.list_all()):
        engine_cls = EngineRegistry.get_engine(name)
        modes = engine_cls.supported_modes()
        default_mode = engine_cls.default_mode()

        # Build mode badges
        mode_parts = []
        for m in modes:
            label = m.value
            if m == default_mode:
                label += "*"
            if m == EngineMode.DOCKER:
                mode_parts.append(f"[blue]{label}[/blue]")
            else:
                mode_parts.append(f"[green]{label}[/green]")
        mode_str = " ".join(mode_parts)

        image = engine_cls.resolved_image()
        available = engine_cls.is_available()
        is_build = is_kitt_managed_image(image)
        source = "Build" if is_build else "Registry"

        if EngineMode.DOCKER not in modes:
            image = "-"
            source = "-"

        if available:
            status = "[green]Ready[/green]"
        elif EngineMode.DOCKER not in modes:
            status = "[dim]Native only[/dim]"
        elif is_build:
            status = "[red]Not Built[/red]"
        else:
            status = "[red]Not Pulled[/red]"
        table.add_row(
            name,
            mode_str,
            image,
            source,
            status,
            ", ".join(engine_cls.supported_formats()),
        )

    console.print(table)
    console.print("\n[dim]* = default mode[/dim]")


@engines.command("check")
@click.argument("engine_name")
def check_engine(engine_name):
    """Check if a specific engine is available and show details."""
    from kitt.engines.registry import EngineRegistry

    EngineRegistry.auto_discover()

    try:
        engine_cls = EngineRegistry.get_engine(engine_name)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from e

    diag = engine_cls.diagnose()
    modes = [m.value for m in engine_cls.supported_modes()]
    default = engine_cls.default_mode().value

    console.print(f"[bold]Engine: {engine_name}[/bold]")
    console.print(f"  Image: {diag.image}")
    console.print(f"  Modes: {', '.join(modes)} (default: {default})")
    console.print(f"  Formats: {', '.join(engine_cls.supported_formats())}")

    if diag.available:
        console.print("  Status: [green]Available[/green]")
    else:
        console.print("  Status: [red]Not Available[/red]")
        if diag.error:
            console.print(f"  [yellow]Error: {diag.error}[/yellow]")
        if diag.guidance:
            console.print(f"  [bold]Fix:[/bold] {diag.guidance}")


@engines.command("status")
def engine_status():
    """Show native engine binary detection for the current system."""
    from kitt.engines.lifecycle import EngineMode
    from kitt.engines.process_manager import ProcessManager
    from kitt.engines.registry import EngineRegistry

    EngineRegistry.auto_discover()

    # Map engine names to their expected native binaries
    _NATIVE_BINARIES = {
        "ollama": ["ollama"],
        "llama_cpp": ["llama-server", "llama-cpp-server"],
        "vllm": [],  # Python module, not a binary
    }

    table = Table(title="Native Engine Status")
    table.add_column("Engine", style="cyan")
    table.add_column("Native Support")
    table.add_column("Binary")
    table.add_column("Status", style="bold")

    for name in sorted(EngineRegistry.list_all()):
        engine_cls = EngineRegistry.get_engine(name)
        modes = engine_cls.supported_modes()

        if EngineMode.NATIVE not in modes:
            table.add_row(name, "[dim]No[/dim]", "-", "[dim]Docker only[/dim]")
            continue

        binary_names = _NATIVE_BINARIES.get(name, [])

        if not binary_names:
            # Python-module based (e.g., vLLM)
            if name == "vllm":
                try:
                    import importlib

                    importlib.import_module("vllm")
                    table.add_row(
                        name,
                        "[green]Yes[/green]",
                        "python -m vllm",
                        "[green]Installed[/green]",
                    )
                except ImportError:
                    table.add_row(
                        name,
                        "[green]Yes[/green]",
                        "python -m vllm",
                        "[red]Not installed[/red]",
                    )
            else:
                table.add_row(name, "[green]Yes[/green]", "-", "[dim]Unknown[/dim]")
            continue

        found_binary = None
        for bin_name in binary_names:
            path = ProcessManager.find_binary(bin_name)
            if path:
                found_binary = path
                break

        if found_binary:
            table.add_row(
                name,
                "[green]Yes[/green]",
                found_binary,
                "[green]Found[/green]",
            )
        else:
            table.add_row(
                name,
                "[green]Yes[/green]",
                " / ".join(binary_names),
                "[red]Not found[/red]",
            )

    console.print(table)

    # Show environment info
    try:
        from kitt.hardware.detector import HardwareFingerprint

        env_type = HardwareFingerprint.detect_environment_type()
        console.print(f"\nEnvironment: [bold]{env_type}[/bold]")
    except Exception:
        pass


@engines.command("setup")
@click.argument("engine_name")
@click.option("--dry-run", is_flag=True, help="Show commands without executing them")
@click.option(
    "--force-rebuild", is_flag=True, help="Rebuild even if image already exists"
)
def setup_engine(engine_name, dry_run, force_rebuild):
    """Pull or build the Docker image for an engine."""
    from kitt.engines.docker_manager import DockerManager
    from kitt.engines.image_resolver import get_build_recipe
    from kitt.engines.registry import EngineRegistry

    EngineRegistry.auto_discover()

    try:
        engine_cls = EngineRegistry.get_engine(engine_name)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from e

    image = engine_cls.resolved_image()

    if not DockerManager.is_docker_available():
        console.print("[red]Docker is not installed or not running.[/red]")
        console.print("Install Docker: https://docs.docker.com/get-docker/")
        raise SystemExit(1)

    recipe = get_build_recipe(image)

    if recipe is not None:
        # KITT-managed image — build from Dockerfile
        dockerfile = str(recipe.dockerfile_path)
        context_dir = str(recipe.dockerfile_path.parent)

        if dry_run:
            cmd_parts = ["docker build", f"-f {dockerfile}", f"-t {image}"]
            if recipe.target:
                cmd_parts.append(f"--target {recipe.target}")
            for k, v in recipe.build_args.items():
                cmd_parts.append(f"--build-arg {k}={v}")
            cmd_parts.append(context_dir)
            console.print(f"  [dim]would run:[/dim] {' '.join(cmd_parts)}")
            if recipe.experimental:
                console.print(
                    "  [yellow]WARNING: This is an experimental build.[/yellow]"
                )
            console.print("\n[yellow]Dry run — no commands were executed.[/yellow]")
            return

        if not force_rebuild and DockerManager.image_exists(image):
            console.print(
                f"Image {image} already exists. Use --force-rebuild to rebuild."
            )
            return

        if recipe.experimental:
            console.print(
                f"[yellow]WARNING: {image} is an experimental build.[/yellow]"
            )

        console.print(
            f"Building {image} (this may take 10-60 minutes for CUDA builds)..."
        )
        try:
            DockerManager.build_image(
                image=image,
                dockerfile=dockerfile,
                context_dir=context_dir,
                target=recipe.target,
                build_args=recipe.build_args,
            )
        except RuntimeError as e:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1) from e
    else:
        # Registry image — pull
        if dry_run:
            console.print(f"  [dim]would run:[/dim] docker pull {image}")
            console.print("\n[yellow]Dry run — no commands were executed.[/yellow]")
            return

        console.print(f"Pulling {image}...")
        try:
            DockerManager.pull_image(image)
        except RuntimeError as e:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1) from e

    console.print(f"[green]{engine_name} ready.[/green]")


# ------------------------------------------------------------------
# Profiles subgroup
# ------------------------------------------------------------------


@engines.group("profiles")
def profiles():
    """Manage engine configuration profiles."""


@profiles.command("list")
@click.option("--engine", default=None, help="Filter profiles by engine name")
def list_profiles(engine):
    """List all saved engine profiles."""

    svc, conn = _get_engine_service()
    if svc is None:
        return

    try:
        items = svc.list_profiles(engine=engine)

        if not items:
            console.print("[dim]No profiles found.[/dim]")
            return

        table = Table(title="Engine Profiles")
        table.add_column("Name", style="cyan")
        table.add_column("Engine")
        table.add_column("Mode")
        table.add_column("Description")

        for p in items:
            mode_style = "green" if p["mode"] == "native" else "blue"
            table.add_row(
                p["name"],
                p["engine"],
                f"[{mode_style}]{p['mode']}[/{mode_style}]",
                p.get("description", ""),
            )

        console.print(table)
    finally:
        conn.close()


@profiles.command("show")
@click.argument("name")
def show_profile(name):
    """Show details of a specific engine profile."""
    import json

    svc, conn = _get_engine_service()
    if svc is None:
        return

    try:
        profile = svc.get_profile_by_name(name)
        if profile is None:
            console.print(f"[red]Profile '{name}' not found.[/red]")
            raise SystemExit(1)

        console.print(f"[bold]Profile: {profile['name']}[/bold]")
        console.print(f"  ID: {profile['id']}")
        console.print(f"  Engine: {profile['engine']}")

        mode_style = "green" if profile["mode"] == "native" else "blue"
        console.print(f"  Mode: [{mode_style}]{profile['mode']}[/{mode_style}]")

        if profile.get("description"):
            console.print(f"  Description: {profile['description']}")

        build_cfg = profile.get("build_config", {})
        if build_cfg:
            console.print("\n  [bold]Build Config:[/bold]")
            console.print(f"    {json.dumps(build_cfg, indent=2)}")

        runtime_cfg = profile.get("runtime_config", {})
        if runtime_cfg:
            console.print("\n  [bold]Runtime Config:[/bold]")
            console.print(f"    {json.dumps(runtime_cfg, indent=2)}")

        console.print(f"\n  Created: {profile.get('created_at', '-')}")
        console.print(f"  Updated: {profile.get('updated_at', '-')}")
    finally:
        conn.close()


def _get_engine_service():
    """Get an EngineService instance and its database connection.

    Returns:
        Tuple of (EngineService, sqlite3.Connection), or (None, None) if
        the database doesn't exist.  Callers must close the connection
        when done.
    """
    import sqlite3
    import threading
    from pathlib import Path

    from kitt.web.services.engine_service import EngineService

    db_path = Path.home() / ".kitt" / "kitt.db"
    if not db_path.exists():
        console.print(
            f"[red]Database not found at {db_path}.[/red]\n"
            "Run the web server first to initialize the database."
        )
        return None, None

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return EngineService(conn, threading.Lock()), conn
