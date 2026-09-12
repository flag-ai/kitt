"""Tests for campaign results rollup."""

import json

from kitt.reporters.campaign_rollup import generate_campaign_rollup


def _make_result(model, engine, passed=True, metrics=None, time_s=10.0):
    return {
        "model": model,
        "engine": engine,
        "passed": passed,
        "total_time_seconds": time_s,
        "results": [
            {
                "test_name": "throughput",
                "metrics": metrics or {"avg_tps": 100.0},
            }
        ],
    }


class TestGenerateCampaignRollup:
    def test_empty_results(self):
        assert generate_campaign_rollup([]) == "No results to aggregate."

    def test_markdown_format(self):
        results = [
            _make_result("Qwen-7B", "vllm"),
            _make_result("Qwen-7B", "vllm", passed=False),
        ]
        output = generate_campaign_rollup(results, output_format="markdown")
        assert "# Campaign Results Rollup" in output
        assert "Qwen-7B" in output
        assert "vllm" in output

    def test_pass_fail_counts(self):
        results = [
            _make_result("m", "e", passed=True),
            _make_result("m", "e", passed=True),
            _make_result("m", "e", passed=False),
        ]
        output = generate_campaign_rollup(results)
        assert "2" in output  # 2 passed
        assert "1" in output  # 1 failed
        assert "3 runs" in output

    def test_grouping_by_model_engine(self):
        results = [
            _make_result("Qwen-7B", "vllm"),
            _make_result("Qwen-7B", "ollama"),
            _make_result("Llama-8B", "vllm"),
        ]
        output = generate_campaign_rollup(results)
        assert "Qwen-7B" in output
        assert "Llama-8B" in output
        assert "vllm" in output
        assert "ollama" in output

    def test_time_aggregation(self):
        results = [
            _make_result("m", "e", time_s=100.0),
            _make_result("m", "e", time_s=200.0),
        ]
        output = generate_campaign_rollup(results)
        assert "300s" in output

    def test_key_metrics_highlighted(self):
        results = [
            _make_result("m", "e", metrics={"avg_tps": 150.0, "avg_latency_ms": 42.0}),
        ]
        output = generate_campaign_rollup(results)
        assert "avg_tps" in output
        assert "avg_latency_ms" in output
        assert "150.00" in output

    def test_json_format(self):
        results = [
            _make_result("Qwen-7B", "vllm", metrics={"avg_tps": 100.0}),
            _make_result("Qwen-7B", "vllm", metrics={"avg_tps": 120.0}),
        ]
        output = generate_campaign_rollup(results, output_format="json")
        data = json.loads(output)

        key = "Qwen-7B|vllm"
        assert key in data
        assert data[key]["passed"] == 2
        assert data[key]["model"] == "Qwen-7B"
        assert data[key]["avg_metrics"]["throughput.avg_tps"] == 110.0

    def test_json_averaged_metrics(self):
        results = [
            _make_result("m", "e", metrics={"avg_tps": 80.0}),
            _make_result("m", "e", metrics={"avg_tps": 120.0}),
        ]
        output = generate_campaign_rollup(results, output_format="json")
        data = json.loads(output)
        assert data["m|e"]["avg_metrics"]["throughput.avg_tps"] == 100.0

    def test_pass_rate_in_markdown(self):
        results = [
            _make_result("m", "e", passed=True),
            _make_result("m", "e", passed=True),
            _make_result("m", "e", passed=True),
            _make_result("m", "e", passed=False),
        ]
        output = generate_campaign_rollup(results)
        assert "75% pass rate" in output

    def test_unknown_model_engine(self):
        results = [{"total_time_seconds": 5, "results": []}]
        output = generate_campaign_rollup(results)
        assert "unknown" in output
