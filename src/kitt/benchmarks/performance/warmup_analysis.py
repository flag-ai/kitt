"""Warmup analysis benchmark implementation."""

import logging
import time
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

DEFAULT_PROMPTS = [
    "Translate this to French: Hello, how are you?",
    "Summarize in one sentence: AI is transforming the way we live and work.",
    "Write a haiku about technology.",
]


@register_benchmark
class WarmupAnalysisBenchmark(LLMBenchmark):
    """Measure warmup phase performance and CUDA kernel initialization times.

    This benchmark intentionally has warmup disabled — it IS the warmup test.
    It runs multiple cold-start-like iterations and measures how latency
    decreases as the engine warms up.
    """

    name = "warmup_analysis"
    version = "1.0.0"
    category = "performance"
    description = "Measure warmup performance and CUDA kernel initialization"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        """Run warmup analysis benchmark."""
        test_config = config.get("test_config", {})
        prompts = test_config.get("prompts", DEFAULT_PROMPTS)
        iterations = test_config.get("iterations", 10)
        max_tokens = config.get("sampling", {}).get("max_tokens", 100)
        temperature = config.get("sampling", {}).get("temperature", 0.0)

        outputs: list[dict[str, Any]] = []
        errors: list[str] = []

        for i in range(iterations):
            prompt = prompts[i % len(prompts)]
            try:
                start = time.perf_counter()
                result = engine.generate(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                wall_time_ms = (time.perf_counter() - start) * 1000

                outputs.append(
                    {
                        "iteration": i,
                        "prompt": prompt[:100],
                        "metrics": {
                            "wall_time_ms": round(wall_time_ms, 2),
                            "total_latency_ms": result.metrics.total_latency_ms,
                            "ttft_ms": result.metrics.ttft_ms,
                            "tps": result.metrics.tps,
                            "completion_tokens": result.completion_tokens,
                            "gpu_memory_peak_gb": result.metrics.gpu_memory_peak_gb,
                        },
                    }
                )

            except Exception as e:
                error_msg = f"Error on warmup iteration {i}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)

        metrics = self._aggregate_metrics(outputs)

        return BenchmarkResult(
            test_name=self.name,
            test_version=self.version,
            passed=len(errors) == 0,
            metrics=metrics,
            outputs=outputs,
            errors=errors,
        )

    def _aggregate_metrics(self, outputs: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze warmup curve."""
        if not outputs:
            return {}

        latencies = [o["metrics"]["wall_time_ms"] for o in outputs]

        # First iteration is the cold start
        first_latency = latencies[0] if latencies else 0

        # Subsequent iterations (warmed up)
        subsequent = latencies[1:] if len(latencies) > 1 else []
        subsequent_avg = sum(subsequent) / len(subsequent) if subsequent else 0

        # Reduction percentage
        reduction_pct = (
            ((first_latency - subsequent_avg) / first_latency * 100)
            if first_latency > 0
            else 0
        )

        # Find stabilization point (where variance drops below 10% of mean)
        stabilization_idx = len(latencies) - 1
        for i in range(2, len(latencies)):
            window = latencies[max(0, i - 2) : i + 1]
            mean_w = sum(window) / len(window)
            if mean_w > 0:
                max_dev = max(abs(v - mean_w) / mean_w for v in window)
                if max_dev < 0.10:
                    stabilization_idx = i
                    break

        return {
            "total_iterations": len(outputs),
            "first_iteration_latency_ms": round(first_latency, 2),
            "subsequent_avg_latency_ms": round(subsequent_avg, 2),
            "latency_reduction_percent": round(reduction_pct, 1),
            "stabilization_iteration": stabilization_idx,
            "per_iteration_latencies_ms": [round(lat, 2) for lat in latencies],
        }
