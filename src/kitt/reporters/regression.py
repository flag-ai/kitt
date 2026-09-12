"""Regression detection for benchmark results."""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RegressionAlert:
    """A detected regression."""

    metric: str
    model: str
    engine: str
    baseline_value: float
    current_value: float
    delta_pct: float
    severity: str  # "warning", "critical"


class RegressionDetector:
    """Detect performance regressions by comparing against baselines.

    Compares current results against baseline results using configurable
    thresholds for different metric types.
    """

    def __init__(
        self,
        warning_threshold_pct: float = 10.0,
        critical_threshold_pct: float = 25.0,
        higher_is_better: list[str] | None = None,
        lower_is_better: list[str] | None = None,
    ) -> None:
        self.warning_threshold = warning_threshold_pct
        self.critical_threshold = critical_threshold_pct
        self.higher_is_better = set(
            higher_is_better
            or [
                "avg_tps",
                "accuracy",
                "max_tps",
                "min_tps",
            ]
        )
        self.lower_is_better = set(
            lower_is_better
            or [
                "avg_latency_ms",
                "p99_latency_ms",
                "p95_latency_ms",
                "total_latency_ms",
                "ttft_ms",
            ]
        )

    def detect(
        self,
        baseline: dict[str, Any],
        current: dict[str, Any],
    ) -> list[RegressionAlert]:
        """Compare current results against baseline and return regressions.

        Args:
            baseline: Baseline result dict.
            current: Current result dict.

        Returns:
            List of detected regressions.
        """
        model = current.get("model", "unknown")
        engine = current.get("engine", "unknown")
        alerts: list[RegressionAlert] = []

        baseline_metrics = self._collect_metrics(baseline)
        current_metrics = self._collect_metrics(current)

        for metric, current_val in current_metrics.items():
            baseline_val = baseline_metrics.get(metric)
            if baseline_val is None or baseline_val == 0:
                continue

            delta_pct = ((current_val - baseline_val) / abs(baseline_val)) * 100

            # Determine if this change is a regression
            is_regression = False
            if metric in self.higher_is_better and delta_pct < 0:
                is_regression = True
                delta_pct = abs(delta_pct)
            elif metric in self.lower_is_better and delta_pct > 0:
                is_regression = True

            if not is_regression:
                continue

            severity = self._classify_severity(abs(delta_pct))
            if severity:
                alerts.append(
                    RegressionAlert(
                        metric=metric,
                        model=model,
                        engine=engine,
                        baseline_value=baseline_val,
                        current_value=current_val,
                        delta_pct=round(delta_pct, 2),
                        severity=severity,
                    )
                )

        return sorted(alerts, key=lambda a: a.delta_pct, reverse=True)

    def _classify_severity(self, delta_pct: float) -> str | None:
        """Classify regression severity based on threshold."""
        if delta_pct >= self.critical_threshold:
            return "critical"
        if delta_pct >= self.warning_threshold:
            return "warning"
        return None

    def _collect_metrics(self, result: dict[str, Any]) -> dict[str, float]:
        """Collect all flat numeric metrics from a result."""
        metrics = {}
        for bench in result.get("results", []):
            for key, value in bench.get("metrics", {}).items():
                if isinstance(value, (int, float)):
                    metrics[key] = float(value)
        return metrics
