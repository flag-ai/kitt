"""Bot CLI commands."""

import logging

import click
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)


@click.group()
def bot():
    """Chat bot integration commands."""


@bot.command()
@click.option(
    "--platform",
    type=click.Choice(["slack", "discord"]),
    required=True,
    help="Bot platform",
)
@click.option("--token", required=True, help="Bot token")
@click.option("--app-token", default=None, help="App token (Slack only)")
def start(platform, token, app_token):
    """Start a chat bot."""
    if platform == "slack":
        if not app_token:
            console.print("[red]Slack requires --app-token[/red]")
            raise SystemExit(1)
        from kitt.bot.slack_bot import SlackBot

        bot_instance = SlackBot(token=token, app_token=app_token)
    else:
        from kitt.bot.discord_bot import DiscordBot

        bot_instance = DiscordBot(token=token)

    console.print(f"[bold]Starting {platform} bot...[/bold]")
    try:
        bot_instance.start()
    except KeyboardInterrupt:
        bot_instance.stop()
        console.print("Bot stopped.")


@bot.command()
def config():
    """Show bot configuration info."""
    console.print("[bold]KITT Bot Configuration[/bold]")
    console.print()
    console.print("[cyan]Slack:[/cyan]")
    console.print("  1. Create a Slack app at https://api.slack.com/apps")
    console.print("  2. Enable Socket Mode and get an app token")
    console.print("  3. Add /kitt slash command")
    console.print("  4. Install to workspace and get bot token")
    console.print(
        "  5. Run: kitt bot start --platform slack --token xoxb-... --app-token xapp-..."
    )
    console.print()
    console.print("[cyan]Discord:[/cyan]")
    console.print("  1. Create a Discord app at https://discord.com/developers")
    console.print("  2. Create a bot and get the token")
    console.print("  3. Enable Message Content Intent")
    console.print("  4. Invite bot to server with Send Messages permission")
    console.print("  5. Run: kitt bot start --platform discord --token ...")
