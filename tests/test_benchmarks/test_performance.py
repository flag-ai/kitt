"""Tests for performance benchmark implementations."""

from datetime import datetime
from unittest.mock import MagicMock

from kitt.benchmarks.performance.latency import LatencyBenchmark
from kitt.benchmarks.performance.memory import MemoryBenchmark
from kitt.benchmarks.performance.throughput import ThroughputBenchmark
from kitt.benchmarks.performance.warmup_analysis import WarmupAnalysisBenchmark
from kitt.engines.base import GenerationMetrics, GenerationResult


def _mock_engine(tps=50.0, latency_ms=100.0, ttft_ms=10.0, tokens=20):
    """Create a mock engine with configurable metrics."""
    engine = MagicMock()
    engine.generate.return_value = GenerationResult(
        output="This is a test output with some tokens.",
        metrics=GenerationMetrics(
            ttft_ms=ttft_ms,
            tps=tps,
            total_latency_ms=latency_ms,
            gpu_memory_peak_gb=4.0,
            gpu_memory_avg_gb=3.5,
            timestamp=datetime.now(),
        ),
        prompt_tokens=15,
        completion_tokens=tokens,
    )
    return engine


class TestLatencyBenchmark:
    def test_registration(self):
        assert LatencyBenchmark.name == "latency"
        assert LatencyBenchmark.category == "performance"

    def test_basic_run(self):
        bench = LatencyBenchmark()
        engine = _mock_engine(ttft_ms=15.0, latency_ms=200.0)
        config = {"iterations": 3, "max_tokens": 64}

        result = bench._execute(engine, config)

        assert result.test_name == "latency"
        assert result.passed is True
        assert len(result.outputs) == 3
        assert "ttft_ms" in result.metrics
        assert result.metrics["ttft_ms"]["avg"] == 15.0

    def test_latency_metrics_structure(self):
        bench = LatencyBenchmark()
        engine = _mock_engine()
        result = bench._execute(engine, {"iterations": 5})

        assert "total_iterations" in result.metrics
        assert result.metrics["total_iterations"] == 5

        ttft = result.metrics["ttft_ms"]
        assert all(k in ttft for k in ["avg", "min", "max", "p50", "p95", "p99"])

    def test_handles_errors(self):
        bench = LatencyBenchmark()
        engine = MagicMock()
        engine.generate.side_effect = RuntimeError("GPU OOM")
        result = bench._execute(engine, {"iterations": 2})

        assert result.passed is False
        assert len(result.errors) == 2


class TestMemoryBenchmark:
    def test_registration(self):
        assert MemoryBenchmark.name == "memory_usage"
        assert MemoryBenchmark.category == "performance"

    def test_basic_run(self):
        bench = MemoryBenchmark()
        engine = _mock_engine()
        config = {"output_lengths": [32, 128]}

        result = bench._execute(engine, config)

        assert result.test_name == "memory_usage"
        assert result.passed is True
        # 3 prompts * 2 output_lengths = 6 measurements
        assert len(result.outputs) == 6

    def test_memory_metrics_structure(self):
        bench = MemoryBenchmark()
        engine = _mock_engine()
        result = bench._execute(engine, {"output_lengths": [64]})

        metrics = result.metrics
        assert "overall_peak_gpu_memory_gb" in metrics
        assert "overall_avg_gpu_memory_gb" in metrics
        assert "per_prompt_peak_gb" in metrics
        assert "short" in metrics["per_prompt_peak_gb"]


class TestWarmupAnalysisBenchmark:
    def test_registration(self):
        assert WarmupAnalysisBenchmark.name == "warmup_analysis"
        assert WarmupAnalysisBenchmark.category == "performance"

    def test_basic_run(self):
        bench = WarmupAnalysisBenchmark()
        engine = _mock_engine()
        config = {
            "test_config": {"iterations": 5},
            "sampling": {"max_tokens": 50},
        }

        result = bench._execute(engine, config)

        assert result.test_name == "warmup_analysis"
        assert result.passed is True
        assert len(result.outputs) == 5

    def test_warmup_metrics(self):
        bench = WarmupAnalysisBenchmark()
        engine = _mock_engine(latency_ms=200.0)
        config = {"test_config": {"iterations": 5}}

        result = bench._execute(engine, config)

        metrics = result.metrics
        assert "first_iteration_latency_ms" in metrics
        assert "subsequent_avg_latency_ms" in metrics
        assert "latency_reduction_percent" in metrics
        assert "per_iteration_latencies_ms" in metrics
        assert len(metrics["per_iteration_latencies_ms"]) == 5

    def test_handles_errors(self):
        bench = WarmupAnalysisBenchmark()
        engine = MagicMock()
        engine.generate.side_effect = RuntimeError("Engine crashed")
        config = {"test_config": {"iterations": 3}}

        result = bench._execute(engine, config)
        assert result.passed is False
        assert len(result.errors) == 3


class TestThroughputBenchmark:
    """Additional tests for existing throughput benchmark."""

    def test_basic_run(self):
        bench = ThroughputBenchmark()
        engine = _mock_engine(tps=75.0, tokens=30)
        config = {"iterations": 3, "max_tokens": 128}

        result = bench._execute(engine, config)

        assert result.test_name == "throughput"
        assert result.passed is True
        assert result.metrics["avg_tps"] == 75.0
        assert result.metrics["total_iterations"] == 3
