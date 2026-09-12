"""Auto-compare campaign runs with previous results."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AutoComparer:
    """Compare campaign results with previous runs automatically."""

    def __init__(self, results_dir: Path | None = None) -> None:
        self.results_dir = results_dir or Path.cwd()

    def compare_with_previous(
        self,
        current_result: dict[str, Any],
        campaign_name: str,
    ) -> dict[str, Any] | None:
        """Compare current result with the most recent previous run.

        Args:
            current_result: Current suite result dict.
            campaign_name: Campaign name for filtering.

        Returns:
            Comparison dict or None if no baseline found.
        """
        baseline = self._find_previous_result(
            current_result.get("model", ""),
            current_result.get("engine", ""),
        )
        if baseline is None:
            logger.debug("No baseline found for comparison")
            return None

        return self._compare(current_result, baseline)

    def _find_previous_result(self, model: str, engine: str) -> dict[str, Any] | None:
        """Find the most recent result for the same model/engine combo."""
        candidates = []
        for metrics_file in self.results_dir.glob("kitt-results/**/metrics.json"):
            try:
                data = json.loads(metrics_file.read_text())
                if data.get("model") == model and data.get("engine") == engine:
                    candidates.append((data.get("timestamp", ""), data))
            except Exception:
                continue

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        # Return second most recent (skip current)
        return candidates[1][1] if len(candidates) > 1 else None

    def _compare(
        self,
        current: dict[str, Any],
        baseline: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare two result sets."""
        comparison: dict[str, Any] = {
            "model": current.get("model"),
            "engine": current.get("engine"),
            "current_timestamp": current.get("timestamp"),
            "baseline_timestamp": baseline.get("timestamp"),
            "regressions": [],
            "improvements": [],
        }

        curr_benchmarks = {b["test_name"]: b for b in current.get("results", [])}
        base_benchmarks = {b["test_name"]: b for b in baseline.get("results", [])}

        for name, curr in curr_benchmarks.items():
            if name not in base_benchmarks:
                continue
            base = base_benchmarks[name]
            curr_metrics = curr.get("metrics", {})
            base_metrics = base.get("metrics", {})

            for key in curr_metrics:
                cv = curr_metrics.get(key)
                bv = base_metrics.get(key)
                if (
                    isinstance(cv, (int, float))
                    and isinstance(bv, (int, float))
                    and bv != 0
                ):
                    pct_change = ((cv - bv) / abs(bv)) * 100
                    entry = {
                        "benchmark": name,
                        "metric": key,
                        "current": cv,
                        "baseline": bv,
                        "change_pct": round(pct_change, 2),
                    }
                    # Determine if regression (tps decrease) or improvement
                    higher_is_better = key in {"avg_tps", "accuracy", "tps"}
                    if higher_is_better and pct_change < -5:
                        comparison["regressions"].append(entry)
                    elif higher_is_better and pct_change > 5:
                        comparison["improvements"].append(entry)
                    elif not higher_is_better and pct_change > 10:
                        comparison["regressions"].append(entry)

        return comparison
