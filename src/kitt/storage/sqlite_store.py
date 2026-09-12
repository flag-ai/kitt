"""SQLite-based result store."""

import json
import logging
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from .base import ResultStore
from .migrations import (
    get_current_version_sqlite,
    run_migrations_sqlite,
    set_version_sqlite,
)
from .schema import SCHEMA_VERSION, SQLITE_SCHEMA

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".kitt" / "kitt.db"


class SQLiteStore(ResultStore):
    """Result store backed by a SQLite database."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            with self._lock:
                if self._conn is None:
                    self._conn = sqlite3.connect(
                        str(self.db_path),
                        check_same_thread=False,
                    )
                    self._conn.row_factory = sqlite3.Row
                    self._conn.execute("PRAGMA journal_mode=WAL")
                    self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _ensure_schema(self) -> None:
        conn = self._get_conn()
        current = get_current_version_sqlite(conn)
        if current == 0:
            conn.executescript(SQLITE_SCHEMA)
            set_version_sqlite(conn, 1)
            logger.info(f"Initialized SQLite database at {self.db_path}")
            current = 1
        if current < SCHEMA_VERSION:
            run_migrations_sqlite(conn, current)

    def save_result(self, result_data: dict[str, Any]) -> str:
        conn = self._get_conn()
        run_id = uuid.uuid4().hex[:16]

        conn.execute(
            """INSERT INTO runs
               (id, model, engine, suite_name, timestamp, passed,
                total_benchmarks, passed_count, failed_count,
                total_time_seconds, kitt_version, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                result_data.get("model", ""),
                result_data.get("engine", ""),
                result_data.get("suite_name", ""),
                result_data.get("timestamp", ""),
                1 if result_data.get("passed") else 0,
                result_data.get("total_benchmarks", 0),
                result_data.get("passed_count", 0),
                result_data.get("failed_count", 0),
                result_data.get("total_time_seconds", 0.0),
                result_data.get("kitt_version", ""),
                json.dumps(result_data, default=str),
            ),
        )

        # Insert benchmarks and metrics
        for bench in result_data.get("results", []):
            cursor = conn.execute(
                """INSERT INTO benchmarks
                   (run_id, test_name, test_version, run_number, passed, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    bench.get("test_name", ""),
                    bench.get("test_version", "1.0.0"),
                    bench.get("run_number", 1),
                    1 if bench.get("passed") else 0,
                    bench.get("timestamp", ""),
                ),
            )
            bench_id = cursor.lastrowid

            for metric_name, metric_value in bench.get("metrics", {}).items():
                if isinstance(metric_value, (int, float)):
                    conn.execute(
                        "INSERT INTO metrics (benchmark_id, metric_name, metric_value) VALUES (?, ?, ?)",
                        (bench_id, metric_name, float(metric_value)),
                    )

        # Insert hardware info if present
        system_info = result_data.get("system_info")
        if system_info:
            gpu = system_info.get("gpu") or {}
            cpu = system_info.get("cpu") or {}
            conn.execute(
                """INSERT INTO hardware
                   (run_id, gpu_model, gpu_vram_gb, gpu_count,
                    cpu_model, cpu_cores, ram_gb, environment_type, fingerprint)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    gpu.get("model"),
                    gpu.get("vram_gb"),
                    gpu.get("count", 1),
                    cpu.get("model"),
                    cpu.get("cores"),
                    system_info.get("ram_gb"),
                    system_info.get("environment_type"),
                    system_info.get("fingerprint"),
                ),
            )

        conn.commit()
        return run_id

    def get_result(self, result_id: str) -> dict[str, Any] | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id, raw_json FROM runs WHERE id = ?", (result_id,)
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row["raw_json"])
        data["id"] = row["id"]
        return data

    def query(
        self,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conn = self._get_conn()
        sql = "SELECT id, raw_json FROM runs"
        params: list[Any] = []

        if filters:
            clauses = []
            allowed_columns = {
                "model",
                "engine",
                "suite_name",
                "passed",
                "kitt_version",
            }
            for key, value in filters.items():
                if key not in allowed_columns:
                    continue
                if key == "passed":
                    clauses.append("passed = ?")
                    params.append(1 if value else 0)
                else:
                    # Safe: key is validated against allowed_columns whitelist above
                    clauses.append(f"{key} = ?")
                    params.append(value)
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)

        if order_by:
            desc = order_by.startswith("-")
            col = order_by.lstrip("-")
            allowed_order = {
                "timestamp",
                "model",
                "engine",
                "total_time_seconds",
                "suite_name",
            }
            if col in allowed_order:
                # Safe: col is validated against allowed_order whitelist above
                sql += f" ORDER BY {col} {'DESC' if desc else 'ASC'}"

        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        if offset > 0:
            if limit is None:
                sql += " LIMIT -1"
            sql += " OFFSET ?"
            params.append(offset)

        rows = conn.execute(sql, params).fetchall()
        results = []
        for row in rows:
            data = json.loads(row["raw_json"])
            data["id"] = row["id"]
            results.append(data)
        return results

    def list_results(self) -> list[dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT id, model, engine, suite_name, timestamp, passed
               FROM runs ORDER BY timestamp DESC"""
        ).fetchall()
        return [
            {
                "id": row["id"],
                "model": row["model"],
                "engine": row["engine"],
                "suite_name": row["suite_name"],
                "timestamp": row["timestamp"],
                "passed": bool(row["passed"]),
            }
            for row in rows
        ]

    def aggregate(
        self,
        group_by: str,
        metrics: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        conn = self._get_conn()
        allowed = {"model", "engine", "suite_name"}
        if group_by not in allowed:
            raise ValueError(f"group_by must be one of {allowed}")

        if metrics:
            # Join with benchmarks and metrics tables
            results: dict[str, dict[str, Any]] = {}
            # Safe: group_by is validated against allowed whitelist above
            rows = conn.execute(
                f"SELECT {group_by}, COUNT(*) as count FROM runs GROUP BY {group_by}"
            ).fetchall()

            for row in rows:
                key = row[group_by]
                results[key] = {group_by: key, "count": row["count"]}

            for metric_name in metrics:
                # Safe: group_by is validated against allowed whitelist above
                metric_rows = conn.execute(
                    f"""SELECT r.{group_by} as grp, AVG(m.metric_value) as avg_val
                        FROM metrics m
                        JOIN benchmarks b ON m.benchmark_id = b.id
                        JOIN runs r ON b.run_id = r.id
                        WHERE m.metric_name = ?
                        GROUP BY r.{group_by}""",
                    (metric_name,),
                ).fetchall()
                for mr in metric_rows:
                    key = mr["grp"]
                    if key in results:
                        results[key][f"{metric_name}_avg"] = mr["avg_val"]

            return list(results.values())
        else:
            # Safe: group_by is validated against allowed whitelist above
            rows = conn.execute(
                f"SELECT {group_by}, COUNT(*) as count FROM runs GROUP BY {group_by}"
            ).fetchall()
            return [{group_by: row[group_by], "count": row["count"]} for row in rows]

    def delete_result(self, result_id: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM runs WHERE id = ?", (result_id,))
        conn.commit()
        return cursor.rowcount > 0

    def count(self, filters: dict[str, Any] | None = None) -> int:
        conn = self._get_conn()
        sql = "SELECT COUNT(*) as cnt FROM runs"
        params: list[Any] = []

        if filters:
            clauses = []
            allowed = {"model", "engine", "suite_name", "passed"}
            for key, value in filters.items():
                if key not in allowed:
                    continue
                if key == "passed":
                    clauses.append("passed = ?")
                    params.append(1 if value else 0)
                else:
                    # Safe: key is validated against allowed whitelist above
                    clauses.append(f"{key} = ?")
                    params.append(value)
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)

        row = conn.execute(sql, params).fetchone()
        return row["cnt"]

    def import_json(self, json_path: Path) -> str:
        """Import a metrics.json file into the database.

        Returns:
            The run ID of the imported result.
        """
        with open(json_path) as f:
            data = json.load(f)
        return self.save_result(data)

    def import_directory(self, directory: Path) -> int:
        """Import all metrics.json files from a directory tree.

        Returns:
            Number of files imported.
        """
        count = 0
        for metrics_file in sorted(directory.glob("**/metrics.json")):
            try:
                self.import_json(metrics_file)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to import {metrics_file}: {e}")
        return count

    def export_result(self, result_id: str, output_path: Path) -> Path | None:
        """Export a result to a JSON file.

        Returns:
            Path to the created file, or None if result not found.
        """
        data = self.get_result(result_id)
        if data is None:
            return None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        return output_path

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
