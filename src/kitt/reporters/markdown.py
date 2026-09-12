"""Markdown summary report generation."""

from datetime import datetime

from kitt.benchmarks.base import BenchmarkResult
from kitt.hardware.fingerprint import SystemInfo
from kitt.runners.suite import SuiteResult


def generate_summary(
    suite_result: SuiteResult,
    system_info: SystemInfo | None = None,
    engine_name: str = "unknown",
    model_name: str = "unknown",
) -> str:
    """Generate a markdown summary of test results.

    Args:
        suite_result: Results from running a test suite.
        system_info: Optional system hardware information.
        engine_name: Name of the inference engine used.
        model_name: Name/path of the model tested.

    Returns:
        Markdown-formatted summary string.
    """
    lines = []
    lines.append(f"# KITT Benchmark Results - {suite_result.suite_name}")
    lines.append("")
    lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Engine**: {engine_name}")
    lines.append(f"**Model**: {model_name}")
    lines.append(
        f"**Status**: {'PASSED' if suite_result.passed else 'FAILED'} "
        f"({suite_result.passed_count}/{suite_result.total_benchmarks})"
    )
    lines.append(f"**Total Time**: {suite_result.total_time_seconds:.1f}s")
    lines.append("")

    # System info
    if system_info:
        lines.append("## System Information")
        lines.append("")
        lines.append(f"- **Environment**: {system_info.environment_type}")
        lines.append(f"- **OS**: {system_info.os}")
        if system_info.gpu:
            gpu = system_info.gpu
            lines.append(
                f"- **GPU**: {gpu.model} ({gpu.vram_gb}GB)"
                + (f" x{gpu.count}" if gpu.count > 1 else "")
            )
        lines.append(
            f"- **CPU**: {system_info.cpu.model} ({system_info.cpu.cores}c/{system_info.cpu.threads}t)"
        )
        lines.append(f"- **RAM**: {system_info.ram_gb}GB {system_info.ram_type}")
        if system_info.cuda_version:
            lines.append(f"- **CUDA**: {system_info.cuda_version}")
        lines.append("")

    # Results table
    lines.append("## Results")
    lines.append("")
    lines.append("| Benchmark | Run | Status | Key Metric |")
    lines.append("|-----------|-----|--------|------------|")

    for result in suite_result.results:
        status = "PASS" if result.passed else "FAIL"
        key_metric = _format_key_metric(result)
        lines.append(
            f"| {result.test_name} | {result.run_number} | {status} | {key_metric} |"
        )

    lines.append("")

    # Detailed metrics per benchmark
    lines.append("## Detailed Metrics")
    lines.append("")

    for result in suite_result.results:
        lines.append(f"### {result.test_name} (Run {result.run_number})")
        lines.append("")

        if result.warmup_times:
            avg_warmup = sum(result.warmup_times) / len(result.warmup_times)
            lines.append(
                f"- **Warmup**: {len(result.warmup_times)} iterations, avg {avg_warmup:.3f}s"
            )

        for key, value in result.metrics.items():
            if isinstance(value, float):
                lines.append(f"- **{key}**: {value:.4f}")
            else:
                lines.append(f"- **{key}**: {value}")

        if result.errors:
            lines.append(f"- **Errors**: {len(result.errors)}")
            for error in result.errors[:5]:  # Show first 5
                lines.append(f"  - {error}")

        lines.append("")

    return "\n".join(lines)


def _format_key_metric(result: BenchmarkResult) -> str:
    """Extract a single key metric for the summary table."""
    metrics = result.metrics
    if "avg_tps" in metrics:
        return f"{metrics['avg_tps']:.1f} tok/s"
    if "accuracy" in metrics:
        return f"{metrics['accuracy']:.1%}"
    if "avg_latency_ms" in metrics:
        return f"{metrics['avg_latency_ms']:.1f}ms"
    return "-"
