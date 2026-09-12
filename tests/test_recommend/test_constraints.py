"""Tests for hardware constraints."""

from kitt.recommend.constraints import HardwareConstraints


def _make_result(
    engine="vllm",
    peak_vram_gb=8.0,
    avg_tps=50.0,
    accuracy=0.8,
    avg_latency_ms=100.0,
):
    """Helper to create a result dict with metrics."""
    return {
        "model": "test-model",
        "engine": engine,
        "metrics": {
            "peak_vram_gb": peak_vram_gb,
            "avg_tps": avg_tps,
            "accuracy": accuracy,
            "avg_latency_ms": avg_latency_ms,
        },
    }


class TestHardwareConstraintsMatches:
    def test_all_none_returns_true(self):
        constraints = HardwareConstraints()
        result = _make_result()
        assert constraints.matches(result) is True

    def test_max_vram_gb_filters_high_vram(self):
        constraints = HardwareConstraints(max_vram_gb=10.0)
        high_vram = _make_result(peak_vram_gb=16.0)
        low_vram = _make_result(peak_vram_gb=8.0)

        assert constraints.matches(high_vram) is False
        assert constraints.matches(low_vram) is True

    def test_min_throughput_tps_filters_low_throughput(self):
        constraints = HardwareConstraints(min_throughput_tps=40.0)
        slow = _make_result(avg_tps=20.0)
        fast = _make_result(avg_tps=60.0)

        assert constraints.matches(slow) is False
        assert constraints.matches(fast) is True

    def test_min_accuracy_filters_low_accuracy(self):
        constraints = HardwareConstraints(min_accuracy=0.7)
        low_acc = _make_result(accuracy=0.5)
        high_acc = _make_result(accuracy=0.85)

        assert constraints.matches(low_acc) is False
        assert constraints.matches(high_acc) is True

    def test_max_latency_ms_filters_high_latency(self):
        constraints = HardwareConstraints(max_latency_ms=150.0)
        high_lat = _make_result(avg_latency_ms=200.0)
        low_lat = _make_result(avg_latency_ms=100.0)

        assert constraints.matches(high_lat) is False
        assert constraints.matches(low_lat) is True

    def test_engine_filters_different_engine(self):
        constraints = HardwareConstraints(engine="vllm")
        vllm_result = _make_result(engine="vllm")
        tgi_result = _make_result(engine="tgi")

        assert constraints.matches(vllm_result) is True
        assert constraints.matches(tgi_result) is False

    def test_multiple_constraints_all_must_pass(self):
        constraints = HardwareConstraints(
            max_vram_gb=12.0,
            min_throughput_tps=30.0,
            min_accuracy=0.7,
        )
        good = _make_result(peak_vram_gb=8.0, avg_tps=50.0, accuracy=0.85)
        bad_vram = _make_result(peak_vram_gb=16.0, avg_tps=50.0, accuracy=0.85)
        bad_tps = _make_result(peak_vram_gb=8.0, avg_tps=10.0, accuracy=0.85)

        assert constraints.matches(good) is True
        assert constraints.matches(bad_vram) is False
        assert constraints.matches(bad_tps) is False

    def test_all_constraints_satisfied(self):
        constraints = HardwareConstraints(
            max_vram_gb=24.0,
            min_throughput_tps=20.0,
            min_accuracy=0.6,
            max_latency_ms=200.0,
            engine="vllm",
        )
        result = _make_result(
            engine="vllm",
            peak_vram_gb=16.0,
            avg_tps=50.0,
            accuracy=0.85,
            avg_latency_ms=100.0,
        )
        assert constraints.matches(result) is True
