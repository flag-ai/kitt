"""Rich HTML formatters for Jupyter notebook display."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NotebookFormatter:
    """Format KITT results for rich display in Jupyter notebooks."""

    def format_results_table(self, results: list[dict[str, Any]]) -> str:
        """Format results as an HTML table.

        Args:
            results: List of result dicts.

        Returns:
            HTML string.
        """
        if not results:
            return "<p>No results to display.</p>"

        rows = []
        for r in results:
            status = "PASS" if r.get("passed") else "FAIL"
            color = "green" if r.get("passed") else "red"
            rows.append(
                f"<tr>"
                f"<td>{r.get('model', '?')}</td>"
                f"<td>{r.get('engine', '?')}</td>"
                f"<td style='color: {color}'>{status}</td>"
                f"<td>{r.get('timestamp', '?')[:19]}</td>"
                f"</tr>"
            )

        return (
            "<table>"
            "<tr><th>Model</th><th>Engine</th><th>Status</th><th>Timestamp</th></tr>"
            + "".join(rows)
            + "</table>"
        )

    def format_comparison(
        self,
        current: dict[str, Any],
        baseline: dict[str, Any],
    ) -> str:
        """Format a comparison between two results as HTML.

        Args:
            current: Current result dict.
            baseline: Baseline result dict.

        Returns:
            HTML string.
        """
        rows = []
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
                    change = ((cv - bv) / bv) * 100
                    color = "green" if change > 0 else "red" if change < 0 else "black"
                    rows.append(
                        f"<tr>"
                        f"<td>{name}</td>"
                        f"<td>{key}</td>"
                        f"<td>{bv:.2f}</td>"
                        f"<td>{cv:.2f}</td>"
                        f"<td style='color: {color}'>{change:+.1f}%</td>"
                        f"</tr>"
                    )

        if not rows:
            return "<p>No comparable metrics found.</p>"

        return (
            "<table>"
            "<tr><th>Benchmark</th><th>Metric</th><th>Baseline</th><th>Current</th><th>Change</th></tr>"
            + "".join(rows)
            + "</table>"
        )

    def format_metrics_summary(self, result: dict[str, Any]) -> str:
        """Format a single result's metrics as HTML summary.

        Args:
            result: Result dict with benchmarks.

        Returns:
            HTML string.
        """
        model = result.get("model", "?")
        engine = result.get("engine", "?")
        passed = result.get("passed", False)
        status_color = "green" if passed else "red"

        html = f"<h3>{model} / {engine}</h3>"
        html += f"<p>Status: <span style='color: {status_color}'>{'PASS' if passed else 'FAIL'}</span></p>"

        rows = []
        for bench in result.get("results", []):
            name = bench.get("test_name", "")
            metrics = bench.get("metrics", {})
            metric_strs = [
                f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}"
                for k, v in metrics.items()
                if isinstance(v, (int, float))
            ]
            rows.append(
                f"<tr><td>{name}</td><td>{', '.join(metric_strs[:5])}</td></tr>"
            )

        if rows:
            html += "<table><tr><th>Benchmark</th><th>Key Metrics</th></tr>"
            html += "".join(rows) + "</table>"

        return html
