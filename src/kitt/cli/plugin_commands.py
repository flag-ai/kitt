"""Plugin management CLI commands."""

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def plugin():
    """Manage KITT plugins."""


@plugin.command()
@click.argument("package")
@click.option("--version", default=None, help="Version constraint (e.g. '>=0.2.0')")
@click.option("--upgrade", is_flag=True, help="Upgrade if already installed")
def install(package, version, upgrade):
    """Install a KITT plugin package."""
    from kitt.plugins.installer import install_plugin

    if install_plugin(package, version=version, upgrade=upgrade):
        console.print(f"[green]Installed {package}[/green]")

        # Show what was discovered
        from kitt.plugins.discovery import discover_plugins

        plugins = discover_plugins()
        for group, items in plugins.items():
            if items:
                console.print(f"  Discovered {len(items)} {group}")
    else:
        console.print(f"[red]Failed to install {package}[/red]")
        raise SystemExit(1)


@plugin.command("list")
def list_plugins():
    """List installed KITT plugins."""
    from kitt.plugins.installer import list_installed_plugins

    installed = list_installed_plugins()

    if not installed:
        console.print("No KITT plugins installed.")
        console.print("Install with: kitt plugin install <package>")
        return

    table = Table(title="Installed Plugins")
    table.add_column("Name", style="cyan")
    table.add_column("Version")

    for p in installed:
        table.add_row(p["name"], p["version"])

    console.print(table)

    # Also show entry-point discovered plugins
    from kitt.plugins.discovery import discover_plugins

    plugins = discover_plugins()
    total = sum(len(v) for v in plugins.values())
    if total:
        console.print(f"\nDiscovered {total} plugin class(es) via entry points:")
        for group, items in plugins.items():
            for item in items:
                name = getattr(item, "name", None) or getattr(item, "__name__", "?")
                console.print(f"  [{group}] {name}")


@plugin.command()
@click.argument("package")
def remove(package):
    """Remove a KITT plugin package."""
    from kitt.plugins.installer import uninstall_plugin

    if uninstall_plugin(package):
        console.print(f"[green]Removed {package}[/green]")
    else:
        console.print(f"[red]Failed to remove {package}[/red]")
        raise SystemExit(1)
