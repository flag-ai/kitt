"""Tests for regression detection."""

from kitt.reporters.regression import RegressionAlert, RegressionDetector


def _make_result(metrics):
    return {
        "model": "Qwen-7B",
        "engine": "vllm",
        "results": [{"test_name": "throughput", "metrics": metrics}],
    }


class TestRegressionDetector:
    def test_no_regression(self):
        detector = RegressionDetector()
        baseline = _make_result({"avg_tps": 100.0})
        current = _make_result({"avg_tps": 105.0})

        alerts = detector.detect(baseline, current)
        assert alerts == []

    def test_throughput_regression_warning(self):
        detector = RegressionDetector(warning_threshold_pct=10.0)
        baseline = _make_result({"avg_tps": 100.0})
        current = _make_result({"avg_tps": 85.0})  # 15% drop

        alerts = detector.detect(baseline, current)
        assert len(alerts) == 1
        assert alerts[0].severity == "warning"
        assert alerts[0].metric == "avg_tps"
        assert alerts[0].delta_pct == 15.0

    def test_throughput_regression_critical(self):
        detector = RegressionDetector(critical_threshold_pct=25.0)
        baseline = _make_result({"avg_tps": 100.0})
        current = _make_result({"avg_tps": 70.0})  # 30% drop

        alerts = detector.detect(baseline, current)
        assert len(alerts) == 1
        assert alerts[0].severity == "critical"

    def test_latency_regression(self):
        detector = RegressionDetector(warning_threshold_pct=10.0)
        baseline = _make_result({"avg_latency_ms": 50.0})
        current = _make_result({"avg_latency_ms": 60.0})  # 20% increase

        alerts = detector.detect(baseline, current)
        assert len(alerts) == 1
        assert alerts[0].severity == "warning"
        assert alerts[0].metric == "avg_latency_ms"

    def test_latency_improvement_no_alert(self):
        detector = RegressionDetector()
        baseline = _make_result({"avg_latency_ms": 50.0})
        current = _make_result({"avg_latency_ms": 40.0})  # Improved

        alerts = detector.detect(baseline, current)
        assert alerts == []

    def test_below_threshold_no_alert(self):
        detector = RegressionDetector(warning_threshold_pct=10.0)
        baseline = _make_result({"avg_tps": 100.0})
        current = _make_result({"avg_tps": 95.0})  # Only 5% drop

        alerts = detector.detect(baseline, current)
        assert alerts == []

    def test_zero_baseline_skipped(self):
        detector = RegressionDetector()
        baseline = _make_result({"avg_tps": 0.0})
        current = _make_result({"avg_tps": 100.0})

        alerts = detector.detect(baseline, current)
        assert alerts == []

    def test_missing_baseline_metric(self):
        detector = RegressionDetector()
        baseline = _make_result({})
        current = _make_result({"avg_tps": 100.0})

        alerts = detector.detect(baseline, current)
        assert alerts == []

    def test_sorted_by_severity(self):
        detector = RegressionDetector(
            warning_threshold_pct=10.0,
            critical_threshold_pct=25.0,
        )
        baseline = _make_result({"avg_tps": 100.0, "accuracy": 90.0})
        current = _make_result({"avg_tps": 85.0, "accuracy": 60.0})

        alerts = detector.detect(baseline, current)
        assert len(alerts) == 2
        # Sorted by delta_pct descending
        assert alerts[0].delta_pct >= alerts[1].delta_pct

    def test_custom_metric_lists(self):
        detector = RegressionDetector(
            warning_threshold_pct=5.0,
            higher_is_better=["custom_score"],
            lower_is_better=["custom_latency"],
        )
        baseline = _make_result({"custom_score": 100.0, "custom_latency": 50.0})
        current = _make_result({"custom_score": 90.0, "custom_latency": 60.0})

        alerts = detector.detect(baseline, current)
        metrics = {a.metric for a in alerts}
        assert "custom_score" in metrics
        assert "custom_latency" in metrics

    def test_model_and_engine_from_current(self):
        detector = RegressionDetector(warning_threshold_pct=5.0)
        baseline = {
            "model": "old",
            "engine": "e",
            "results": [{"test_name": "t", "metrics": {"avg_tps": 100.0}}],
        }
        current = {
            "model": "Qwen-7B",
            "engine": "vllm",
            "results": [{"test_name": "t", "metrics": {"avg_tps": 80.0}}],
        }

        alerts = detector.detect(baseline, current)
        assert alerts[0].model == "Qwen-7B"
        assert alerts[0].engine == "vllm"


class TestRegressionAlert:
    def test_fields(self):
        alert = RegressionAlert(
            metric="avg_tps",
            model="Qwen-7B",
            engine="vllm",
            baseline_value=100.0,
            current_value=80.0,
            delta_pct=20.0,
            severity="warning",
        )
        assert alert.metric == "avg_tps"
        assert alert.baseline_value == 100.0
        assert alert.current_value == 80.0
