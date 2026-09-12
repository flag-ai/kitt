"""CI report formatting for PR comments and GitHub Actions."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CIReportFormatter:
    """Format benchmark results as Markdown for CI/CD contexts."""

    def format_summary(
        self,
        results: dict[str, Any],
        baseline: dict[str, Any] | None = None,
    ) -> str:
        """Format a benchmark result summary as Markdown table.

        Args:
            results: Suite result dict (from metrics.json).
            baseline: Optional baseline result for comparison.

        Returns:
            Markdown string suitable for PR comments.
        """
        lines = []
        lines.append("## KITT Benchmark Results")
        lines.append("")

        model = results.get("model", "unknown")
        engine = results.get("engine", "unknown")
        passed = results.get("passed", False)
        status = "PASS" if passed else "FAIL"

        lines.append(
            f"**Model:** {model} | **Engine:** {engine} | **Status:** {status}"
        )
        lines.append("")

        # Benchmarks table
        lines.append("| Benchmark | Run | Status | Key Metrics |")
        lines.append("|-----------|-----|--------|-------------|")

        for bench in results.get("results", []):
            name = bench.get("test_name", "")
            run_num = bench.get("run_number", 1)
            bench_status = "PASS" if bench.get("passed") else "FAIL"
            metrics = bench.get("metrics", {})

            key_metrics = []
            for k, v in metrics.items():
                if isinstance(v, (int, float)):
                    key_metrics.append(
                        f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}"
                    )
            metrics_str = ", ".join(key_metrics[:4])

            lines.append(f"| {name} | {run_num} | {bench_status} | {metrics_str} |")

        lines.append("")

        # Regression comparison
        if baseline:
            regression_lines = self._format_regression(results, baseline)
            if regression_lines:
                lines.extend(regression_lines)

        total_time = results.get("total_time_seconds", 0)
        lines.append(f"*Total time: {total_time:.1f}s*")

        return "\n".join(lines)

    def format_regression_alert(
        self,
        regressions: list[dict[str, Any]],
    ) -> str:
        """Format regression alerts as Markdown.

        Args:
            regressions: List of regression dicts from RegressionDetector.

        Returns:
            Markdown string.
        """
        if not regressions:
            return "No regressions detected."

        lines = ["### Regressions Detected", ""]
        lines.append("| Metric | Current | Baseline | Change | Severity |")
        lines.append("|--------|---------|----------|--------|----------|")

        for r in regressions:
            metric = r.get("metric", "")
            current = r.get("current", 0)
            baseline = r.get("baseline", 0)
            change = r.get("change_pct", 0)
            severity = r.get("severity", "warning")

            lines.append(
                f"| {metric} | {current:.2f} | {baseline:.2f} | "
                f"{change:+.1f}% | {severity} |"
            )

        return "\n".join(lines)

    def _format_regression(
        self,
        current: dict[str, Any],
        baseline: dict[str, Any],
    ) -> list[str]:
        """Compare current vs baseline and format differences."""
        lines = ["### Comparison vs Baseline", ""]

        current_benchmarks = {b["test_name"]: b for b in current.get("results", [])}
        baseline_benchmarks = {b["test_name"]: b for b in baseline.get("results", [])}

        has_changes = False
        for name, curr_bench in current_benchmarks.items():
            if name in baseline_benchmarks:
                base_bench = baseline_benchmarks[name]
                curr_metrics = curr_bench.get("metrics", {})
                base_metrics = base_bench.get("metrics", {})

                for key in curr_metrics:
                    curr_val = curr_metrics.get(key)
                    base_val = base_metrics.get(key)
                    if (
                        isinstance(curr_val, (int, float))
                        and isinstance(base_val, (int, float))
                        and base_val != 0
                    ):
                        change = ((curr_val - base_val) / base_val) * 100
                        if abs(change) > 5:
                            if not has_changes:
                                lines.append("| Benchmark | Metric | Change |")
                                lines.append("|-----------|--------|--------|")
                                has_changes = True
                            lines.append(f"| {name} | {key} | {change:+.1f}% |")

        if not has_changes:
            lines.append("No significant changes vs baseline.")

        lines.append("")
        return lines
