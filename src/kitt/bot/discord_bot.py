"""Discord bot integration for KITT."""

import logging
from typing import Any

from .base import BotInterface
from .commands import BotCommandHandler

logger = logging.getLogger(__name__)


class DiscordBot(BotInterface):
    """KITT Discord bot using discord.py."""

    def __init__(
        self,
        token: str,
        result_store: Any | None = None,
    ) -> None:
        try:
            import discord
            from discord.ext import commands as discord_commands
        except ImportError:
            raise ImportError(
                "discord.py is required for Discord bot. "
                "Install with: pip install discord.py"
            ) from None

        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = discord_commands.Bot(command_prefix="!", intents=intents)
        self.token = token
        self.commands_handler = BotCommandHandler(result_store=result_store)
        self._register_commands()

    def _register_commands(self) -> None:
        handler = self.commands_handler

        @self.bot.command(name="kitt")
        async def kitt_command(ctx, *args):
            cmd = args[0] if args else "help"
            if cmd == "status":
                await ctx.send(handler.handle_status())
            elif cmd == "results":
                await ctx.send(handler.handle_results())
            elif cmd == "help":
                await ctx.send(handler.handle_help())
            else:
                await ctx.send(f"Unknown: {cmd}\n{handler.handle_help()}")

    def start(self) -> None:
        logger.info("Starting Discord bot...")
        self.bot.run(self.token)

    def stop(self) -> None:
        logger.info("Stopping Discord bot...")
        import asyncio

        asyncio.get_event_loop().run_until_complete(self.bot.close())

    def send_message(self, channel: str, text: str) -> bool:
        logger.warning("Discord send_message requires async context")
        return False
