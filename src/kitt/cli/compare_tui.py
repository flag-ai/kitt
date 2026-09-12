"""TUI for comparing benchmark results using Textual."""

import json
from pathlib import Path
from typing import Any

try:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import (
        DataTable,
        Footer,
        Header,
        Static,
        Tree,
    )

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False


def check_textual_available() -> bool:
    """Check if Textual is installed."""
    return TEXTUAL_AVAILABLE


if TEXTUAL_AVAILABLE:

    class ComparisonApp(App):
        """TUI application for comparing benchmark results."""

        CSS = """
        Screen {
            layout: horizontal;
        }

        #sidebar {
            width: 30;
            background: $panel;
            border-right: thick $primary;
            padding: 1;
        }

        #main-content {
            width: 1fr;
        }

        #summary-panel {
            height: auto;
            max-height: 8;
            padding: 1;
            background: $surface;
            border-bottom: thick $primary;
        }

        #metrics-table {
            height: 1fr;
        }

        .header-text {
            text-style: bold;
            color: $text;
        }
        """

        BINDINGS = [
            ("q", "quit", "Quit"),
            ("d", "toggle_dark", "Dark/Light"),
            ("r", "refresh", "Refresh"),
        ]

        def __init__(self, result_paths: list[str], **kwargs):
            super().__init__(**kwargs)
            self.result_paths = result_paths
            self.result_data: list[dict[str, Any]] = []
            self.labels: list[str] = []

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Horizontal():
                with Vertical(id="sidebar"):
                    yield Static("Runs", classes="header-text")
                    yield Tree("Results", id="run-tree")
                with Vertical(id="main-content"):
                    yield Static("", id="summary-panel")
                    yield DataTable(id="metrics-table")
            yield Footer()

        def on_mount(self) -> None:
            self._load_results()
            self._build_run_tree()
            self._populate_comparison_table()
            self._update_summary()

        def _load_results(self) -> None:
            """Load all result JSON files."""
            for path_str in self.result_paths:
                path = Path(path_str)
                metrics_file = path / "metrics.json" if path.is_dir() else path
                if not metrics_file.exists():
                    continue
                with open(metrics_file) as f:
                    data = json.load(f)
                self.result_data.append(data)
                label = data.get("model", path.name)[:20]
                engine = data.get("engine", "?")
                self.labels.append(f"{label} ({engine})")

        def _build_run_tree(self) -> None:
            """Build the sidebar tree of runs."""
            tree = self.query_one("#run-tree", Tree)
            tree.clear()
            for _i, (data, label) in enumerate(
                zip(self.result_data, self.labels, strict=False)
            ):
                node = tree.root.add(label)
                node.add_leaf(f"Suite: {data.get('suite_name', '?')}")
                node.add_leaf(f"Time: {data.get('timestamp', '?')[:19]}")
                passed = data.get("passed", False)
                status = "PASS" if passed else "FAIL"
                node.add_leaf(f"Status: {status}")
                results = data.get("results", [])
                node.add_leaf(f"Benchmarks: {len(results)}")

            tree.root.expand_all()

        def _populate_comparison_table(self) -> None:
            """Fill the main comparison data table."""
            table = self.query_one("#metrics-table", DataTable)
            table.clear(columns=True)

            if len(self.result_data) < 2:
                table.add_column("Info")
                table.add_row("Load at least 2 result sets to compare")
                return

            # Extract per-benchmark metrics
            all_benchmarks = set()
            for data in self.result_data:
                for r in data.get("results", []):
                    all_benchmarks.add(r.get("test_name", "?"))

            table.add_column("Benchmark", key="bench")
            table.add_column("Metric", key="metric")
            for i, label in enumerate(self.labels):
                table.add_column(label[:15], key=f"run_{i}")
            table.add_column("Delta", key="delta")

            for bench_name in sorted(all_benchmarks):
                bench_metrics = self._collect_bench_metrics(bench_name)
                for metric_name in sorted(bench_metrics.keys()):
                    values = bench_metrics[metric_name]
                    row = [bench_name, metric_name]
                    float_vals = []
                    for i in range(len(self.labels)):
                        val = values.get(i)
                        if val is not None and isinstance(val, (int, float)):
                            row.append(f"{val:.4f}")
                            float_vals.append(val)
                        else:
                            row.append(str(val) if val is not None else "-")
                    # Delta column
                    if len(float_vals) >= 2:
                        delta = float_vals[-1] - float_vals[0]
                        pct = (delta / float_vals[0] * 100) if float_vals[0] != 0 else 0
                        row.append(f"{delta:+.4f} ({pct:+.1f}%)")
                    else:
                        row.append("-")
                    table.add_row(*row)

        def _collect_bench_metrics(self, bench_name: str) -> dict[str, dict[int, Any]]:
            """Collect metrics for a benchmark across all runs."""
            metrics: dict[str, dict[int, Any]] = {}
            for i, data in enumerate(self.result_data):
                for r in data.get("results", []):
                    if r.get("test_name") != bench_name:
                        continue
                    for k, v in r.get("metrics", {}).items():
                        if isinstance(v, (int, float)):
                            if k not in metrics:
                                metrics[k] = {}
                            metrics[k][i] = v
            return metrics

        def _update_summary(self) -> None:
            """Update summary panel."""
            panel = self.query_one("#summary-panel", Static)
            if not self.result_data:
                panel.update("No results loaded")
                return

            lines = [f"Comparing {len(self.result_data)} result set(s)"]
            for i, (data, label) in enumerate(
                zip(self.result_data, self.labels, strict=False)
            ):
                passed = data.get("passed", False)
                status = "[PASS]" if passed else "[FAIL]"
                time_s = data.get("total_time_seconds", 0)
                lines.append(f"  {i + 1}. {label} - {status} ({time_s:.1f}s)")

            panel.update("\n".join(lines))

        def action_toggle_dark(self) -> None:
            self.dark: bool = not self.dark

        def action_refresh(self) -> None:
            self.result_data.clear()
            self.labels.clear()
            self._load_results()
            self._build_run_tree()
            self._populate_comparison_table()
            self._update_summary()


def launch_comparison_tui(result_paths: list[str]) -> None:
    """Launch the comparison TUI.

    Args:
        result_paths: Paths to result directories or metrics.json files.
    """
    if not TEXTUAL_AVAILABLE:
        raise ImportError(
            "Textual is not installed. Install with: pip install kitt[cli_ui]"
        )

    app = ComparisonApp(result_paths)
    app.run()
