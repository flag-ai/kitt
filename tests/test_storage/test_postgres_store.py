"""Tests for PostgreSQL result store (mocked)."""

from unittest.mock import MagicMock, patch

import pytest


def _make_result(model="llama-3.1", engine="vllm", passed=True):
    return {
        "model": model,
        "engine": engine,
        "suite_name": "standard",
        "timestamp": "2025-01-15T10:30:00",
        "passed": passed,
        "total_benchmarks": 3,
        "passed_count": 3 if passed else 1,
        "failed_count": 0 if passed else 2,
        "total_time_seconds": 120.5,
        "kitt_version": "1.2.1",
        "results": [
            {
                "test_name": "throughput",
                "test_version": "1.0.0",
                "run_number": 1,
                "passed": True,
                "metrics": {"avg_tps": 45.2},
                "errors": [],
                "timestamp": "2025-01-15T10:30:00",
            }
        ],
    }


@pytest.fixture
def mock_psycopg2():
    with patch.dict("sys.modules", {"psycopg2": MagicMock()}):
        import sys

        mock_pg = sys.modules["psycopg2"]
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pg.connect.return_value = mock_conn

        # Schema version check returns 0 (new DB)
        mock_cursor.fetchone.return_value = (0,)

        yield mock_pg, mock_conn, mock_cursor


class TestPostgresStoreImport:
    def test_import_error_without_psycopg2(self):
        with patch.dict("sys.modules", {"psycopg2": None}):
            # Clear any cached imports
            import sys

            if "kitt.storage.postgres_store" in sys.modules:
                del sys.modules["kitt.storage.postgres_store"]
            with pytest.raises(ImportError, match="psycopg2"):
                from kitt.storage.postgres_store import PostgresStore

                PostgresStore("postgresql://localhost/test")


class TestPostgresStoreSaveResult:
    def test_save_calls_insert(self, mock_psycopg2):
        mock_pg, mock_conn, mock_cursor = mock_psycopg2

        import sys

        if "kitt.storage.postgres_store" in sys.modules:
            del sys.modules["kitt.storage.postgres_store"]

        from kitt.storage.postgres_store import PostgresStore

        store = PostgresStore.__new__(PostgresStore)
        store._conn = mock_conn

        # Mock version check for _ensure_schema
        mock_cursor.fetchone.return_value = (1,)

        result = _make_result()
        run_id = store.save_result(result)
        assert run_id
        assert mock_cursor.execute.called
        mock_conn.commit.assert_called()

    def test_save_inserts_benchmarks(self, mock_psycopg2):
        mock_pg, mock_conn, mock_cursor = mock_psycopg2
        import sys

        if "kitt.storage.postgres_store" in sys.modules:
            del sys.modules["kitt.storage.postgres_store"]

        from kitt.storage.postgres_store import PostgresStore

        store = PostgresStore.__new__(PostgresStore)
        store._conn = mock_conn

        mock_cursor.fetchone.return_value = (1,)

        store.save_result(_make_result())

        # Should have INSERT INTO runs, INSERT INTO benchmarks, INSERT INTO metrics
        insert_calls = [
            c
            for c in mock_cursor.execute.call_args_list
            if isinstance(c[0][0], str) and "INSERT" in c[0][0]
        ]
        assert len(insert_calls) >= 2  # runs + benchmarks + metrics


class TestPostgresStoreQuery:
    def test_query_no_filters(self, mock_psycopg2):
        mock_pg, mock_conn, mock_cursor = mock_psycopg2
        import json
        import sys

        if "kitt.storage.postgres_store" in sys.modules:
            del sys.modules["kitt.storage.postgres_store"]

        from kitt.storage.postgres_store import PostgresStore

        store = PostgresStore.__new__(PostgresStore)
        store._conn = mock_conn

        mock_cursor.fetchall.return_value = [(json.dumps(_make_result()),)]

        results = store.query()
        assert len(results) == 1
        assert results[0]["model"] == "llama-3.1"

    def test_query_with_filter(self, mock_psycopg2):
        mock_pg, mock_conn, mock_cursor = mock_psycopg2
        import sys

        if "kitt.storage.postgres_store" in sys.modules:
            del sys.modules["kitt.storage.postgres_store"]

        from kitt.storage.postgres_store import PostgresStore

        store = PostgresStore.__new__(PostgresStore)
        store._conn = mock_conn
        mock_cursor.fetchall.return_value = []

        store.query(filters={"model": "llama"})
        sql = mock_cursor.execute.call_args[0][0]
        assert "WHERE" in sql
        assert "model = %s" in sql

    def test_query_with_limit(self, mock_psycopg2):
        mock_pg, mock_conn, mock_cursor = mock_psycopg2
        import sys

        if "kitt.storage.postgres_store" in sys.modules:
            del sys.modules["kitt.storage.postgres_store"]

        from kitt.storage.postgres_store import PostgresStore

        store = PostgresStore.__new__(PostgresStore)
        store._conn = mock_conn
        mock_cursor.fetchall.return_value = []

        store.query(limit=10)
        sql = mock_cursor.execute.call_args[0][0]
        assert "LIMIT" in sql


class TestPostgresStoreListResults:
    def test_list_results(self, mock_psycopg2):
        mock_pg, mock_conn, mock_cursor = mock_psycopg2
        import sys

        if "kitt.storage.postgres_store" in sys.modules:
            del sys.modules["kitt.storage.postgres_store"]

        from kitt.storage.postgres_store import PostgresStore

        store = PostgresStore.__new__(PostgresStore)
        store._conn = mock_conn

        mock_cursor.fetchall.return_value = [
            ("id1", "llama", "vllm", "standard", "2025-01-15", True)
        ]

        results = store.list_results()
        assert len(results) == 1
        assert results[0]["model"] == "llama"


class TestPostgresStoreAggregate:
    def test_aggregate_by_engine(self, mock_psycopg2):
        mock_pg, mock_conn, mock_cursor = mock_psycopg2
        import sys

        if "kitt.storage.postgres_store" in sys.modules:
            del sys.modules["kitt.storage.postgres_store"]

        from kitt.storage.postgres_store import PostgresStore

        store = PostgresStore.__new__(PostgresStore)
        store._conn = mock_conn

        mock_cursor.fetchall.return_value = [("vllm", 5), ("tgi", 3)]

        groups = store.aggregate("engine")
        assert len(groups) == 2

    def test_aggregate_invalid_field(self, mock_psycopg2):
        mock_pg, mock_conn, mock_cursor = mock_psycopg2
        import sys

        if "kitt.storage.postgres_store" in sys.modules:
            del sys.modules["kitt.storage.postgres_store"]

        from kitt.storage.postgres_store import PostgresStore

        store = PostgresStore.__new__(PostgresStore)
        store._conn = mock_conn

        with pytest.raises(ValueError):
            store.aggregate("invalid")


class TestPostgresStoreDelete:
    def test_delete_result(self, mock_psycopg2):
        mock_pg, mock_conn, mock_cursor = mock_psycopg2
        import sys

        if "kitt.storage.postgres_store" in sys.modules:
            del sys.modules["kitt.storage.postgres_store"]

        from kitt.storage.postgres_store import PostgresStore

        store = PostgresStore.__new__(PostgresStore)
        store._conn = mock_conn

        mock_cursor.rowcount = 1

        assert store.delete_result("some-id") is True
        mock_conn.commit.assert_called()


class TestPostgresStoreCount:
    def test_count(self, mock_psycopg2):
        mock_pg, mock_conn, mock_cursor = mock_psycopg2
        import sys

        if "kitt.storage.postgres_store" in sys.modules:
            del sys.modules["kitt.storage.postgres_store"]

        from kitt.storage.postgres_store import PostgresStore

        store = PostgresStore.__new__(PostgresStore)
        store._conn = mock_conn

        mock_cursor.fetchone.return_value = (42,)

        assert store.count() == 42

    def test_count_with_filter(self, mock_psycopg2):
        mock_pg, mock_conn, mock_cursor = mock_psycopg2
        import sys

        if "kitt.storage.postgres_store" in sys.modules:
            del sys.modules["kitt.storage.postgres_store"]

        from kitt.storage.postgres_store import PostgresStore

        store = PostgresStore.__new__(PostgresStore)
        store._conn = mock_conn

        mock_cursor.fetchone.return_value = (5,)

        result = store.count(filters={"engine": "vllm"})
        assert result == 5
        sql = mock_cursor.execute.call_args[0][0]
        assert "WHERE" in sql


class TestPostgresStoreClose:
    def test_close(self, mock_psycopg2):
        mock_pg, mock_conn, mock_cursor = mock_psycopg2
        import sys

        if "kitt.storage.postgres_store" in sys.modules:
            del sys.modules["kitt.storage.postgres_store"]

        from kitt.storage.postgres_store import PostgresStore

        store = PostgresStore.__new__(PostgresStore)
        store._conn = mock_conn

        store.close()
        mock_conn.close.assert_called_once()
