"""PostgreSQL-based result store (optional dependency)."""

import json
import logging
import uuid
from typing import Any

from .base import ResultStore
from .migrations import (
    get_current_version_postgres,
    run_migrations_postgres,
    set_version_postgres,
)
from .schema import POSTGRES_SCHEMA, SCHEMA_VERSION

logger = logging.getLogger(__name__)


class PostgresStore(ResultStore):
    """Result store backed by PostgreSQL.

    Requires psycopg2: pip install psycopg2-binary
    """

    def __init__(self, dsn: str) -> None:
        """Initialize with a PostgreSQL connection string.

        Args:
            dsn: Connection string, e.g. "postgresql://user:pass@host/dbname"
        """
        try:
            import psycopg2
        except ImportError:
            raise ImportError(
                "psycopg2 is required for PostgreSQL storage. "
                "Install with: pip install psycopg2-binary"
            ) from None

        self._conn = psycopg2.connect(dsn)
        self._conn.autocommit = False
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        current = get_current_version_postgres(self._conn)
        if current == 0:
            cursor = self._conn.cursor()
            cursor.execute(POSTGRES_SCHEMA)
            self._conn.commit()
            set_version_postgres(self._conn, SCHEMA_VERSION)
            logger.info("Initialized PostgreSQL schema")
        elif current < SCHEMA_VERSION:
            run_migrations_postgres(self._conn, current)

    def save_result(self, result_data: dict[str, Any]) -> str:
        run_id = uuid.uuid4().hex[:16]
        cursor = self._conn.cursor()

        cursor.execute(
            """INSERT INTO runs
               (id, model, engine, suite_name, timestamp, passed,
                total_benchmarks, passed_count, failed_count,
                total_time_seconds, kitt_version, raw_json)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                run_id,
                result_data.get("model", ""),
                result_data.get("engine", ""),
                result_data.get("suite_name", ""),
                result_data.get("timestamp", ""),
                result_data.get("passed", False),
                result_data.get("total_benchmarks", 0),
                result_data.get("passed_count", 0),
                result_data.get("failed_count", 0),
                result_data.get("total_time_seconds", 0.0),
                result_data.get("kitt_version", ""),
                json.dumps(result_data, default=str),
            ),
        )

        for bench in result_data.get("results", []):
            cursor.execute(
                """INSERT INTO benchmarks
                   (run_id, test_name, test_version, run_number, passed, timestamp)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (
                    run_id,
                    bench.get("test_name", ""),
                    bench.get("test_version", "1.0.0"),
                    bench.get("run_number", 1),
                    bench.get("passed", False),
                    bench.get("timestamp", ""),
                ),
            )
            bench_id = cursor.fetchone()[0]

            for metric_name, metric_value in bench.get("metrics", {}).items():
                if isinstance(metric_value, (int, float)):
                    cursor.execute(
                        "INSERT INTO metrics (benchmark_id, metric_name, metric_value) VALUES (%s, %s, %s)",
                        (bench_id, metric_name, float(metric_value)),
                    )

        system_info = result_data.get("system_info")
        if system_info:
            gpu = system_info.get("gpu") or {}
            cpu = system_info.get("cpu") or {}
            cursor.execute(
                """INSERT INTO hardware
                   (run_id, gpu_model, gpu_vram_gb, gpu_count,
                    cpu_model, cpu_cores, ram_gb, environment_type, fingerprint)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
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

        self._conn.commit()
        return run_id

    def get_result(self, result_id: str) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT raw_json FROM runs WHERE id = %s", (result_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def query(
        self,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        sql = "SELECT raw_json FROM runs"
        params: list[Any] = []

        if filters:
            clauses = []
            allowed = {"model", "engine", "suite_name", "passed", "kitt_version"}
            for key, value in filters.items():
                if key not in allowed:
                    continue
                # Safe: key is validated against allowed whitelist above
                clauses.append(f"{key} = %s")
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
            sql += " LIMIT %s"
            params.append(limit)

        if offset > 0:
            sql += " OFFSET %s"
            params.append(offset)

        cursor.execute(sql, params)
        return [json.loads(row[0]) for row in cursor.fetchall()]

    def list_results(self) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT id, model, engine, suite_name, timestamp, passed FROM runs ORDER BY timestamp DESC"
        )
        return [
            {
                "id": row[0],
                "model": row[1],
                "engine": row[2],
                "suite_name": row[3],
                "timestamp": row[4],
                "passed": row[5],
            }
            for row in cursor.fetchall()
        ]

    def aggregate(
        self,
        group_by: str,
        metrics: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        allowed = {"model", "engine", "suite_name"}
        if group_by not in allowed:
            raise ValueError(f"group_by must be one of {allowed}")

        if metrics:
            results: dict[str, dict[str, Any]] = {}
            # Safe: group_by is validated against allowed whitelist above
            cursor.execute(f"SELECT {group_by}, COUNT(*) FROM runs GROUP BY {group_by}")
            for row in cursor.fetchall():
                results[row[0]] = {group_by: row[0], "count": row[1]}

            for metric_name in metrics:
                # Safe: group_by is validated against allowed whitelist above
                cursor.execute(
                    f"""SELECT r.{group_by}, AVG(m.metric_value)
                        FROM metrics m
                        JOIN benchmarks b ON m.benchmark_id = b.id
                        JOIN runs r ON b.run_id = r.id
                        WHERE m.metric_name = %s
                        GROUP BY r.{group_by}""",
                    (metric_name,),
                )
                for row in cursor.fetchall():
                    if row[0] in results:
                        results[row[0]][f"{metric_name}_avg"] = row[1]

            return list(results.values())
        else:
            # Safe: group_by is validated against allowed whitelist above
            cursor.execute(f"SELECT {group_by}, COUNT(*) FROM runs GROUP BY {group_by}")
            return [{group_by: row[0], "count": row[1]} for row in cursor.fetchall()]

    def delete_result(self, result_id: str) -> bool:
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM runs WHERE id = %s", (result_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self, filters: dict[str, Any] | None = None) -> int:
        cursor = self._conn.cursor()
        sql = "SELECT COUNT(*) FROM runs"
        params: list[Any] = []

        if filters:
            clauses = []
            allowed = {"model", "engine", "suite_name", "passed"}
            for key, value in filters.items():
                if key not in allowed:
                    continue
                # Safe: key is validated against allowed whitelist above
                clauses.append(f"{key} = %s")
                params.append(value)
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)

        cursor.execute(sql, params)
        return cursor.fetchone()[0]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
