"""Tests for CI report formatter."""

import pytest

from kitt.ci.report_formatter import CIReportFormatter


@pytest.fixture
def formatter():
    return CIReportFormatter()


@pytest.fixture
def basic_results():
    return {
        "model": "meta-llama/Llama-3.1-8B-Instruct",
        "engine": "vllm",
        "passed": True,
        "results": [
            {
                "test_name": "throughput",
                "run_number": 1,
                "passed": True,
                "metrics": {"avg_tps": 45.67, "p99_latency": 120.5},
            },
            {
                "test_name": "mmlu",
                "run_number": 1,
                "passed": True,
                "metrics": {"accuracy": 0.65, "total_items": 100},
            },
        ],
        "total_time_seconds": 312.5,
    }


@pytest.fixture
def baseline_results():
    return {
        "model": "meta-llama/Llama-3.1-8B-Instruct",
        "engine": "vllm",
        "passed": True,
        "results": [
            {
                "test_name": "throughput",
                "run_number": 1,
                "passed": True,
                "metrics": {"avg_tps": 50.0, "p99_latency": 100.0},
            },
            {
                "test_name": "mmlu",
                "run_number": 1,
                "passed": True,
                "metrics": {"accuracy": 0.64, "total_items": 100},
            },
        ],
        "total_time_seconds": 290.0,
    }


class TestFormatSummary:
    def test_basic_output(self, formatter, basic_results):
        md = formatter.format_summary(basic_results)
        assert "## KITT Benchmark Results" in md
        assert "meta-llama/Llama-3.1-8B-Instruct" in md
        assert "vllm" in md
        assert "PASS" in md
        assert "throughput" in md
        assert "mmlu" in md
        assert "312.5s" in md

    def test_with_baseline_showing_regression(
        self, formatter, basic_results, baseline_results
    ):
        md = formatter.format_summary(basic_results, baseline=baseline_results)
        assert "## KITT Benchmark Results" in md
        # avg_tps dropped from 50.0 to 45.67 = -8.7%, should appear
        assert "Comparison vs Baseline" in md
        assert "avg_tps" in md

    def test_with_no_benchmarks(self, formatter):
        results = {
            "model": "test-model",
            "engine": "ollama",
            "passed": False,
            "results": [],
            "total_time_seconds": 0.0,
        }
        md = formatter.format_summary(results)
        assert "## KITT Benchmark Results" in md
        assert "test-model" in md
        assert "FAIL" in md
        assert "0.0s" in md


class TestFormatRegressionAlert:
    def test_with_regressions(self, formatter):
        regressions = [
            {
                "metric": "avg_tps",
                "current": 42.5,
                "baseline": 50.0,
                "change_pct": -15.0,
                "severity": "critical",
            },
            {
                "metric": "accuracy",
                "current": 0.55,
                "baseline": 0.65,
                "change_pct": -15.4,
                "severity": "warning",
            },
        ]
        md = formatter.format_regression_alert(regressions)
        assert "### Regressions Detected" in md
        assert "avg_tps" in md
        assert "critical" in md
        assert "accuracy" in md
        assert "warning" in md
        assert "-15.0%" in md

    def test_empty_list_returns_no_regressions(self, formatter):
        md = formatter.format_regression_alert([])
        assert md == "No regressions detected."


class TestFormatRegression:
    def test_with_significant_changes(self, formatter, basic_results, baseline_results):
        lines = formatter._format_regression(basic_results, baseline_results)
        text = "\n".join(lines)
        assert "Comparison vs Baseline" in text
        # avg_tps: 45.67 vs 50.0 = -8.7% (significant)
        assert "avg_tps" in text
        # p99_latency: 120.5 vs 100.0 = +20.5% (significant)
        assert "p99_latency" in text

    def test_with_no_significant_changes(self, formatter):
        current = {
            "results": [
                {
                    "test_name": "throughput",
                    "metrics": {"avg_tps": 50.0},
                },
            ],
        }
        baseline = {
            "results": [
                {
                    "test_name": "throughput",
                    "metrics": {"avg_tps": 49.5},
                },
            ],
        }
        lines = formatter._format_regression(current, baseline)
        text = "\n".join(lines)
        assert "No significant changes vs baseline." in text
