"""Campaign management service for the web UI.

Handles campaign CRUD, launch via agent, and status tracking.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime
from typing import Any

from kitt.web.services.event_bus import event_bus

logger = logging.getLogger(__name__)


class CampaignService:
    """Manages web campaigns stored in the database."""

    def __init__(
        self, db_conn: sqlite3.Connection, write_lock: threading.Lock | None = None
    ) -> None:
        self._conn = db_conn
        self._write_lock: threading.Lock = write_lock or threading.Lock()

    def _commit(self) -> None:
        """Commit the current transaction (must be called inside _write_lock)."""
        self._conn.commit()

    def create(
        self,
        name: str,
        config_json: dict[str, Any],
        description: str = "",
        agent_id: str = "",
    ) -> str:
        """Create a new campaign.

        Returns:
            The campaign ID.
        """
        campaign_id = uuid.uuid4().hex[:16]
        now = datetime.now().isoformat()

        with self._write_lock:
            self._conn.execute(
                """INSERT INTO web_campaigns
                   (id, name, description, config_json, status, agent_id, created_at)
                   VALUES (?, ?, ?, ?, 'draft', ?, ?)""",
                (
                    campaign_id,
                    name,
                    description,
                    json.dumps(config_json, default=str),
                    agent_id,
                    now,
                ),
            )
            self._commit()

        event_bus.publish("campaign_created", campaign_id, {"name": name})
        return campaign_id

    def get(self, campaign_id: str) -> dict[str, Any] | None:
        """Get full campaign details."""
        row = self._conn.execute(
            "SELECT * FROM web_campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["config"] = json.loads(result.pop("config_json", "{}"))
        return result

    def list_campaigns(
        self,
        status: str = "",
        page: int = 1,
        per_page: int = 25,
    ) -> dict[str, Any]:
        """List campaigns with optional status filter."""
        sql = "SELECT * FROM web_campaigns"
        params: list[Any] = []

        if status:
            sql += " WHERE status = ?"
            params.append(status)

        # Count
        count_sql = sql.replace("SELECT *", "SELECT COUNT(*) as cnt")
        total = self._conn.execute(count_sql, params).fetchone()["cnt"]

        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([per_page, (page - 1) * per_page])

        rows = self._conn.execute(sql, params).fetchall()
        items = []
        for r in rows:
            item = dict(r)
            item.pop("config_json", None)
            items.append(item)

        pages = (total + per_page - 1) // per_page if per_page else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    def update_status(
        self,
        campaign_id: str,
        status: str,
        error: str = "",
        **kwargs: Any,
    ) -> bool:
        """Update campaign status and optional fields."""
        sets = ["status = ?"]
        params: list[Any] = [status]

        if error:
            sets.append("error = ?")
            params.append(error)

        now = datetime.now().isoformat()
        if status == "running":
            sets.append("started_at = ?")
            params.append(now)
        elif status in ("completed", "failed", "cancelled"):
            sets.append("completed_at = ?")
            params.append(now)

        for field in ("total_runs", "succeeded", "failed", "skipped"):
            if field in kwargs:
                sets.append(f"{field} = ?")
                params.append(kwargs[field])

        params.append(campaign_id)
        sql = f"UPDATE web_campaigns SET {', '.join(sets)} WHERE id = ?"
        with self._write_lock:
            cursor = self._conn.execute(sql, params)
            self._commit()

        event_bus.publish(
            "status",
            campaign_id,
            {
                "status": status,
                "error": error,
            },
        )
        return cursor.rowcount > 0

    def delete(self, campaign_id: str) -> bool:
        """Delete a campaign."""
        with self._write_lock:
            cursor = self._conn.execute(
                "DELETE FROM web_campaigns WHERE id = ?", (campaign_id,)
            )
            self._commit()
        return cursor.rowcount > 0

    def update_config(self, campaign_id: str, config: dict[str, Any]) -> bool:
        """Update campaign configuration (only while in draft status)."""
        with self._write_lock:
            cursor = self._conn.execute(
                """UPDATE web_campaigns SET config_json = ?
                   WHERE id = ? AND status = 'draft'""",
                (json.dumps(config, default=str), campaign_id),
            )
            self._commit()
        return cursor.rowcount > 0
