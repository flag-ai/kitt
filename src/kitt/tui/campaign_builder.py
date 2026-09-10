"""Interactive TUI campaign builder using Textual."""

import logging
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class CampaignBuilderApp:
    """Interactive campaign configuration builder.

    Provides a step-by-step wizard for creating campaign YAML configs.
    Falls back to a simple CLI prompt flow if Textual is unavailable.
    """

    def __init__(self) -> None:
        self.config: dict[str, Any] = {
            "campaign_name": "",
            "description": "",
            "models": [],
            "engines": [],
            "disk": {"reserve_gb": 50.0, "cleanup_after_run": True},
        }

    def run_simple(self) -> dict[str, Any]:
        """Run the builder in simple CLI mode (no TUI).

        Returns:
            Campaign config dict.
        """
        import click

        self.config["campaign_name"] = click.prompt(
            "Campaign name", default="my-campaign"
        )
        self.config["description"] = click.prompt("Description", default="")

        # Models
        click.echo("\nModels (enter blank to finish):")
        while True:
            model = click.prompt("  Model ID", default="", show_default=False)
            if not model:
                break
            params = click.prompt("  Params (e.g. 7B)", default="")
            self.config["models"].append({"name": model, "params": params})

        # Engines
        available = ["vllm", "llama_cpp", "ollama", "exllamav2", "mlx"]
        click.echo(f"\nAvailable engines: {', '.join(available)}")
        while True:
            engine = click.prompt("  Engine name", default="", show_default=False)
            if not engine:
                break
            suite = click.prompt("  Suite", default="standard")
            self.config["engines"].append({"name": engine, "suite": suite})

        # Options
        reserve = click.prompt("Disk reserve (GB)", default=50.0, type=float)
        self.config["disk"]["reserve_gb"] = reserve

        return self.config

    def run_tui(self) -> dict[str, Any] | None:
        """Run the full TUI builder.

        Returns:
            Campaign config dict, or None if user cancelled.
        """
        try:
            from textual.app import App, ComposeResult
            from textual.containers import Vertical
            from textual.widgets import Button, Footer, Header, Input, Static
        except ImportError:
            logger.info("Textual not available, falling back to simple mode")
            return self.run_simple()

        builder = self

        class BuilderScreen(App):
            CSS = """
            Screen { align: center middle; }
            #form { width: 80; padding: 2; }
            Input { margin: 1 0; }
            """
            BINDINGS = [("q", "quit", "Quit")]

            def compose(self) -> ComposeResult:
                yield Header()
                with Vertical(id="form"):
                    yield Static("KITT Campaign Builder", classes="title")
                    yield Input(placeholder="Campaign name", id="name")
                    yield Input(placeholder="Description", id="desc")
                    yield Input(
                        placeholder="Model (e.g. Qwen/Qwen2.5-7B-Instruct)", id="model"
                    )
                    yield Input(placeholder="Engine (e.g. vllm)", id="engine")
                    yield Input(
                        placeholder="Suite (default: standard)",
                        id="suite",
                        value="standard",
                    )
                    yield Button("Generate YAML", id="generate")
                yield Footer()

            def on_button_pressed(self, event: Button.Pressed) -> None:
                if event.button.id == "generate":
                    builder.config["campaign_name"] = (
                        self.query_one("#name", Input).value or "my-campaign"
                    )
                    builder.config["description"] = self.query_one("#desc", Input).value
                    model = self.query_one("#model", Input).value
                    engine = self.query_one("#engine", Input).value
                    suite = self.query_one("#suite", Input).value or "standard"

                    if model:
                        builder.config["models"].append({"name": model, "params": ""})
                    if engine:
                        builder.config["engines"].append(
                            {"name": engine, "suite": suite}
                        )

                    self.exit()

        app = BuilderScreen()
        app.run()
        return builder.config

    def to_yaml(self) -> str:
        """Convert current config to YAML string."""
        return yaml.dump(self.config, default_flow_style=False, sort_keys=False)

    def save(self, path: str) -> None:
        """Save config to YAML file."""
        from pathlib import Path

        Path(path).write_text(self.to_yaml())
        logger.info(f"Campaign config saved to {path}")
