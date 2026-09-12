"""Cron-based campaign scheduling."""

import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CronScheduler:
    """Schedule campaigns via cron expressions or daemon mode."""

    CRON_PATTERN = re.compile(
        r"^(\*|[0-9,\-/]+)\s+"
        r"(\*|[0-9,\-/]+)\s+"
        r"(\*|[0-9,\-/]+)\s+"
        r"(\*|[0-9,\-/]+)\s+"
        r"(\*|[0-9,\-/]+)$"
    )

    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or Path.home() / ".kitt" / "schedules"
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def schedule(
        self,
        campaign_config_path: str,
        cron_expr: str,
        campaign_id: str | None = None,
    ) -> bool:
        """Register a campaign on a cron schedule.

        Args:
            campaign_config_path: Path to campaign YAML config.
            cron_expr: Cron expression (e.g. "0 2 * * *" for 2am daily).
            campaign_id: Optional identifier for this schedule.

        Returns:
            True if scheduling succeeded.
        """
        if not self.CRON_PATTERN.match(cron_expr):
            logger.error(f"Invalid cron expression: {cron_expr}")
            return False

        schedule_id = campaign_id or Path(campaign_config_path).stem

        # Save schedule config
        import json

        schedule_file = self.config_dir / f"{schedule_id}.json"
        schedule_data = {
            "campaign_config": campaign_config_path,
            "cron_expr": cron_expr,
            "schedule_id": schedule_id,
            "enabled": True,
        }
        schedule_file.write_text(json.dumps(schedule_data, indent=2))

        # Register in system crontab
        kitt_cmd = f"{sys.executable} -m kitt campaign run {campaign_config_path}"
        cron_line = f"{cron_expr} {kitt_cmd} # kitt-schedule:{schedule_id}"

        try:
            result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            existing = result.stdout if result.returncode == 0 else ""

            # Remove old entry if exists
            lines = [
                line
                for line in existing.splitlines()
                if f"kitt-schedule:{schedule_id}" not in line
            ]
            lines.append(cron_line)

            new_crontab = "\n".join(lines) + "\n"
            proc = subprocess.run(
                ["crontab", "-"],
                input=new_crontab,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                logger.error(f"Failed to set crontab: {proc.stderr}")
                return False

            logger.info(f"Scheduled {schedule_id}: {cron_expr}")
            return True

        except FileNotFoundError:
            logger.warning("crontab not available — schedule saved to config only")
            return True

    def unschedule(self, schedule_id: str) -> bool:
        """Remove a scheduled campaign.

        Returns:
            True if removed.
        """
        # Remove config file
        schedule_file = self.config_dir / f"{schedule_id}.json"
        if schedule_file.exists():
            schedule_file.unlink()

        # Remove from crontab
        try:
            result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            if result.returncode == 0:
                lines = [
                    line
                    for line in result.stdout.splitlines()
                    if f"kitt-schedule:{schedule_id}" not in line
                ]
                new_crontab = "\n".join(lines) + "\n"
                subprocess.run(
                    ["crontab", "-"],
                    input=new_crontab,
                    capture_output=True,
                    text=True,
                )
        except FileNotFoundError:
            pass

        logger.info(f"Unscheduled {schedule_id}")
        return True

    def list_scheduled(self) -> list[dict[str, Any]]:
        """List all scheduled campaigns."""
        import json

        schedules = []
        for f in sorted(self.config_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                schedules.append(data)
            except Exception:
                continue
        return schedules
