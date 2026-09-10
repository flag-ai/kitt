"""Notification dispatch for campaign events."""

import json
import logging
import platform
import shutil
import smtplib
import subprocess
import urllib.request
from email.mime.text import MIMEText

from .models import NotificationConfig

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Send notifications on campaign events.

    Supports: webhooks (HTTP POST), desktop notifications, and email.
    """

    def __init__(self, config: NotificationConfig) -> None:
        self.config = config

    def notify_complete(self, campaign_name: str, summary: str) -> None:
        """Notify that a campaign has completed."""
        if not self.config.on_complete:
            return
        title = f"KITT Campaign Complete: {campaign_name}"
        self._dispatch(title, summary)

    def notify_failure(self, campaign_name: str, run_key: str, error: str) -> None:
        """Notify that a run has failed."""
        if not self.config.on_failure:
            return
        title = f"KITT Run Failed: {run_key}"
        body = f"Campaign: {campaign_name}\nRun: {run_key}\nError: {error}"
        self._dispatch(title, body)

    def _dispatch(self, title: str, body: str) -> None:
        """Send notification through all configured channels."""
        if self.config.webhook_url:
            self._send_webhook(title, body)
        if self.config.desktop:
            self._send_desktop(title, body)
        if self.config.email and self.config.smtp_host:
            self._send_email(title, body)

    def _send_webhook(self, title: str, body: str) -> None:
        """Send notification via HTTP POST webhook."""
        payload = json.dumps({"title": title, "body": body}).encode("utf-8")
        try:
            assert self.config.webhook_url is not None
            req = urllib.request.Request(
                self.config.webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10):
                pass
            logger.debug(f"Webhook notification sent: {title}")
        except Exception as e:
            logger.warning(f"Webhook notification failed: {e}")

    def _send_desktop(self, title: str, body: str) -> None:
        """Send desktop notification via OS-native mechanism."""
        system = platform.system()
        try:
            if system == "Linux" and shutil.which("notify-send"):
                subprocess.run(
                    ["notify-send", title, body[:200]],
                    capture_output=True,
                    timeout=5,
                )
            elif system == "Darwin" and shutil.which("osascript"):
                script = f'display notification "{body[:200]}" with title "{title}"'
                subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    timeout=5,
                )
            else:
                logger.debug(f"Desktop notifications not available on {system}")
        except Exception as e:
            logger.warning(f"Desktop notification failed: {e}")

    def _send_email(self, title: str, body: str) -> None:
        """Send notification via SMTP email."""
        if not self.config.email or not self.config.smtp_host:
            return

        try:
            msg = MIMEText(body)
            msg["Subject"] = title
            msg["From"] = self.config.smtp_user or "kitt@localhost"
            msg["To"] = self.config.email

            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                if self.config.smtp_user and self.config.smtp_password:
                    server.starttls()
                    server.login(self.config.smtp_user, self.config.smtp_password)
                server.send_message(msg)

            logger.debug(f"Email notification sent to {self.config.email}")
        except Exception as e:
            logger.warning(f"Email notification failed: {e}")
