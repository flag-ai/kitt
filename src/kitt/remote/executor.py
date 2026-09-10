"""Remote campaign execution via SSH."""

import logging
import re
import shlex
import time
from pathlib import Path

from .host_config import HostConfig
from .ssh_connection import SSHConnection

logger = logging.getLogger(__name__)

_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_.~/@: -]+$")


def _validate_remote_path(path: str) -> str:
    """Validate that a remote path contains only safe characters."""
    if not _SAFE_PATH_RE.match(path):
        raise ValueError(f"Unsafe characters in remote path: {path!r}")
    return path


class RemoteCampaignExecutor:
    """Execute campaigns on remote hosts via SSH."""

    def __init__(self, host_config: HostConfig) -> None:
        self.host = host_config
        self.conn = SSHConnection(
            host=host_config.hostname,
            user=host_config.user or None,
            ssh_key=host_config.ssh_key or None,
            port=host_config.port,
            strict_host_key=host_config.strict_host_key,
        )

    def upload_config(self, local_config_path: str) -> str | None:
        """Upload campaign config to remote host.

        Returns:
            Remote path if successful, None otherwise.
        """
        remote_dir = "~/kitt-campaigns"
        self.conn.run_command(f"mkdir -p {shlex.quote(remote_dir)}")

        filename = Path(local_config_path).name
        remote_path = f"{remote_dir}/{filename}"
        _validate_remote_path(remote_path)

        if self.conn.upload_file(local_config_path, remote_path):
            logger.info(f"Config uploaded to {remote_path}")
            return remote_path
        return None

    def start_campaign(
        self,
        remote_config_path: str,
        dry_run: bool = False,
    ) -> bool:
        """Start a campaign on the remote host (detached).

        Uses nohup for disconnect safety.

        Returns:
            True if campaign started.
        """
        kitt_cmd = self.host.kitt_path or "kitt"
        _validate_remote_path(remote_config_path)
        cmd = f"{shlex.quote(kitt_cmd)} campaign run {shlex.quote(remote_config_path)}"
        if dry_run:
            cmd += " --dry-run"

        # Run detached with nohup
        full_cmd = f"nohup {cmd} > ~/kitt-campaign.log 2>&1 & echo $!"

        rc, out, err = self.conn.run_command(full_cmd)
        if rc == 0 and out.strip():
            pid = out.strip()
            if not pid.isdigit():
                logger.warning(f"Unexpected PID value: {pid!r}")
                return False
            logger.info(f"Campaign started on remote (PID: {pid})")
            return True
        else:
            logger.error(f"Failed to start remote campaign: {err}")
            return False

    def check_status(self) -> str:
        """Check if a campaign is running on the remote host.

        Returns:
            Status string.
        """
        kitt_cmd = self.host.kitt_path or "kitt"

        # Check for running process
        rc, out, _ = self.conn.run_command("pgrep -f 'kitt campaign run'")
        if rc == 0 and out.strip():
            return "running"

        # Check campaign state
        rc, out, _ = self.conn.run_command(
            f"{shlex.quote(kitt_cmd)} campaign status 2>/dev/null"
        )
        if rc == 0:
            return out.strip()

        return "unknown"

    def get_logs(self, tail: int = 50) -> str:
        """Get recent campaign logs from remote.

        Args:
            tail: Number of lines to retrieve.

        Returns:
            Log output string.
        """
        rc, out, _ = self.conn.run_command(
            f"tail -n {shlex.quote(str(tail))} ~/kitt-campaign.log 2>/dev/null"
        )
        return out if rc == 0 else "No logs available."

    def run_and_wait(
        self,
        local_config_path: str,
        poll_interval: int = 30,
        timeout: int = 7200,
        dry_run: bool = False,
    ) -> bool:
        """Upload config, run campaign, and wait for completion.

        Args:
            local_config_path: Local path to campaign YAML.
            poll_interval: Seconds between status checks.
            timeout: Maximum wait time in seconds.
            dry_run: If True, pass --dry-run to campaign.

        Returns:
            True if campaign completed successfully.
        """
        # Upload config
        remote_path = self.upload_config(local_config_path)
        if not remote_path:
            return False

        # Start campaign
        if not self.start_campaign(remote_path, dry_run=dry_run):
            return False

        # Poll for completion
        elapsed = 0
        while elapsed < timeout:
            time.sleep(poll_interval)
            elapsed += poll_interval

            status = self.check_status()
            if status == "running":
                logger.debug(f"Campaign still running ({elapsed}s elapsed)")
                continue
            else:
                logger.info(f"Campaign finished: {status}")
                return True

        logger.warning(f"Campaign timed out after {timeout}s")
        return False
