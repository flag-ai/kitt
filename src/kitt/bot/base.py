"""Base class for chat bot integrations."""

from abc import ABC, abstractmethod


class BotInterface(ABC):
    """Abstract interface for chat bots."""

    @abstractmethod
    def start(self) -> None:
        """Start the bot event loop."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the bot."""

    @abstractmethod
    def send_message(self, channel: str, text: str) -> bool:
        """Send a message to a channel."""
