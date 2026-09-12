"""Tests for Slack bot integration."""

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestSlackBotImportError:
    def test_import_error_when_slack_bolt_not_available(self):
        # Temporarily remove slack_bolt from sys.modules if present
        with patch.dict(
            "sys.modules", {"slack_bolt": None, "slack_bolt.adapter.socket_mode": None}
        ):
            # Force re-import
            if "kitt.bot.slack_bot" in sys.modules:
                del sys.modules["kitt.bot.slack_bot"]
            from kitt.bot.slack_bot import SlackBot

            with pytest.raises(ImportError, match="slack-bolt"):
                SlackBot(token="xoxb-test", app_token="xapp-test")


def _make_slack_bot():
    """Create a SlackBot with mocked slack_bolt dependencies."""
    mock_app_cls = MagicMock()
    mock_handler_cls = MagicMock()
    mock_app = MagicMock()
    mock_app_cls.return_value = mock_app
    mock_handler = MagicMock()
    mock_handler_cls.return_value = mock_handler

    mock_slack_bolt = MagicMock()
    mock_slack_bolt.App = mock_app_cls
    mock_socket_mode = MagicMock()
    mock_socket_mode.SocketModeHandler = mock_handler_cls

    with patch.dict(
        "sys.modules",
        {
            "slack_bolt": mock_slack_bolt,
            "slack_bolt.adapter": MagicMock(),
            "slack_bolt.adapter.socket_mode": mock_socket_mode,
        },
    ):
        if "kitt.bot.slack_bot" in sys.modules:
            del sys.modules["kitt.bot.slack_bot"]
        from kitt.bot.slack_bot import SlackBot

        bot = SlackBot(token="xoxb-test", app_token="xapp-test")

    return bot, mock_app, mock_handler, mock_app_cls, mock_handler_cls


class TestSlackBotInit:
    def test_creates_app_and_handler(self):
        bot, mock_app, mock_handler, mock_app_cls, mock_handler_cls = _make_slack_bot()
        assert bot.app is mock_app
        assert bot.handler is mock_handler
        mock_app_cls.assert_called_once_with(token="xoxb-test")
        mock_handler_cls.assert_called_once_with(mock_app, "xapp-test")


class TestSlackBotStart:
    def test_calls_handler_start(self):
        bot, mock_app, mock_handler, _, _ = _make_slack_bot()
        bot.start()
        mock_handler.start.assert_called_once()


class TestSlackBotStop:
    def test_calls_handler_close(self):
        bot, mock_app, mock_handler, _, _ = _make_slack_bot()
        bot.stop()
        mock_handler.close.assert_called_once()


class TestSlackBotSendMessage:
    def test_success_returns_true(self):
        bot, mock_app, mock_handler, _, _ = _make_slack_bot()
        result = bot.send_message("#general", "Hello from KITT")
        assert result is True
        mock_app.client.chat_postMessage.assert_called_once_with(
            channel="#general", text="Hello from KITT"
        )

    def test_failure_returns_false(self):
        bot, mock_app, mock_handler, _, _ = _make_slack_bot()
        mock_app.client.chat_postMessage.side_effect = Exception("API error")
        result = bot.send_message("#general", "Hello")
        assert result is False


class TestSlackBotCommands:
    def test_registers_kitt_command(self):
        bot, mock_app, mock_handler, _, _ = _make_slack_bot()
        mock_app.command.assert_called_with("/kitt")
