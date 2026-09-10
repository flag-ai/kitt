"""Tests for batch inference benchmark."""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from kitt.benchmarks.performance.batch_inference import BatchInferenceBenchmark


@dataclass
class MockMetrics:
    tps: float = 45.0
    total_latency_ms: float = 250.0
    ttft_ms: float = 50.0
    gpu_memory_peak_gb: float = 10.0
    gpu_memory_avg_gb: float = 8.0


@dataclass
class MockResult:
    output: str = "test output"
    metrics: MockMetrics = None
    prompt_tokens: int = 10
    completion_tokens: int = 50

    def __post_init__(self):
        if self.metrics is None:
            self.metrics = MockMetrics()


@pytest.fixture
def engine():
    mock = MagicMock()
    mock.generate.return_value = MockResult()
    return mock


@pytest.fixture
def bench():
    return BatchInferenceBenchmark()


class TestBatchInferenceBenchmark:
    def test_name_and_category(self, bench):
        assert bench.name == "batch_inference"
        assert bench.category == "performance"

    def test_basic_execution(self, bench, engine):
        config = {
            "concurrency_levels": [1, 2],
            "requests_per_level": 4,
        }
        result = bench._execute(engine, config)
        assert result.test_name == "batch_inference"
        assert result.passed

    def test_metrics_include_concurrency_levels(self, bench, engine):
        config = {
            "concurrency_levels": [1, 4],
            "requests_per_level": 2,
        }
        result = bench._execute(engine, config)
        assert "concurrency_levels_tested" in result.metrics
        assert "optimal_concurrency" in result.metrics

    def test_metrics_per_level(self, bench, engine):
        config = {
            "concurrency_levels": [1],
            "requests_per_level": 3,
        }
        result = bench._execute(engine, config)
        assert "throughput_at_1" in result.metrics
        assert "latency_at_1" in result.metrics

    def test_outputs_per_level(self, bench, engine):
        config = {
            "concurrency_levels": [1, 2],
            "requests_per_level": 2,
        }
        result = bench._execute(engine, config)
        assert len(result.outputs) == 2
        assert result.outputs[0]["concurrency"] == 1

    def test_handles_engine_failure(self, bench, engine):
        engine.generate.side_effect = RuntimeError("GPU OOM")
        config = {
            "concurrency_levels": [1],
            "requests_per_level": 2,
        }
        result = bench._execute(engine, config)
        assert len(result.errors) > 0

    def test_single_concurrency_level(self, bench, engine):
        config = {"concurrency_levels": [1], "requests_per_level": 1}
        result = bench._execute(engine, config)
        assert result.metrics.get("optimal_concurrency") == 1

    def test_custom_prompts(self, bench, engine):
        config = {
            "concurrency_levels": [1],
            "prompts": ["Custom prompt A", "Custom prompt B"],
            "requests_per_level": 2,
        }
        result = bench._execute(engine, config)
        assert result.passed

    def test_empty_concurrency_levels(self, bench, engine):
        config = {"concurrency_levels": [], "requests_per_level": 2}
        result = bench._execute(engine, config)
        assert result.metrics == {}

    def test_compute_aggregate_optimal(self, bench):
        level_metrics = {
            1: {"throughput_total_tps": 50},
            4: {"throughput_total_tps": 150},
            8: {"throughput_total_tps": 120},
        }
        agg = bench._compute_aggregate(level_metrics)
        assert agg["optimal_concurrency"] == 4
        assert agg["optimal_throughput_tps"] == 150

    def test_run_concurrent(self, bench, engine):
        results = bench._run_concurrent(
            engine,
            ["prompt1", "prompt2"],
            concurrency=2,
            num_requests=4,
            max_tokens=128,
            temperature=0.0,
        )
        assert len(results) == 4
        assert all(r["success"] for r in results)

    def test_run_concurrent_with_failures(self, bench, engine):
        engine.generate.side_effect = Exception("fail")
        results = bench._run_concurrent(
            engine,
            ["p"],
            concurrency=1,
            num_requests=2,
            max_tokens=128,
            temperature=0.0,
        )
        assert all(not r["success"] for r in results)
