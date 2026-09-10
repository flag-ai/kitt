"""Tests for benchmark base classes."""

from datetime import datetime
from unittest.mock import MagicMock

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark, WarmupConfig
from kitt.engines.base import GenerationMetrics, GenerationResult


def _make_mock_engine():
    """Create a mock engine that returns predictable results."""
    engine = MagicMock()
    engine.generate.return_value = GenerationResult(
        output="test output",
        metrics=GenerationMetrics(
            ttft_ms=10.0,
            tps=50.0,
            total_latency_ms=100.0,
            gpu_memory_peak_gb=2.0,
            gpu_memory_avg_gb=1.5,
            timestamp=datetime.now(),
        ),
        prompt_tokens=5,
        completion_tokens=10,
    )
    return engine


class ConcreteBenchmark(LLMBenchmark):
    """Minimal concrete benchmark for testing."""

    name = "test_benchmark"
    version = "1.0.0"
    category = "performance"

    def _execute(self, engine, config):
        result = engine.generate(prompt="test", max_tokens=10)
        return BenchmarkResult(
            test_name=self.name,
            test_version=self.version,
            passed=True,
            metrics={"tps": result.metrics.tps},
            outputs=[{"output": result.output}],
        )


class TestWarmupConfig:
    def test_defaults(self):
        config = WarmupConfig()
        assert config.enabled is True
        assert config.iterations == 5

    def test_custom(self):
        config = WarmupConfig(enabled=False, iterations=0)
        assert config.enabled is False


class TestBenchmarkResult:
    def test_creation(self):
        result = BenchmarkResult(
            test_name="test",
            test_version="1.0.0",
            passed=True,
            metrics={"tps": 50.0},
            outputs=[],
        )
        assert result.test_name == "test"
        assert result.passed is True
        assert result.run_number == 1


class TestLLMBenchmark:
    def test_run_with_warmup(self):
        benchmark = ConcreteBenchmark()
        engine = _make_mock_engine()

        result = benchmark.run(engine, {"warmup": {"enabled": True, "iterations": 2}})

        assert result.passed is True
        assert len(result.warmup_times) == 2
        # 2 warmup + 1 actual = 3 calls
        assert engine.generate.call_count == 3

    def test_run_without_warmup(self):
        benchmark = ConcreteBenchmark()
        engine = _make_mock_engine()

        result = benchmark.run(engine, {"warmup": {"enabled": False}})

        assert result.passed is True
        assert result.warmup_times == []
        assert engine.generate.call_count == 1

    def test_warmup_handles_errors(self):
        benchmark = ConcreteBenchmark()
        engine = _make_mock_engine()

        # First warmup call fails, rest succeed
        engine.generate.side_effect = [
            Exception("warmup fail"),
            engine.generate.return_value,
            engine.generate.return_value,  # actual test
        ]

        result = benchmark.run(engine, {"warmup": {"enabled": True, "iterations": 2}})
        # One warmup succeeded, one failed
        assert len(result.warmup_times) == 1

    def test_validate_config(self):
        benchmark = ConcreteBenchmark()
        assert benchmark.validate_config({}) is True

    def test_required_config_default_empty(self):
        benchmark = ConcreteBenchmark()
        assert benchmark.required_config() == []
