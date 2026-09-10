"""Tests for Jupyter notebook formatters."""

from kitt.jupyter.formatters import NotebookFormatter


class TestFormatResultsTable:
    def setup_method(self):
        self.formatter = NotebookFormatter()

    def test_with_results_returns_html_table(self):
        results = [
            {
                "model": "Llama-3.1-8B",
                "engine": "vllm",
                "passed": True,
                "timestamp": "2025-01-15T12:00:00Z",
            }
        ]
        html = self.formatter.format_results_table(results)
        assert "<table>" in html
        assert "Llama-3.1-8B" in html
        assert "vllm" in html
        assert "PASS" in html

    def test_empty_returns_no_results_message(self):
        html = self.formatter.format_results_table([])
        assert "No results to display" in html

    def test_includes_pass_fail_colors(self):
        results = [
            {
                "model": "m1",
                "engine": "e1",
                "passed": True,
                "timestamp": "2025-01-15T12:00:00Z",
            },
            {
                "model": "m2",
                "engine": "e2",
                "passed": False,
                "timestamp": "2025-01-15T12:00:00Z",
            },
        ]
        html = self.formatter.format_results_table(results)
        assert "color: green" in html
        assert "color: red" in html

    def test_includes_header_row(self):
        results = [
            {
                "model": "m1",
                "engine": "e1",
                "passed": True,
                "timestamp": "2025-01-15T12:00:00Z",
            },
        ]
        html = self.formatter.format_results_table(results)
        assert "<th>Model</th>" in html
        assert "<th>Engine</th>" in html
        assert "<th>Status</th>" in html
        assert "<th>Timestamp</th>" in html


class TestFormatComparison:
    def setup_method(self):
        self.formatter = NotebookFormatter()

    def test_with_matching_benchmarks(self):
        current = {
            "results": [
                {
                    "test_name": "mmlu",
                    "metrics": {"accuracy": 0.85, "throughput": 50.0},
                },
            ]
        }
        baseline = {
            "results": [
                {
                    "test_name": "mmlu",
                    "metrics": {"accuracy": 0.80, "throughput": 45.0},
                },
            ]
        }
        html = self.formatter.format_comparison(current, baseline)
        assert "<table>" in html
        assert "mmlu" in html
        assert "accuracy" in html

    def test_with_no_comparable_metrics(self):
        current = {
            "results": [
                {"test_name": "bench_a", "metrics": {"accuracy": 0.9}},
            ]
        }
        baseline = {
            "results": [
                {"test_name": "bench_b", "metrics": {"accuracy": 0.8}},
            ]
        }
        html = self.formatter.format_comparison(current, baseline)
        assert "No comparable metrics found" in html

    def test_comparison_shows_change_percentage(self):
        current = {
            "results": [
                {"test_name": "perf", "metrics": {"tps": 100.0}},
            ]
        }
        baseline = {
            "results": [
                {"test_name": "perf", "metrics": {"tps": 80.0}},
            ]
        }
        html = self.formatter.format_comparison(current, baseline)
        assert "%" in html


class TestFormatMetricsSummary:
    def setup_method(self):
        self.formatter = NotebookFormatter()

    def test_shows_model_engine_status(self):
        result = {
            "model": "Llama-3.1-8B",
            "engine": "vllm",
            "passed": True,
            "results": [],
        }
        html = self.formatter.format_metrics_summary(result)
        assert "Llama-3.1-8B" in html
        assert "vllm" in html
        assert "PASS" in html
        assert "color: green" in html

    def test_includes_benchmark_rows(self):
        result = {
            "model": "Llama-3.1-8B",
            "engine": "vllm",
            "passed": True,
            "results": [
                {
                    "test_name": "mmlu",
                    "metrics": {"accuracy": 0.85, "throughput": 50.0},
                },
                {"test_name": "gsm8k", "metrics": {"accuracy": 0.72}},
            ],
        }
        html = self.formatter.format_metrics_summary(result)
        assert "mmlu" in html
        assert "gsm8k" in html
        assert "<table>" in html

    def test_fail_status_shows_red(self):
        result = {
            "model": "model-x",
            "engine": "engine-y",
            "passed": False,
            "results": [],
        }
        html = self.formatter.format_metrics_summary(result)
        assert "FAIL" in html
        assert "color: red" in html
