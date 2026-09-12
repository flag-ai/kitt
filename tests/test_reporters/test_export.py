"""Tests for CSV and Parquet export."""

import csv

import pytest

from kitt.reporters.export import export_to_csv, flatten_result


@pytest.fixture
def sample_result():
    return {
        "model": "Qwen2.5-7B",
        "engine": "vllm",
        "suite_name": "quick",
        "timestamp": "2025-01-01T12:00:00",
        "kitt_version": "1.2.1",
        "results": [
            {
                "test_name": "throughput",
                "test_version": "1.0.0",
                "run_number": 1,
                "passed": True,
                "metrics": {
                    "avg_tps": 120.5,
                    "total_iterations": 5,
                    "ttft_ms": {"avg": 42.0, "p99": 55.0},
                },
            },
            {
                "test_name": "latency",
                "test_version": "1.0.0",
                "run_number": 1,
                "passed": True,
                "metrics": {
                    "avg_latency_ms": 85.3,
                },
            },
        ],
    }


class TestFlattenResult:
    def test_basic_flatten(self, sample_result):
        rows = flatten_result(sample_result)
        assert len(rows) == 2

    def test_base_fields_carried(self, sample_result):
        rows = flatten_result(sample_result)
        for row in rows:
            assert row["model"] == "Qwen2.5-7B"
            assert row["engine"] == "vllm"
            assert row["kitt_version"] == "1.2.1"

    def test_flat_metrics(self, sample_result):
        rows = flatten_result(sample_result)
        assert rows[0]["avg_tps"] == 120.5
        assert rows[0]["total_iterations"] == 5

    def test_nested_metrics_dot_notation(self, sample_result):
        rows = flatten_result(sample_result)
        assert rows[0]["ttft_ms.avg"] == 42.0
        assert rows[0]["ttft_ms.p99"] == 55.0

    def test_per_bench_fields(self, sample_result):
        rows = flatten_result(sample_result)
        assert rows[0]["test_name"] == "throughput"
        assert rows[1]["test_name"] == "latency"
        assert rows[0]["passed"] is True

    def test_empty_results(self):
        rows = flatten_result({"model": "m", "engine": "e", "results": []})
        assert rows == []


class TestExportToCsv:
    def test_csv_round_trip(self, sample_result, tmp_path):
        out = tmp_path / "results.csv"
        result_path = export_to_csv([sample_result], out)

        assert result_path == out
        assert out.exists()

        with open(out) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]["model"] == "Qwen2.5-7B"
        assert rows[0]["avg_tps"] == "120.5"

    def test_multiple_results(self, sample_result, tmp_path):
        result2 = {
            **sample_result,
            "model": "Llama-3-8B",
            "engine": "llama_cpp",
        }
        out = tmp_path / "combined.csv"
        export_to_csv([sample_result, result2], out)

        with open(out) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 4
        models = {r["model"] for r in rows}
        assert models == {"Qwen2.5-7B", "Llama-3-8B"}

    def test_empty_raises(self, tmp_path):
        out = tmp_path / "empty.csv"
        with pytest.raises(ValueError, match="No data"):
            export_to_csv([], out)

    def test_creates_parent_dirs(self, sample_result, tmp_path):
        out = tmp_path / "sub" / "dir" / "results.csv"
        export_to_csv([sample_result], out)
        assert out.exists()
