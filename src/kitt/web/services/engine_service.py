"""Engine profile CRUD and agent engine status queries."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class EngineService:
    """Manages engine profiles and agent engine status."""

    def __init__(self, db_conn: Any, db_write_lock: threading.Lock | None = None):
        self._conn = db_conn
        self._lock = db_write_lock or threading.Lock()

    # ------------------------------------------------------------------
    # Engine profiles CRUD
    # ------------------------------------------------------------------

    def create_profile(self, data: dict) -> dict:
        """Create a new engine profile."""
        profile_id = uuid.uuid4().hex[:16]
        now = datetime.now().isoformat()

        with self._lock:
            self._conn.execute(
                """INSERT INTO engine_profiles
                   (id, name, engine, mode, description,
                    build_config, runtime_config, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    profile_id,
                    data["name"],
                    data["engine"],
                    data.get("mode", "docker"),
                    data.get("description", ""),
                    json.dumps(data.get("build_config", {})),
                    json.dumps(data.get("runtime_config", {})),
                    now,
                    now,
                ),
            )
            self._conn.commit()

        result = self.get_profile(profile_id)
        assert result is not None  # Just inserted — must exist
        return result

    def get_profile(self, profile_id: str) -> dict | None:
        """Get a single profile by ID."""
        row = self._conn.execute(
            "SELECT * FROM engine_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def get_profile_by_name(self, name: str) -> dict | None:
        """Get a single profile by name."""
        row = self._conn.execute(
            "SELECT * FROM engine_profiles WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_profiles(self, engine: str | None = None) -> list[dict]:
        """List all profiles, optionally filtered by engine."""
        if engine:
            rows = self._conn.execute(
                "SELECT * FROM engine_profiles WHERE engine = ? ORDER BY name",
                (engine,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM engine_profiles ORDER BY name"
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_profile(self, profile_id: str, data: dict) -> dict | None:
        """Update an existing profile."""
        existing = self.get_profile(profile_id)
        if existing is None:
            return None

        now = datetime.now().isoformat()
        with self._lock:
            self._conn.execute(
                """UPDATE engine_profiles
                   SET name = ?, engine = ?, mode = ?, description = ?,
                       build_config = ?, runtime_config = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    data.get("name", existing["name"]),
                    data.get("engine", existing["engine"]),
                    data.get("mode", existing["mode"]),
                    data.get("description", existing["description"]),
                    json.dumps(data.get("build_config", existing["build_config"])),
                    json.dumps(data.get("runtime_config", existing["runtime_config"])),
                    now,
                    profile_id,
                ),
            )
            self._conn.commit()

        return self.get_profile(profile_id)

    def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile. Returns True if deleted."""
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM engine_profiles WHERE id = ?", (profile_id,)
            )
            self._conn.commit()
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Agent engine status
    # ------------------------------------------------------------------

    def get_agent_engines(self, agent_id: str) -> list[dict]:
        """Get engine status for a specific agent."""
        rows = self._conn.execute(
            "SELECT * FROM agent_engines WHERE agent_id = ? ORDER BY engine",
            (agent_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_agent_engine(self, agent_id: str, engine_data: dict) -> None:
        """Insert or update an agent's engine status."""
        with self._lock:
            self._conn.execute(
                """INSERT INTO agent_engines
                   (agent_id, engine, mode, version, binary_path, status, last_checked)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(agent_id, engine, mode) DO UPDATE SET
                       version = excluded.version,
                       binary_path = excluded.binary_path,
                       status = excluded.status,
                       last_checked = excluded.last_checked""",
                (
                    agent_id,
                    engine_data["engine"],
                    engine_data.get("mode", "docker"),
                    engine_data.get("version", ""),
                    engine_data.get("binary_path", ""),
                    engine_data.get("status", "unknown"),
                    datetime.now().isoformat(),
                ),
            )
            self._conn.commit()

    def get_engine_status_matrix(self) -> dict[str, list[dict]]:
        """Get engine status for all agents, grouped by agent ID."""
        rows = self._conn.execute(
            "SELECT * FROM agent_engines ORDER BY agent_id, engine"
        ).fetchall()
        matrix: dict[str, list[dict]] = {}
        for row in rows:
            d = dict(row)
            agent_id = d["agent_id"]
            if agent_id not in matrix:
                matrix[agent_id] = []
            matrix[agent_id].append(d)
        return matrix

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: Any) -> dict:
        """Convert a database row to a dict, parsing JSON fields."""
        d = dict(row)
        for field in ("build_config", "runtime_config"):
            if field in d and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    d[field] = {}
        return d
