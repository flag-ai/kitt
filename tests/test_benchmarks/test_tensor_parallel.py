"""Tests for tensor parallel benchmark."""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from kitt.benchmarks.performance.tensor_parallel import TensorParallelBenchmark


@dataclass
class MockMetrics:
    tps: float = 45.0
    total_latency_ms: float = 250.0


@dataclass
class MockResult:
    output: str = "test"
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
    return TensorParallelBenchmark()


class TestTensorParallelBenchmark:
    def test_name_and_category(self, bench):
        assert bench.name == "tensor_parallel"
        assert bench.category == "performance"

    def test_required_config(self, bench):
        assert "model_path" in bench.required_config()

    def test_skips_unavailable_gpu_counts(self, bench, engine):
        with patch.object(bench, "_detect_gpu_count", return_value=1):
            config = {
                "model_path": "/models/test",
                "tp_sizes": [1, 2, 4],
                "iterations": 2,
            }
            result = bench._execute(engine, config)
            # Should have skipped tp=2 and tp=4
            skipped = [o for o in result.outputs if o.get("skipped")]
            assert len(skipped) == 2

    def test_runs_available_tp_sizes(self, bench, engine):
        with patch.object(bench, "_detect_gpu_count", return_value=4):
            config = {
                "model_path": "/models/test",
                "tp_sizes": [1],
                "iterations": 2,
            }
            result = bench._execute(engine, config)
            assert result.passed
            assert "tps_tp1" in result.metrics

    def test_compute_scaling_empty(self, bench):
        metrics = bench._compute_scaling({})
        assert metrics == {}

    def test_compute_scaling_single(self, bench):
        tp_results = {
            1: {"avg_tps": 50, "avg_latency_ms": 200},
        }
        metrics = bench._compute_scaling(tp_results)
        assert metrics["tps_tp1"] == 50
        assert metrics["best_tp_size"] == 1

    def test_compute_scaling_with_speedup(self, bench):
        tp_results = {
            1: {"avg_tps": 50, "avg_latency_ms": 200},
            2: {"avg_tps": 90, "avg_latency_ms": 120},
        }
        metrics = bench._compute_scaling(tp_results)
        assert "speedup_tp2" in metrics
        assert "scaling_efficiency_tp2" in metrics
        assert metrics["speedup_tp2"] == 1.8

    def test_handles_engine_failure(self, bench, engine):
        engine.generate.side_effect = RuntimeError("OOM")
        with patch.object(bench, "_detect_gpu_count", return_value=1):
            config = {
                "model_path": "/models/test",
                "tp_sizes": [1],
                "iterations": 1,
            }
            result = bench._execute(engine, config)
            assert len(result.errors) > 0

    def test_detect_gpu_count_fallback(self, bench):
        with patch("kitt.hardware.detector.detect_gpu", return_value=None):
            assert bench._detect_gpu_count() == 1

    def test_detect_gpu_count_with_gpu(self, bench):
        mock_gpu = MagicMock()
        mock_gpu.count = 4
        with patch("kitt.hardware.detector.detect_gpu", return_value=mock_gpu):
            assert bench._detect_gpu_count() == 4
