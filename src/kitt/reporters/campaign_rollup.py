"""Campaign results rollup — aggregate and pivot."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def generate_campaign_rollup(
    results: list[dict[str, Any]],
    output_format: str = "markdown",
) -> str:
    """Generate an aggregated rollup of campaign results.

    Args:
        results: List of result dicts from campaign runs.
        output_format: "markdown" or "json".

    Returns:
        Formatted rollup string.
    """
    if not results:
        return "No results to aggregate."

    # Group by model × engine
    groups: dict[str, dict[str, Any]] = {}
    for r in results:
        model = r.get("model", "unknown")
        engine = r.get("engine", "unknown")
        key = f"{model}|{engine}"

        if key not in groups:
            groups[key] = {
                "model": model,
                "engine": engine,
                "passed": 0,
                "failed": 0,
                "total_time_s": 0.0,
                "metrics": {},
            }

        group = groups[key]
        if r.get("passed", False):
            group["passed"] += 1
        else:
            group["failed"] += 1

        group["total_time_s"] += r.get("total_time_seconds", 0)

        # Collect aggregate metrics
        for bench in r.get("results", []):
            test_name = bench.get("test_name", "")
            for k, v in bench.get("metrics", {}).items():
                if isinstance(v, (int, float)):
                    metric_key = f"{test_name}.{k}"
                    if metric_key not in group["metrics"]:
                        group["metrics"][metric_key] = []
                    group["metrics"][metric_key].append(float(v))

    if output_format == "json":
        return _to_json(groups)
    return _to_markdown(groups)


def _to_markdown(groups: dict[str, dict[str, Any]]) -> str:
    """Generate Markdown rollup table."""
    lines = ["# Campaign Results Rollup", ""]

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Model | Engine | Pass | Fail | Time |")
    lines.append("|-------|--------|------|------|------|")

    total_passed = 0
    total_failed = 0

    for key in sorted(groups.keys()):
        g = groups[key]
        total_passed += g["passed"]
        total_failed += g["failed"]
        time_str = f"{g['total_time_s']:.0f}s"
        lines.append(
            f"| {g['model']} | {g['engine']} | "
            f"{g['passed']} | {g['failed']} | {time_str} |"
        )

    lines.append("")
    total = total_passed + total_failed
    rate = (total_passed / total * 100) if total > 0 else 0
    lines.append(
        f"**Total:** {total} runs, {total_passed} passed, "
        f"{total_failed} failed ({rate:.0f}% pass rate)"
    )
    lines.append("")

    # Key metrics pivot
    lines.append("## Key Metrics")
    lines.append("")

    # Find common metrics across groups
    all_metric_keys = set()
    for g in groups.values():
        all_metric_keys.update(g["metrics"].keys())

    # Focus on throughput and accuracy
    highlight_patterns = ["avg_tps", "accuracy", "avg_latency_ms"]
    highlighted = sorted(
        k for k in all_metric_keys if any(p in k for p in highlight_patterns)
    )

    if highlighted:
        header = "| Model | Engine | " + " | ".join(highlighted) + " |"
        sep = "|-------|--------|" + "|".join("------" for _ in highlighted) + "|"
        lines.append(header)
        lines.append(sep)

        for key in sorted(groups.keys()):
            g = groups[key]
            vals = []
            for mk in highlighted:
                values = g["metrics"].get(mk, [])
                if values:
                    avg = sum(values) / len(values)
                    vals.append(f"{avg:.2f}")
                else:
                    vals.append("-")
            lines.append(f"| {g['model']} | {g['engine']} | " + " | ".join(vals) + " |")

    lines.append("")
    return "\n".join(lines)


def _to_json(groups: dict[str, dict[str, Any]]) -> str:
    """Generate JSON rollup."""
    output = {}
    for key, g in groups.items():
        # Average all metric values
        avg_metrics = {}
        for mk, values in g["metrics"].items():
            avg_metrics[mk] = round(sum(values) / len(values), 4) if values else 0

        output[key] = {
            "model": g["model"],
            "engine": g["engine"],
            "passed": g["passed"],
            "failed": g["failed"],
            "total_time_s": round(g["total_time_s"], 1),
            "avg_metrics": avg_metrics,
        }

    return json.dumps(output, indent=2)
