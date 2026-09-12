"""Tests for speculative decoding benchmark."""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from kitt.benchmarks.performance.speculative import SpeculativeDecodingBenchmark


@dataclass
class MockMetrics:
    tps: float = 45.0
    total_latency_ms: float = 250.0


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
    return SpeculativeDecodingBenchmark()


class TestSpeculativeDecodingBenchmark:
    def test_name_and_category(self, bench):
        assert bench.name == "speculative_decoding"
        assert bench.category == "performance"

    def test_required_config(self, bench):
        assert "model_path" in bench.required_config()

    def test_baseline_only(self, bench, engine):
        config = {
            "model_path": "/models/test",
            "iterations": 2,
        }
        result = bench._execute(engine, config)
        assert result.passed
        assert "baseline_avg_tps" in result.metrics
        assert "speculative_avg_tps" not in result.metrics

    def test_with_speculative_model(self, bench, engine):
        config = {
            "model_path": "/models/test",
            "speculative_model": "/models/draft",
            "iterations": 2,
        }
        result = bench._execute(engine, config)
        assert "baseline_avg_tps" in result.metrics
        assert "speculative_avg_tps" in result.metrics
        assert "speedup_ratio" in result.metrics

    def test_outputs_include_modes(self, bench, engine):
        config = {
            "model_path": "/models/test",
            "speculative_model": "/models/draft",
            "iterations": 2,
        }
        result = bench._execute(engine, config)
        modes = [o["mode"] for o in result.outputs]
        assert "baseline" in modes
        assert "speculative" in modes

    def test_handles_speculative_failure(self, bench, engine):
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 3:
                raise RuntimeError("Spec decode fail")
            return MockResult()

        engine.generate.side_effect = side_effect
        config = {
            "model_path": "/models/test",
            "speculative_model": "/models/draft",
            "iterations": 5,
        }
        result = bench._execute(engine, config)
        assert "baseline_avg_tps" in result.metrics

    def test_run_iterations(self, bench, engine):
        result = bench._run_iterations(engine, "test prompt", 128, 0.0, 3)
        assert len(result["errors"]) == 0
        assert result["stats"]["iterations"] == 3
        assert result["stats"]["avg_tps"] == 45.0

    def test_run_iterations_with_failure(self, bench, engine):
        engine.generate.side_effect = Exception("fail")
        result = bench._run_iterations(engine, "test", 128, 0.0, 2)
        assert len(result["errors"]) == 2

    def test_compute_metrics_baseline_only(self, bench):
        baseline = {"stats": {"avg_tps": 50, "avg_latency_ms": 200}, "outputs": []}
        metrics = bench._compute_metrics(baseline, None)
        assert metrics["baseline_avg_tps"] == 50
        assert "speedup_ratio" not in metrics

    def test_compute_metrics_with_speculative(self, bench):
        baseline = {"stats": {"avg_tps": 50, "avg_latency_ms": 200}, "outputs": ["a"]}
        speculative = {
            "stats": {"avg_tps": 75, "avg_latency_ms": 140},
            "outputs": ["a"],
        }
        metrics = bench._compute_metrics(baseline, speculative)
        assert metrics["speedup_ratio"] == 1.5
        assert metrics["output_match_rate"] == 1.0

    def test_speedup_ratio_zero_baseline(self, bench):
        baseline = {"stats": {"avg_tps": 0}, "outputs": []}
        speculative = {"stats": {"avg_tps": 50}, "outputs": []}
        metrics = bench._compute_metrics(baseline, speculative)
        assert metrics["speedup_ratio"] == 0
