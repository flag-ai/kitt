"""Sync results from remote host to local."""

import json
import logging
from pathlib import Path

from .host_config import HostConfig
from .ssh_connection import SSHConnection

logger = logging.getLogger(__name__)


class ResultSync:
    """Download and merge results from a remote host."""

    def __init__(
        self,
        host_config: HostConfig,
        local_results_dir: Path | None = None,
    ) -> None:
        self.host = host_config
        self.conn = SSHConnection(
            host=host_config.hostname,
            user=host_config.user or None,
            ssh_key=host_config.ssh_key or None,
            port=host_config.port,
        )
        self.local_dir = local_results_dir or Path.cwd() / "kitt-results"

    def list_remote_results(self) -> list[str]:
        """List result directories on the remote host.

        Returns:
            List of remote result directory paths.
        """
        remote_dir = self.host.storage_path or "~/kitt-results"
        rc, out, _ = self.conn.run_command(
            f"find {remote_dir} -name 'metrics.json' -printf '%h\\n' 2>/dev/null | sort -u"
        )
        if rc == 0 and out.strip():
            return out.strip().splitlines()
        return []

    def list_local_results(self) -> list[str]:
        """List result directory names that already exist locally."""
        if not self.local_dir.exists():
            return []
        return [
            str(p.parent.relative_to(self.local_dir))
            for p in self.local_dir.glob("**/metrics.json")
        ]

    def sync(self, incremental: bool = True) -> int:
        """Download results from remote to local.

        Args:
            incremental: If True, only download new results.

        Returns:
            Number of result directories synced.
        """
        remote_results = self.list_remote_results()
        if not remote_results:
            logger.info("No remote results found")
            return 0

        local_existing = set(self.list_local_results()) if incremental else set()
        synced = 0

        self.local_dir.mkdir(parents=True, exist_ok=True)

        for remote_path in remote_results:
            # Extract relative path for comparison
            # Remote paths like ~/kitt-results/model/engine/timestamp
            remote_base = self.host.storage_path or "~/kitt-results"
            rel_path = remote_path.replace(remote_base + "/", "").replace(
                remote_base, ""
            )
            if rel_path.startswith("/"):
                rel_path = rel_path[1:]

            if incremental and rel_path in local_existing:
                logger.debug(f"Skipping (already local): {rel_path}")
                continue

            local_dest = self.local_dir / rel_path
            local_dest.mkdir(parents=True, exist_ok=True)

            if self.conn.download_directory(remote_path + "/", str(local_dest)):
                synced += 1
                logger.info(f"Synced: {rel_path}")
            else:
                logger.warning(f"Failed to sync: {rel_path}")

        logger.info(f"Synced {synced} result(s) from {self.conn.target}")
        return synced

    def import_to_store(self, result_store) -> int:
        """Import synced results into a ResultStore.

        Args:
            result_store: ResultStore instance to import into.

        Returns:
            Number of results imported.
        """
        imported = 0
        for metrics_file in self.local_dir.glob("**/metrics.json"):
            try:
                data = json.loads(metrics_file.read_text())
                result_store.save_result(data)
                imported += 1
            except Exception as e:
                logger.debug(f"Failed to import {metrics_file}: {e}")

        return imported
