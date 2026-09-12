"""Tests for SQLite result store."""

import json

import pytest

from kitt.storage.sqlite_store import SQLiteStore


def _make_result(model="llama-3.1", engine="vllm", passed=True, suite="standard"):
    return {
        "model": model,
        "engine": engine,
        "suite_name": suite,
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
                "metrics": {"avg_tps": 45.2, "avg_latency_ms": 250.0},
                "errors": [],
                "timestamp": "2025-01-15T10:30:00",
            }
        ],
        "system_info": {
            "gpu": {"model": "RTX 4090", "vram_gb": 24, "count": 1},
            "cpu": {"model": "i9-13900K", "cores": 24},
            "ram_gb": 64,
            "environment_type": "native_linux",
            "fingerprint": "rtx4090-24gb",
        },
    }


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.db"
    s = SQLiteStore(db_path=db_path)
    yield s
    s.close()


class TestSQLiteStore:
    def test_init_creates_database(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = SQLiteStore(db_path=db_path)
        assert db_path.exists()
        store.close()

    def test_save_and_get(self, store):
        result = _make_result()
        run_id = store.save_result(result)
        assert run_id
        retrieved = store.get_result(run_id)
        assert retrieved is not None
        assert retrieved["model"] == "llama-3.1"
        assert retrieved["engine"] == "vllm"

    def test_get_nonexistent(self, store):
        assert store.get_result("nonexistent") is None

    def test_list_results(self, store):
        store.save_result(_make_result(model="model-a"))
        store.save_result(_make_result(model="model-b"))
        results = store.list_results()
        assert len(results) == 2

    def test_list_results_order(self, store):
        store.save_result(_make_result(model="first"))
        store.save_result(_make_result(model="second"))
        results = store.list_results()
        # Default order is timestamp DESC
        assert len(results) == 2

    def test_query_no_filters(self, store):
        store.save_result(_make_result())
        results = store.query()
        assert len(results) == 1

    def test_query_filter_model(self, store):
        store.save_result(_make_result(model="model-a"))
        store.save_result(_make_result(model="model-b"))
        results = store.query(filters={"model": "model-a"})
        assert len(results) == 1
        assert results[0]["model"] == "model-a"

    def test_query_filter_engine(self, store):
        store.save_result(_make_result(engine="vllm"))
        store.save_result(_make_result(engine="tgi"))
        results = store.query(filters={"engine": "tgi"})
        assert len(results) == 1

    def test_query_filter_passed(self, store):
        store.save_result(_make_result(passed=True))
        store.save_result(_make_result(passed=False))
        results = store.query(filters={"passed": True})
        assert len(results) == 1
        assert results[0]["passed"] is True

    def test_query_limit(self, store):
        for i in range(10):
            store.save_result(_make_result(model=f"model-{i}"))
        results = store.query(limit=5)
        assert len(results) == 5

    def test_query_offset(self, store):
        for i in range(5):
            store.save_result(_make_result(model=f"model-{i}"))
        all_results = store.query()
        offset_results = store.query(offset=2)
        assert len(offset_results) == len(all_results) - 2

    def test_query_order_by_timestamp(self, store):
        store.save_result(_make_result(model="a"))
        store.save_result(_make_result(model="b"))
        results = store.query(order_by="-timestamp")
        assert len(results) == 2

    def test_count_all(self, store):
        assert store.count() == 0
        store.save_result(_make_result())
        assert store.count() == 1
        store.save_result(_make_result())
        assert store.count() == 2

    def test_count_with_filter(self, store):
        store.save_result(_make_result(engine="vllm"))
        store.save_result(_make_result(engine="tgi"))
        assert store.count({"engine": "vllm"}) == 1
        assert store.count({"engine": "tgi"}) == 1

    def test_aggregate_by_engine(self, store):
        store.save_result(_make_result(engine="vllm"))
        store.save_result(_make_result(engine="vllm"))
        store.save_result(_make_result(engine="tgi"))
        groups = store.aggregate("engine")
        engine_counts = {g["engine"]: g["count"] for g in groups}
        assert engine_counts["vllm"] == 2
        assert engine_counts["tgi"] == 1

    def test_aggregate_with_metrics(self, store):
        store.save_result(_make_result())
        groups = store.aggregate("engine", metrics=["avg_tps"])
        assert len(groups) == 1
        assert "avg_tps_avg" in groups[0]
        assert groups[0]["avg_tps_avg"] == pytest.approx(45.2)

    def test_aggregate_invalid_group_by(self, store):
        with pytest.raises(ValueError):
            store.aggregate("invalid_field")

    def test_delete_result(self, store):
        run_id = store.save_result(_make_result())
        assert store.count() == 1
        assert store.delete_result(run_id) is True
        assert store.count() == 0

    def test_delete_cascades(self, store):
        """Deleting a run should cascade to benchmarks and metrics."""
        run_id = store.save_result(_make_result())
        conn = store._get_conn()
        benchmarks = conn.execute(
            "SELECT COUNT(*) as cnt FROM benchmarks WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert benchmarks["cnt"] > 0
        store.delete_result(run_id)
        benchmarks = conn.execute(
            "SELECT COUNT(*) as cnt FROM benchmarks WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert benchmarks["cnt"] == 0

    def test_delete_nonexistent(self, store):
        assert store.delete_result("nonexistent") is False

    def test_hardware_info_stored(self, store):
        run_id = store.save_result(_make_result())
        conn = store._get_conn()
        hw = conn.execute(
            "SELECT * FROM hardware WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert hw is not None
        assert hw["gpu_model"] == "RTX 4090"
        assert hw["gpu_vram_gb"] == 24

    def test_import_json(self, store, tmp_path):
        json_path = tmp_path / "metrics.json"
        json_path.write_text(json.dumps(_make_result()))
        run_id = store.import_json(json_path)
        assert store.get_result(run_id) is not None

    def test_import_directory(self, store, tmp_path):
        results_dir = tmp_path / "kitt-results" / "model" / "vllm" / "run1"
        results_dir.mkdir(parents=True)
        (results_dir / "metrics.json").write_text(json.dumps(_make_result()))
        count = store.import_directory(tmp_path)
        assert count == 1
        assert store.count() == 1

    def test_export_result(self, store, tmp_path):
        run_id = store.save_result(_make_result())
        out_path = tmp_path / "export" / "result.json"
        result = store.export_result(run_id, out_path)
        assert result is not None
        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert data["model"] == "llama-3.1"

    def test_export_nonexistent(self, store, tmp_path):
        result = store.export_result("nope", tmp_path / "nope.json")
        assert result is None

    def test_close_and_reopen(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = SQLiteStore(db_path=db_path)
        store.save_result(_make_result())
        store.close()

        store2 = SQLiteStore(db_path=db_path)
        assert store2.count() == 1
        store2.close()
