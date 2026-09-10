"""Slack bot integration for KITT."""

import logging
from typing import Any

from .base import BotInterface
from .commands import BotCommandHandler

logger = logging.getLogger(__name__)


class SlackBot(BotInterface):
    """KITT Slack bot using slack-bolt."""

    def __init__(
        self,
        token: str,
        app_token: str,
        result_store: Any | None = None,
    ) -> None:
        try:
            from slack_bolt import App
            from slack_bolt.adapter.socket_mode import SocketModeHandler
        except ImportError:
            raise ImportError(
                "slack-bolt is required for Slack bot. "
                "Install with: pip install slack-bolt"
            ) from None

        self.app = App(token=token)
        self.handler = SocketModeHandler(self.app, app_token)
        self.commands = BotCommandHandler(result_store=result_store)
        self._register_commands()

    def _register_commands(self) -> None:
        @self.app.command("/kitt")
        def handle_command(ack, command, respond):
            ack()
            text = command.get("text", "").strip()
            parts = text.split()
            cmd = parts[0] if parts else "help"

            if cmd == "status":
                respond(self.commands.handle_status())
            elif cmd == "results":
                respond(self.commands.handle_results())
            elif cmd == "help":
                respond(self.commands.handle_help())
            else:
                respond(f"Unknown command: {cmd}\n{self.commands.handle_help()}")

    def start(self) -> None:
        logger.info("Starting Slack bot...")
        self.handler.start()

    def stop(self) -> None:
        logger.info("Stopping Slack bot...")
        self.handler.close()

    def send_message(self, channel: str, text: str) -> bool:
        try:
            self.app.client.chat_postMessage(channel=channel, text=text)
            return True
        except Exception as e:
            logger.error(f"Failed to send Slack message: {e}")
            return False
