"""Tests for campaign notifications."""

from unittest.mock import MagicMock, patch

import pytest

from kitt.campaign.models import NotificationConfig
from kitt.campaign.notifications import NotificationDispatcher


@pytest.fixture
def webhook_config():
    return NotificationConfig(
        webhook_url="https://hooks.example.com/test",
        on_complete=True,
        on_failure=True,
    )


@pytest.fixture
def desktop_config():
    return NotificationConfig(desktop=True, on_complete=True, on_failure=True)


@pytest.fixture
def email_config():
    return NotificationConfig(
        email="user@example.com",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="kitt",
        smtp_password="secret",
        on_complete=True,
        on_failure=True,
    )


class TestWebhookNotification:
    @patch("urllib.request.urlopen")
    def test_sends_webhook(self, mock_urlopen, webhook_config):
        mock_urlopen.return_value.__enter__ = MagicMock()
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        dispatcher = NotificationDispatcher(webhook_config)
        dispatcher.notify_complete("Test Campaign", "All passed")

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://hooks.example.com/test"
        assert req.method == "POST"

    @patch("urllib.request.urlopen", side_effect=Exception("Network error"))
    def test_webhook_failure_handled(self, mock_urlopen, webhook_config):
        dispatcher = NotificationDispatcher(webhook_config)
        # Should not raise
        dispatcher.notify_complete("Test", "summary")

    def test_no_webhook_when_disabled(self):
        config = NotificationConfig(on_complete=False)
        dispatcher = NotificationDispatcher(config)
        with patch("urllib.request.urlopen") as mock:
            dispatcher.notify_complete("Test", "summary")
            mock.assert_not_called()


class TestDesktopNotification:
    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/notify-send")
    @patch("platform.system", return_value="Linux")
    def test_linux_notify_send(self, mock_sys, mock_which, mock_run, desktop_config):
        dispatcher = NotificationDispatcher(desktop_config)
        dispatcher.notify_complete("Test Campaign", "Done")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "notify-send"

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/osascript")
    @patch("platform.system", return_value="Darwin")
    def test_macos_osascript(self, mock_sys, mock_which, mock_run, desktop_config):
        dispatcher = NotificationDispatcher(desktop_config)
        dispatcher.notify_complete("Test Campaign", "Done")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "osascript"


class TestEmailNotification:
    @patch("smtplib.SMTP")
    def test_sends_email(self, mock_smtp_cls, email_config):
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = lambda s: mock_server
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        dispatcher = NotificationDispatcher(email_config)
        dispatcher.notify_complete("Test Campaign", "summary")

        mock_smtp_cls.assert_called_once_with("smtp.example.com", 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("kitt", "secret")
        mock_server.send_message.assert_called_once()


class TestNotifyFailure:
    @patch("urllib.request.urlopen")
    def test_failure_notification(self, mock_urlopen, webhook_config):
        mock_urlopen.return_value.__enter__ = MagicMock()
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        dispatcher = NotificationDispatcher(webhook_config)
        dispatcher.notify_failure("Campaign", "Model|engine|quant", "OOM error")

        mock_urlopen.assert_called_once()

    def test_failure_disabled(self):
        config = NotificationConfig(
            webhook_url="https://hooks.example.com/test",
            on_failure=False,
        )
        dispatcher = NotificationDispatcher(config)
        with patch("urllib.request.urlopen") as mock:
            dispatcher.notify_failure("Campaign", "key", "error")
            mock.assert_not_called()
