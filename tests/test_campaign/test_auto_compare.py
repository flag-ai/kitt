"""Tests for auto-compare campaign results."""

import json

import pytest

from kitt.campaign.auto_compare import AutoComparer


@pytest.fixture
def comparer(tmp_path):
    return AutoComparer(results_dir=tmp_path)


def _write_metrics(tmp_path, subpath, data):
    """Helper to write a metrics.json file under kitt-results/."""
    full_path = tmp_path / "kitt-results" / subpath / "metrics.json"
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(json.dumps(data))


class TestCompareWithPrevious:
    def test_returns_none_when_no_baseline(self, comparer):
        current = {"model": "llama-8b", "engine": "vllm"}
        result = comparer.compare_with_previous(current, "test-campaign")
        assert result is None

    def test_returns_comparison_dict(self, comparer, tmp_path):
        # Write two results: older baseline and current
        _write_metrics(
            tmp_path,
            "llama-8b/vllm/2024-01-01",
            {
                "model": "llama-8b",
                "engine": "vllm",
                "timestamp": "2024-01-01T00:00:00",
                "results": [
                    {"test_name": "throughput", "metrics": {"avg_tps": 50.0}},
                ],
            },
        )
        _write_metrics(
            tmp_path,
            "llama-8b/vllm/2024-01-02",
            {
                "model": "llama-8b",
                "engine": "vllm",
                "timestamp": "2024-01-02T00:00:00",
                "results": [
                    {"test_name": "throughput", "metrics": {"avg_tps": 40.0}},
                ],
            },
        )

        current = {
            "model": "llama-8b",
            "engine": "vllm",
            "timestamp": "2024-01-02T00:00:00",
            "results": [
                {"test_name": "throughput", "metrics": {"avg_tps": 40.0}},
            ],
        }
        result = comparer.compare_with_previous(current, "test-campaign")
        assert result is not None
        assert result["model"] == "llama-8b"
        assert result["engine"] == "vllm"


class TestFindPreviousResult:
    def test_returns_none_for_no_matches(self, comparer):
        result = comparer._find_previous_result("llama-8b", "vllm")
        assert result is None

    def test_skips_current_returns_older(self, comparer, tmp_path):
        _write_metrics(
            tmp_path,
            "run1",
            {
                "model": "llama-8b",
                "engine": "vllm",
                "timestamp": "2024-01-01T00:00:00",
            },
        )
        _write_metrics(
            tmp_path,
            "run2",
            {
                "model": "llama-8b",
                "engine": "vllm",
                "timestamp": "2024-01-02T00:00:00",
            },
        )

        result = comparer._find_previous_result("llama-8b", "vllm")
        assert result is not None
        assert result["timestamp"] == "2024-01-01T00:00:00"


class TestCompare:
    def test_detects_regression_in_tps(self, comparer):
        current = {
            "model": "llama-8b",
            "engine": "vllm",
            "timestamp": "2024-01-02",
            "results": [
                {"test_name": "throughput", "metrics": {"avg_tps": 40.0}},
            ],
        }
        baseline = {
            "model": "llama-8b",
            "engine": "vllm",
            "timestamp": "2024-01-01",
            "results": [
                {"test_name": "throughput", "metrics": {"avg_tps": 50.0}},
            ],
        }
        result = comparer._compare(current, baseline)
        assert len(result["regressions"]) == 1
        reg = result["regressions"][0]
        assert reg["metric"] == "avg_tps"
        assert reg["change_pct"] < -5

    def test_detects_improvement_in_accuracy(self, comparer):
        current = {
            "model": "llama-8b",
            "engine": "vllm",
            "timestamp": "2024-01-02",
            "results": [
                {"test_name": "mmlu", "metrics": {"accuracy": 0.75}},
            ],
        }
        baseline = {
            "model": "llama-8b",
            "engine": "vllm",
            "timestamp": "2024-01-01",
            "results": [
                {"test_name": "mmlu", "metrics": {"accuracy": 0.65}},
            ],
        }
        result = comparer._compare(current, baseline)
        assert len(result["improvements"]) == 1
        imp = result["improvements"][0]
        assert imp["metric"] == "accuracy"
        assert imp["change_pct"] > 5

    def test_ignores_small_changes(self, comparer):
        current = {
            "model": "llama-8b",
            "engine": "vllm",
            "timestamp": "2024-01-02",
            "results": [
                {"test_name": "throughput", "metrics": {"avg_tps": 49.0}},
            ],
        }
        baseline = {
            "model": "llama-8b",
            "engine": "vllm",
            "timestamp": "2024-01-01",
            "results": [
                {"test_name": "throughput", "metrics": {"avg_tps": 50.0}},
            ],
        }
        result = comparer._compare(current, baseline)
        assert len(result["regressions"]) == 0
        assert len(result["improvements"]) == 0

    def test_handles_missing_benchmarks(self, comparer):
        current = {
            "model": "llama-8b",
            "engine": "vllm",
            "timestamp": "2024-01-02",
            "results": [
                {"test_name": "throughput", "metrics": {"avg_tps": 40.0}},
                {"test_name": "new_bench", "metrics": {"score": 0.9}},
            ],
        }
        baseline = {
            "model": "llama-8b",
            "engine": "vllm",
            "timestamp": "2024-01-01",
            "results": [
                {"test_name": "throughput", "metrics": {"avg_tps": 50.0}},
            ],
        }
        result = comparer._compare(current, baseline)
        # new_bench not in baseline, so only throughput compared
        assert len(result["regressions"]) == 1
        assert result["regressions"][0]["benchmark"] == "throughput"
