"""Agent lifecycle management service.

Manages agent registration, heartbeats, command dispatch,
and status tracking.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from typing import Any

from kitt.web.models.agent import AgentHeartbeat, AgentRegistration
from kitt.web.services.event_bus import event_bus

logger = logging.getLogger(__name__)

# Agent is considered offline if no heartbeat for this many seconds
HEARTBEAT_TIMEOUT_S = 90


class AgentManager:
    """Manages agent lifecycle and command dispatch."""

    def __init__(
        self, db_conn: sqlite3.Connection, write_lock: threading.Lock | None = None
    ) -> None:
        self._conn = db_conn
        self._write_lock: threading.Lock = write_lock or threading.Lock()

    def _commit(self) -> None:
        """Commit the current transaction (must be called inside _write_lock)."""
        self._conn.commit()

    @staticmethod
    def _hash_token(token: str) -> str:
        """Compute SHA-256 hash of a token for secure storage."""
        return hashlib.sha256(token.encode()).hexdigest()

    def provision(self, name: str, port: int = 8090) -> dict[str, Any]:
        """Provision a new agent with a unique token.

        If an agent with the same name already exists, rotates its token.

        Returns:
            Dict with agent_id, raw token (one-time), and token_prefix.
        """
        raw_token = secrets.token_hex(32)
        token_hash = self._hash_token(raw_token)
        token_prefix = raw_token[:8]
        now = datetime.now().isoformat()

        with self._write_lock:
            row = self._conn.execute(
                "SELECT id FROM agents WHERE name = ?", (name,)
            ).fetchone()

            if row:
                agent_id = row["id"]
                self._conn.execute(
                    "UPDATE agents SET token_hash = ?, token_prefix = ?, port = ? WHERE id = ?",
                    (token_hash, token_prefix, port, agent_id),
                )
                logger.info("Rotated token for existing agent: %s (%s)", name, agent_id)
            else:
                agent_id = uuid.uuid4().hex[:16]
                self._conn.execute(
                    """INSERT INTO agents
                       (id, name, hostname, port, token, token_hash, token_prefix,
                        status, registered_at)
                       VALUES (?, ?, ?, ?, '', ?, ?, 'provisioned', ?)""",
                    (agent_id, name, name, port, token_hash, token_prefix, now),
                )
                logger.info("Provisioned new agent: %s (%s)", name, agent_id)

            self._commit()
        self._ensure_default_settings(agent_id)
        return {
            "agent_id": agent_id,
            "token": raw_token,
            "token_prefix": token_prefix,
        }

    def create_test_agent(
        self,
        name: str,
        gpu_info: str = "NVIDIA RTX 4090 24GB",
        gpu_count: int = 1,
        cpu_info: str = "Intel Core i9-13900K",
        cpu_arch: str = "x86_64",
        ram_gb: int = 64,
        environment_type: str = "native_linux",
    ) -> dict[str, Any]:
        """Create a virtual test agent directly in the database.

        Test agents are always online and simulate test execution
        without requiring a real GPU server.

        Returns:
            Dict with agent_id.
        """
        agent_id = uuid.uuid4().hex[:16]
        now = datetime.now().isoformat()
        hostname = f"test-{name}"
        tags = json.dumps(["test"])

        with self._write_lock:
            self._conn.execute(
                """INSERT INTO agents
                   (id, name, hostname, port, token, token_hash, token_prefix,
                    status, gpu_info, gpu_count,
                    cpu_info, cpu_arch, ram_gb, environment_type,
                    last_heartbeat, registered_at, tags)
                   VALUES (?, ?, ?, 0, '', '', '', 'online', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    agent_id,
                    name,
                    hostname,
                    gpu_info,
                    gpu_count,
                    cpu_info,
                    cpu_arch,
                    ram_gb,
                    environment_type,
                    now,
                    now,
                    tags,
                ),
            )
            self._commit()

        self._ensure_default_settings(agent_id)
        logger.info("Created test agent: %s (%s)", name, agent_id)
        return {"agent_id": agent_id}

    def is_test_agent(self, agent_id: str) -> bool:
        """Check whether an agent is a virtual test agent."""
        row = self._conn.execute(
            "SELECT tags FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        if row is None:
            return False
        raw_tags = row["tags"] or "[]"
        try:
            tags = json.loads(raw_tags)
        except (json.JSONDecodeError, TypeError):
            return False
        return "test" in tags

    def register(self, reg: AgentRegistration, token: str) -> dict[str, Any]:
        """Register a new agent or update an existing one.

        Returns:
            Dict with agent_id and heartbeat_interval_s.
        """
        now = datetime.now().isoformat()
        token_hash = self._hash_token(token) if token else ""

        with self._write_lock:
            # Check inside lock to prevent TOCTOU race on concurrent registrations
            row = self._conn.execute(
                "SELECT id FROM agents WHERE name = ?", (reg.name,)
            ).fetchone()
            if row:
                agent_id = row["id"]
                self._conn.execute(
                    """UPDATE agents SET
                        hostname = ?, port = ?, status = 'online',
                        gpu_info = ?, gpu_count = ?, cpu_info = ?, cpu_arch = ?,
                        ram_gb = ?,
                        environment_type = ?, fingerprint = ?, kitt_version = ?,
                        hardware_details = ?,
                        last_heartbeat = ?
                       WHERE id = ?""",
                    (
                        reg.hostname,
                        reg.port,
                        reg.gpu_info,
                        reg.gpu_count,
                        reg.cpu_info,
                        reg.cpu_arch,
                        reg.ram_gb,
                        reg.environment_type,
                        reg.fingerprint,
                        reg.kitt_version,
                        reg.hardware_details,
                        now,
                        agent_id,
                    ),
                )
            else:
                agent_id = uuid.uuid4().hex[:16]
                self._conn.execute(
                    """INSERT INTO agents
                       (id, name, hostname, port, token, token_hash, token_prefix,
                        status, gpu_info, gpu_count,
                        cpu_info, cpu_arch, ram_gb, environment_type, fingerprint,
                        kitt_version, hardware_details,
                        last_heartbeat, registered_at)
                       VALUES (?, ?, ?, ?, '', ?, ?, 'online', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        agent_id,
                        reg.name,
                        reg.hostname,
                        reg.port,
                        token_hash,
                        token[:8] if token else "",
                        reg.gpu_info,
                        reg.gpu_count,
                        reg.cpu_info,
                        reg.cpu_arch,
                        reg.ram_gb,
                        reg.environment_type,
                        reg.fingerprint,
                        reg.kitt_version,
                        reg.hardware_details,
                        now,
                        now,
                    ),
                )

            self._commit()
        self._ensure_default_settings(agent_id)
        event_bus.publish(
            "agent_status",
            agent_id,
            {
                "name": reg.name,
                "status": "online",
            },
        )

        return {"agent_id": agent_id, "heartbeat_interval_s": 30}

    def heartbeat(self, agent_id: str, hb: AgentHeartbeat) -> dict[str, Any]:
        """Process agent heartbeat.

        Checks for pending quick_tests assigned to this agent and returns
        them as commands for the agent to execute.  Also persists engine
        status reported by the agent into the ``agent_engines`` table.

        Returns:
            Dict with ack and any pending commands.
        """
        now = datetime.now().isoformat()
        with self._write_lock:
            self._conn.execute(
                """UPDATE agents SET
                    status = ?, last_heartbeat = ?
                   WHERE id = ?""",
                (hb.status or "idle", now, agent_id),
            )

            # Persist engine status reported by the agent.
            for eng in hb.engines:
                engine_name = eng.get("engine", "")
                if not engine_name:
                    continue
                status = "installed" if eng.get("installed") else "not_installed"
                if eng.get("running"):
                    status = "running"
                mode = "native"  # Agent-reported engines are native discoveries
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
                        engine_name,
                        mode,
                        eng.get("version", ""),
                        eng.get("binary_path", ""),
                        status,
                        now,
                    ),
                )

            self._commit()

            # Check for queued quick_tests assigned to this agent
            commands: list[dict[str, Any]] = []
            rows = self._conn.execute(
                """SELECT id, command_id, model_path, engine_name, benchmark_name,
                          suite_name, engine_mode, profile_id
                   FROM quick_tests
                   WHERE agent_id = ? AND status = 'queued'
                   ORDER BY created_at
                   LIMIT 1""",
                (agent_id,),
            ).fetchall()

            for row in rows:
                test_id = row["id"]
                benchmark = row["benchmark_name"]
                # Determine command type from benchmark_name sentinel values.
                if row["engine_name"] == "cleanup":
                    cmd_type = "cleanup_storage"
                elif benchmark in (
                    "install_engine",
                    "start_engine",
                    "stop_engine",
                ):
                    cmd_type = benchmark
                else:
                    cmd_type = "run_test"
                payload: dict[str, Any] = {
                    "model_path": row["model_path"],
                    "engine_name": row["engine_name"],
                    "benchmark_name": row["benchmark_name"],
                    "suite_name": row["suite_name"],
                    "engine_mode": row["engine_mode"],
                    "profile_id": row["profile_id"],
                }
                # For engine commands, profile_id carries JSON runtime_config.
                if cmd_type in ("start_engine", "install_engine", "stop_engine"):
                    raw = row["profile_id"] or "{}"
                    try:
                        payload["runtime_config"] = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        payload["runtime_config"] = {}

                commands.append(
                    {
                        "command_id": row["command_id"],
                        "test_id": test_id,
                        "type": cmd_type,
                        "payload": payload,
                    }
                )
                # Mark as dispatched
                self._conn.execute(
                    "UPDATE quick_tests SET status = 'dispatched' WHERE id = ?",
                    (test_id,),
                )
                event_bus.publish(
                    "status",
                    test_id,
                    {"status": "dispatched", "test_id": test_id},
                )

            if commands:
                self._commit()
                logger.info(
                    "Dispatched %d command(s) to agent %s via heartbeat",
                    len(commands),
                    agent_id,
                )

        settings = self.get_agent_settings(agent_id)
        return {"ack": True, "commands": commands, "settings": settings}

    # Fields that must never appear in API responses.
    _SENSITIVE_FIELDS = {"token", "token_hash"}

    def _sanitize(self, row: dict[str, Any]) -> dict[str, Any]:
        """Strip sensitive fields from an agent dict before returning."""
        return {k: v for k, v in row.items() if k not in self._SENSITIVE_FIELDS}

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        """Get full agent details."""
        row = self._conn.execute(
            "SELECT * FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        if row is None:
            return None
        return self._sanitize(dict(row))

    def get_agent_by_name(self, name: str) -> dict[str, Any] | None:
        """Look up an agent by name (hostname).

        Unlike ``check_agent_auth_by_name`` (which returns success for
        nonexistent agents to allow first-time registration), this method
        returns ``None`` when no agent with the given name exists.
        """
        row = self._conn.execute(
            "SELECT * FROM agents WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return self._sanitize(dict(row))

    def list_agents(self) -> list[dict[str, Any]]:
        """List all registered agents."""
        self._check_stale_agents()
        rows = self._conn.execute("SELECT * FROM agents ORDER BY name").fetchall()
        return [self._sanitize(dict(r)) for r in rows]

    def delete_agent(self, agent_id: str) -> bool:
        """Remove an agent registration."""
        with self._write_lock:
            cursor = self._conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
            self._commit()
        return cursor.rowcount > 0

    def update_agent(self, agent_id: str, updates: dict[str, Any]) -> bool:
        """Update agent fields (notes, tags, etc.)."""
        allowed = {"notes", "tags"}
        to_set = {k: v for k, v in updates.items() if k in allowed}
        if not to_set:
            return False

        clauses = ", ".join(f"{k} = ?" for k in to_set)
        values = list(to_set.values()) + [agent_id]
        with self._write_lock:
            self._conn.execute(f"UPDATE agents SET {clauses} WHERE id = ?", values)
            self._commit()
        return True

    def verify_token(self, agent_id: str, token: str) -> bool:
        """Verify that a token matches the registered agent.

        Checks token_hash first (new hashed storage), falls back to
        legacy raw token column for backward compatibility.
        Returns True if the agent has no token configured (empty hash and token).
        """
        row = self._conn.execute(
            "SELECT token, token_hash FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        if row is None:
            return False

        stored_hash = row["token_hash"] or ""
        stored_raw = row["token"] or ""

        # No token configured on this agent — allow (dev/migration compat)
        if not stored_hash and not stored_raw:
            return True

        # Prefer hash-based verification
        if stored_hash:
            provided_hash = self._hash_token(token)
            return hmac.compare_digest(provided_hash, stored_hash)

        # Fall back to legacy raw token comparison
        return hmac.compare_digest(token, stored_raw)

    def check_agent_auth(
        self, agent_id: str, token: str
    ) -> tuple[bool, str | None, int]:
        """Check whether the agent exists and verify its token.

        Encapsulates the lookup + token verification pattern so API
        endpoints don't need to query _conn directly.

        Returns:
            (ok, error_message, http_status) — ok is True when the
            request should proceed.  On failure, error_message and
            http_status describe the problem.
        """
        row = self._conn.execute(
            "SELECT id, token_hash, token FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        if row is None:
            return False, "Agent not found", 404

        stored_hash = row["token_hash"] or ""
        stored_raw = row["token"] or ""

        if stored_hash or stored_raw:
            if not token:
                return False, "Missing authorization", 401
            if not self.verify_token(agent_id, token):
                return False, "Invalid token for this agent", 403

        return True, None, 0

    def check_agent_auth_by_name(
        self, name: str, token: str
    ) -> tuple[bool, str | None, int]:
        """Same as check_agent_auth but looks up the agent by name.

        Used by the register endpoint where only the agent name is known.
        Returns (ok, error_message, http_status).
        """
        row = self._conn.execute(
            "SELECT id, token_hash, token FROM agents WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            # Agent doesn't exist yet — no token to check
            return True, None, 0

        stored_hash = row["token_hash"] or ""
        stored_raw = row["token"] or ""

        if stored_hash or stored_raw:
            if not token:
                return False, "Missing authorization", 401
            if not self.verify_token(row["id"], token):
                return False, "Invalid token for this agent", 403

        return True, None, 0

    def rotate_token(self, agent_id: str) -> dict[str, Any] | None:
        """Generate a new token for an existing agent.

        Returns:
            Dict with raw token and prefix, or None if agent not found.
        """
        row = self._conn.execute(
            "SELECT id FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        if row is None:
            return None

        raw_token = secrets.token_hex(32)
        token_hash = self._hash_token(raw_token)
        token_prefix = raw_token[:8]

        with self._write_lock:
            self._conn.execute(
                "UPDATE agents SET token_hash = ?, token_prefix = ?, token = '' WHERE id = ?",
                (token_hash, token_prefix, agent_id),
            )
            self._commit()
        logger.info("Rotated token for agent %s", agent_id)

        return {"token": raw_token, "token_prefix": token_prefix}

    # --- Agent settings ---

    _DEFAULT_SETTINGS = {
        "model_storage_dir": "~/.kitt/models",
        "model_share_source": "",
        "model_share_mount": "",
        "auto_cleanup": "true",
        "heartbeat_interval_s": "30",
        "kitt_image": "",
    }

    def _ensure_default_settings(self, agent_id: str) -> None:
        """Insert default settings for an agent if they don't exist."""
        with self._write_lock:
            for key, value in self._DEFAULT_SETTINGS.items():
                self._conn.execute(
                    "INSERT OR IGNORE INTO agent_settings (agent_id, key, value) VALUES (?, ?, ?)",
                    (agent_id, key, value),
                )
            self._commit()

    def get_agent_settings(self, agent_id: str) -> dict[str, str]:
        """Get all settings for an agent as a flat dict."""
        rows = self._conn.execute(
            "SELECT key, value FROM agent_settings WHERE agent_id = ?",
            (agent_id,),
        ).fetchall()
        return {row["key"]: row["value"] for row in rows}

    def update_agent_settings(self, agent_id: str, updates: dict[str, str]) -> bool:
        """Upsert agent settings. Returns True if any rows were affected."""
        # Validate keys against known settings
        valid_keys = set(self._DEFAULT_SETTINGS.keys())
        filtered = {k: str(v) for k, v in updates.items() if k in valid_keys}
        if not filtered:
            return False

        with self._write_lock:
            for key, value in filtered.items():
                self._conn.execute(
                    """INSERT INTO agent_settings (agent_id, key, value)
                       VALUES (?, ?, ?)
                       ON CONFLICT(agent_id, key) DO UPDATE SET value = excluded.value""",
                    (agent_id, key, value),
                )
            self._commit()
        return True

    def queue_cleanup_command(self, agent_id: str, model_path: str = "") -> str:
        """Queue a cleanup_storage command for dispatch via heartbeat.

        Returns:
            The command ID for the queued cleanup.
        """
        command_id = uuid.uuid4().hex[:16]
        with self._write_lock:
            self._conn.execute(
                """INSERT INTO quick_tests
                   (id, agent_id, model_path, engine_name, benchmark_name,
                    suite_name, status, command_id)
                   VALUES (?, ?, ?, 'cleanup', 'cleanup_storage', 'quick', 'queued', ?)""",
                (command_id, agent_id, model_path or "__cleanup__", command_id),
            )
            self._commit()
        return command_id

    def queue_engine_command(
        self,
        agent_id: str,
        engine_name: str,
        command: str,
        runtime_config: dict[str, Any] | None = None,
        model_path: str = "",
    ) -> str:
        """Queue an engine lifecycle command for dispatch via heartbeat.

        Args:
            agent_id: Target agent.
            engine_name: Engine to operate on (ollama, llama_cpp, vllm).
            command: One of install_engine, start_engine, stop_engine.
            runtime_config: Optional runtime config (for start_engine).
            model_path: Optional model path (for start_engine).

        Returns:
            The command ID for the queued command.
        """
        command_id = uuid.uuid4().hex[:16]
        profile_id = ""
        if runtime_config:
            import json as _json

            profile_id = _json.dumps(runtime_config)
        with self._write_lock:
            self._conn.execute(
                """INSERT INTO quick_tests
                   (id, agent_id, model_path, engine_name, benchmark_name,
                    suite_name, status, command_id, engine_mode, profile_id)
                   VALUES (?, ?, ?, ?, ?, 'quick', 'queued', ?, 'native', ?)""",
                (
                    command_id,
                    agent_id,
                    model_path,
                    engine_name,
                    command,
                    command_id,
                    profile_id,
                ),
            )
            self._commit()
        return command_id

    def _check_stale_agents(self) -> None:
        """Mark agents as offline if heartbeat is stale.

        Test agents (tags contain "test") are always online and skipped.
        """
        with self._write_lock:
            rows = self._conn.execute(
                "SELECT id, last_heartbeat, tags FROM agents WHERE status != 'offline'"
            ).fetchall()

            now = time.time()
            for row in rows:
                # Skip test agents — they are always online
                raw_tags = row["tags"] or "[]"
                try:
                    tags = json.loads(raw_tags)
                except (json.JSONDecodeError, TypeError):
                    tags = []
                if "test" in tags:
                    continue

                if row["last_heartbeat"]:
                    try:
                        hb_time = datetime.fromisoformat(row["last_heartbeat"])
                        age = now - hb_time.timestamp()
                        if age > HEARTBEAT_TIMEOUT_S:
                            self._conn.execute(
                                "UPDATE agents SET status = 'offline' WHERE id = ?",
                                (row["id"],),
                            )
                    except (ValueError, OSError):
                        pass

            self._commit()
