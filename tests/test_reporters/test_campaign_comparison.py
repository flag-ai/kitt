"""Tests for cross-campaign comparison."""

from kitt.reporters.campaign_comparison import compare_campaigns


def _make_result(model, engine, metrics):
    return {
        "model": model,
        "engine": engine,
        "results": [
            {"test_name": "throughput", "metrics": metrics},
        ],
    }


class TestCompareCampaigns:
    def test_basic_delta(self):
        a = [_make_result("Qwen-7B", "vllm", {"avg_tps": 100.0})]
        b = [_make_result("Qwen-7B", "vllm", {"avg_tps": 120.0})]

        result = compare_campaigns(a, b)
        key = "Qwen-7B|vllm"
        assert key in result
        assert result[key]["in_a"] is True
        assert result[key]["in_b"] is True

        delta = result[key]["deltas"]["throughput.avg_tps"]
        assert delta["baseline"] == 100.0
        assert delta["comparison"] == 120.0
        assert delta["delta"] == 20.0
        assert delta["pct_change"] == 20.0

    def test_negative_delta(self):
        a = [_make_result("Qwen-7B", "vllm", {"avg_tps": 100.0})]
        b = [_make_result("Qwen-7B", "vllm", {"avg_tps": 80.0})]

        result = compare_campaigns(a, b)
        delta = result["Qwen-7B|vllm"]["deltas"]["throughput.avg_tps"]
        assert delta["delta"] == -20.0
        assert delta["pct_change"] == -20.0

    def test_only_in_baseline(self):
        a = [_make_result("Qwen-7B", "vllm", {"avg_tps": 100.0})]
        b = []

        result = compare_campaigns(a, b)
        assert result["Qwen-7B|vllm"]["in_a"] is True
        assert result["Qwen-7B|vllm"]["in_b"] is False
        assert result["Qwen-7B|vllm"]["note"] == "Only in baseline"

    def test_only_in_comparison(self):
        a = []
        b = [_make_result("Qwen-7B", "ollama", {"avg_tps": 90.0})]

        result = compare_campaigns(a, b)
        assert result["Qwen-7B|ollama"]["in_a"] is False
        assert result["Qwen-7B|ollama"]["in_b"] is True
        assert result["Qwen-7B|ollama"]["note"] == "Only in comparison"

    def test_multiple_models(self):
        a = [
            _make_result("Qwen-7B", "vllm", {"avg_tps": 100.0}),
            _make_result("Llama-8B", "ollama", {"avg_tps": 50.0}),
        ]
        b = [
            _make_result("Qwen-7B", "vllm", {"avg_tps": 110.0}),
            _make_result("Llama-8B", "ollama", {"avg_tps": 55.0}),
        ]

        result = compare_campaigns(a, b)
        assert len(result) == 2
        assert "Qwen-7B|vllm" in result
        assert "Llama-8B|ollama" in result

    def test_metric_filter(self):
        a = [_make_result("m", "e", {"avg_tps": 100.0, "avg_latency_ms": 50.0})]
        b = [_make_result("m", "e", {"avg_tps": 120.0, "avg_latency_ms": 40.0})]

        result = compare_campaigns(a, b, metric_keys=["avg_tps"])
        deltas = result["m|e"]["deltas"]
        assert "throughput.avg_tps" in deltas
        assert "throughput.avg_latency_ms" not in deltas

    def test_zero_baseline(self):
        a = [_make_result("m", "e", {"avg_tps": 0.0})]
        b = [_make_result("m", "e", {"avg_tps": 50.0})]

        result = compare_campaigns(a, b)
        delta = result["m|e"]["deltas"]["throughput.avg_tps"]
        assert delta["pct_change"] == 0  # Division by zero guarded

    def test_nested_metrics(self):
        a = [
            {
                "model": "m",
                "engine": "e",
                "results": [{"test_name": "t", "metrics": {"ttft_ms": {"avg": 40.0}}}],
            }
        ]
        b = [
            {
                "model": "m",
                "engine": "e",
                "results": [{"test_name": "t", "metrics": {"ttft_ms": {"avg": 50.0}}}],
            }
        ]

        result = compare_campaigns(a, b)
        assert "t.ttft_ms.avg" in result["m|e"]["deltas"]
