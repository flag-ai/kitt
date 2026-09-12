"""Shared command handler for bot integrations."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BotCommandHandler:
    """Handle bot commands with shared logic across Slack/Discord."""

    def __init__(self, result_store: Any | None = None) -> None:
        self.store = result_store

    def handle_status(self) -> str:
        """Return campaign status summary."""
        try:
            from kitt.campaign.state_manager import CampaignStateManager

            mgr = CampaignStateManager()
            campaigns = mgr.list_campaigns()
            if not campaigns:
                return "No campaigns found."
            latest = campaigns[-1]
            return (
                f"Latest campaign: {latest['campaign_name']}\n"
                f"Status: {latest['status']}\n"
                f"Runs: {latest['total_runs']} | "
                f"Success: {latest['succeeded']} | "
                f"Failed: {latest['failed']}"
            )
        except Exception as e:
            return f"Error getting status: {e}"

    def handle_results(
        self,
        model: str | None = None,
        engine: str | None = None,
        limit: int = 5,
    ) -> str:
        """Return recent results."""
        if self.store is None:
            return "No storage backend configured."

        filters = {}
        if model:
            filters["model"] = model
        if engine:
            filters["engine"] = engine

        try:
            results = self.store.query(
                filters=filters or None,
                order_by="-timestamp",
                limit=limit,
            )
            if not results:
                return "No results found."

            lines = [f"Recent results ({len(results)}):"]
            for r in results:
                status = "PASS" if r.get("passed") else "FAIL"
                lines.append(
                    f"  {r.get('model', '?')} / {r.get('engine', '?')} "
                    f"— {status} ({r.get('timestamp', '?')[:19]})"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Error querying results: {e}"

    def handle_compare(self, model: str, engine: str) -> str:
        """Compare recent runs for a model/engine pair."""
        if self.store is None:
            return "No storage backend configured."

        try:
            results = self.store.query(
                filters={"model": model, "engine": engine},
                order_by="-timestamp",
                limit=2,
            )
            if len(results) < 2:
                return "Need at least 2 runs to compare."

            current = results[0]
            previous = results[1]

            lines = [f"Comparison for {model} / {engine}:"]
            lines.append(f"  Current:  {current.get('timestamp', '?')[:19]}")
            lines.append(f"  Previous: {previous.get('timestamp', '?')[:19]}")

            # Compare pass/fail
            curr_status = "PASS" if current.get("passed") else "FAIL"
            prev_status = "PASS" if previous.get("passed") else "FAIL"
            lines.append(f"  Status: {prev_status} -> {curr_status}")

            return "\n".join(lines)
        except Exception as e:
            return f"Error comparing: {e}"

    def handle_help(self) -> str:
        """Return help text."""
        return (
            "KITT Bot Commands:\n"
            "  /kitt status - Show campaign status\n"
            "  /kitt results [--model X] [--engine Y] - Show recent results\n"
            "  /kitt compare <model> <engine> - Compare recent runs\n"
            "  /kitt help - Show this help"
        )
