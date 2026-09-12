"""Tests for JSON file-based result store."""

import pytest

from kitt.storage.json_store import JsonStore


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
    }


@pytest.fixture
def store(tmp_path):
    return JsonStore(base_dir=tmp_path)


class TestJsonStore:
    def test_save_and_get(self, store, tmp_path):
        result = _make_result()
        result_id = store.save_result(result)
        assert result_id
        # File should exist
        files = list(tmp_path.glob("kitt-results/**/metrics.json"))
        assert len(files) == 1

    def test_save_creates_directory_structure(self, store, tmp_path):
        store.save_result(_make_result(model="meta/llama-3.1"))
        dirs = list(tmp_path.glob("kitt-results/meta_llama-3.1/*"))
        assert len(dirs) >= 1

    def test_list_results(self, store):
        store.save_result(_make_result(model="model-a"))
        store.save_result(_make_result(model="model-b"))
        results = store.list_results()
        assert len(results) == 2
        models = {r["model"] for r in results}
        assert models == {"model-a", "model-b"}

    def test_list_results_fields(self, store):
        store.save_result(_make_result())
        results = store.list_results()
        assert len(results) == 1
        r = results[0]
        assert "id" in r
        assert "model" in r
        assert "engine" in r
        assert "suite_name" in r
        assert "timestamp" in r
        assert "passed" in r

    def test_query_no_filters(self, store):
        store.save_result(_make_result())
        results = store.query()
        assert len(results) == 1

    def test_query_with_model_filter(self, store):
        store.save_result(_make_result(model="model-a"))
        store.save_result(_make_result(model="model-b"))
        results = store.query(filters={"model": "model-a"})
        assert len(results) == 1
        assert results[0]["model"] == "model-a"

    def test_query_with_engine_filter(self, store):
        store.save_result(_make_result(engine="vllm"))
        store.save_result(_make_result(engine="tgi"))
        results = store.query(filters={"engine": "tgi"})
        assert len(results) == 1
        assert results[0]["engine"] == "tgi"

    def test_query_with_limit(self, store):
        for i in range(5):
            store.save_result(_make_result(model=f"model-{i}"))
        results = store.query(limit=3)
        assert len(results) == 3

    def test_query_with_offset(self, store):
        for i in range(5):
            store.save_result(_make_result(model=f"model-{i}"))
        all_results = store.query()
        offset_results = store.query(offset=2)
        assert len(offset_results) == len(all_results) - 2

    def test_query_order_by(self, store):
        store.save_result(_make_result(model="aaa"))
        store.save_result(_make_result(model="zzz"))
        results = store.query(order_by="model")
        assert results[0]["model"] == "aaa"
        results_desc = store.query(order_by="-model")
        assert results_desc[0]["model"] == "zzz"

    def test_count_all(self, store):
        assert store.count() == 0
        store.save_result(_make_result())
        assert store.count() == 1

    def test_count_with_filter(self, store):
        store.save_result(_make_result(engine="vllm"))
        store.save_result(_make_result(engine="tgi"))
        assert store.count({"engine": "vllm"}) == 1

    def test_aggregate_by_engine(self, store):
        store.save_result(_make_result(engine="vllm"))
        store.save_result(_make_result(engine="vllm"))
        store.save_result(_make_result(engine="tgi"))
        groups = store.aggregate("engine")
        engine_counts = {g["engine"]: g["count"] for g in groups}
        assert engine_counts["vllm"] == 2
        assert engine_counts["tgi"] == 1

    def test_aggregate_with_metrics(self, store):
        store.save_result(_make_result(engine="vllm"))
        groups = store.aggregate("engine", metrics=["avg_tps"])
        assert len(groups) >= 1
        assert "avg_tps_avg" in groups[0]

    def test_delete_result(self, store):
        store.save_result(_make_result())
        results = store.list_results()
        assert len(results) == 1
        deleted = store.delete_result(results[0]["id"])
        assert deleted
        assert store.count() == 0

    def test_delete_nonexistent(self, store):
        assert store.delete_result("nonexistent") is False

    def test_cache_invalidation(self, store):
        store.save_result(_make_result(model="first"))
        assert store.count() == 1
        store.save_result(_make_result(model="second"))
        assert store.count() == 2
