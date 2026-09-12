"""Web settings persistence service.

Stores key-value UI settings in the web_settings SQLite table.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading

logger = logging.getLogger(__name__)

# Defaults applied when a key has no stored value.
_DEFAULTS: dict[str, str] = {
    "devon_tab_visible": "true",
    "model_dir": "",
    "devon_url": "",
    "results_dir": "",
}


class SettingsService:
    """Read/write web UI settings backed by SQLite."""

    def __init__(
        self, db_conn: sqlite3.Connection, write_lock: threading.Lock | None = None
    ) -> None:
        self._conn = db_conn
        self._write_lock: threading.Lock = write_lock or threading.Lock()

    def _commit(self) -> None:
        """Commit the current transaction (must be called inside _write_lock)."""
        self._conn.commit()

    def get(self, key: str, default: str | None = None) -> str:
        """Get a setting value, falling back to built-in defaults."""
        row = self._conn.execute(
            "SELECT value FROM web_settings WHERE key = ?", (key,)
        ).fetchone()
        if row is not None:
            return row["value"] if isinstance(row, sqlite3.Row) else row[0]
        if default is not None:
            return default
        return _DEFAULTS.get(key, "")

    def get_effective(self, key: str, env_var: str, fallback: str) -> str:
        """Resolve a setting value: DB (non-empty) > env var > fallback.

        Returns:
            The effective value and does not store it — callers decide
            what to do with the result.
        """
        db_val = self.get(key)
        if db_val:
            return db_val
        env_val = os.environ.get(env_var, "")
        if env_val:
            return env_val
        return fallback

    def get_source(self, key: str, env_var: str) -> str:
        """Return the source of the effective value: 'saved', 'env', or 'default'."""
        db_val = self.get(key)
        if db_val:
            return "saved"
        env_val = os.environ.get(env_var, "")
        if env_val:
            return "env"
        return "default"

    def set(self, key: str, value: str) -> None:
        """Upsert a setting value."""
        with self._write_lock:
            self._conn.execute(
                "INSERT INTO web_settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self._commit()

    def get_all(self) -> dict[str, str]:
        """Return all stored settings merged with defaults."""
        settings = dict(_DEFAULTS)
        rows = self._conn.execute("SELECT key, value FROM web_settings").fetchall()
        for row in rows:
            k = row["key"] if isinstance(row, sqlite3.Row) else row[0]
            v = row["value"] if isinstance(row, sqlite3.Row) else row[1]
            settings[k] = v
        return settings

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get a setting as a boolean."""
        val = self.get(key, str(default).lower())
        return val.lower() in ("true", "1", "yes")
