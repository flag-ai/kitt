"""Tests for Discord bot integration."""

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestDiscordBotImportError:
    def test_import_error_when_discord_not_available(self):
        with patch.dict(
            "sys.modules",
            {"discord": None, "discord.ext": None, "discord.ext.commands": None},
        ):
            if "kitt.bot.discord_bot" in sys.modules:
                del sys.modules["kitt.bot.discord_bot"]
            from kitt.bot.discord_bot import DiscordBot

            with pytest.raises(ImportError, match="discord.py"):
                DiscordBot(token="discord-test-token")


def _make_discord_bot():
    """Create a DiscordBot with mocked discord dependencies."""
    mock_discord = MagicMock()
    mock_commands = MagicMock()
    mock_bot = MagicMock()
    mock_commands.Bot.return_value = mock_bot

    # Set up Intents mock
    mock_intents = MagicMock()
    mock_discord.Intents.default.return_value = mock_intents

    mock_ext = MagicMock()
    mock_ext.commands = mock_commands

    with patch.dict(
        "sys.modules",
        {
            "discord": mock_discord,
            "discord.ext": mock_ext,
            "discord.ext.commands": mock_commands,
        },
    ):
        if "kitt.bot.discord_bot" in sys.modules:
            del sys.modules["kitt.bot.discord_bot"]
        from kitt.bot.discord_bot import DiscordBot

        bot = DiscordBot(token="discord-test-token")

    return bot, mock_bot, mock_discord, mock_commands


class TestDiscordBotInit:
    def test_creates_bot(self):
        bot, mock_bot, mock_discord, mock_commands = _make_discord_bot()
        assert bot.bot is mock_bot
        mock_commands.Bot.assert_called_once()
        call_kwargs = mock_commands.Bot.call_args[1]
        assert call_kwargs["command_prefix"] == "!"


class TestDiscordBotStart:
    def test_calls_bot_run(self):
        bot, mock_bot, _, _ = _make_discord_bot()
        bot.start()
        mock_bot.run.assert_called_once_with("discord-test-token")


class TestDiscordBotSendMessage:
    def test_returns_false(self):
        bot, mock_bot, _, _ = _make_discord_bot()
        result = bot.send_message("#general", "Hello")
        assert result is False


class TestDiscordBotCommands:
    def test_registers_kitt_command(self):
        bot, mock_bot, _, _ = _make_discord_bot()
        mock_bot.command.assert_called_with(name="kitt")


class TestDiscordBotStop:
    def test_calls_bot_close(self):
        bot, mock_bot, _, _ = _make_discord_bot()
        mock_loop = MagicMock()
        with patch("asyncio.get_event_loop", return_value=mock_loop):
            bot.stop()
            mock_loop.run_until_complete.assert_called_once()
