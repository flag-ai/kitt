"""Batch inference benchmark — measure throughput under concurrent load."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENCY_LEVELS = [1, 4, 8, 16]

DEFAULT_PROMPTS = [
    "Explain quantum computing in simple terms.",
    "Write a haiku about machine learning.",
    "What is the capital of France?",
    "Describe the water cycle in 100 words.",
]


@register_benchmark
class BatchInferenceBenchmark(LLMBenchmark):
    """Measure throughput and latency under concurrent request load."""

    name = "batch_inference"
    version = "1.0.0"
    category = "performance"
    description = "Measure inference performance at multiple concurrency levels"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        concurrency_levels = config.get(
            "concurrency_levels", DEFAULT_CONCURRENCY_LEVELS
        )
        prompts = config.get("prompts", DEFAULT_PROMPTS)
        max_tokens = config.get("max_tokens", 128)
        temperature = config.get("temperature", 0.0)
        requests_per_level = config.get("requests_per_level", len(prompts))

        outputs: list[dict[str, Any]] = []
        errors: list[str] = []
        level_metrics: dict[int, dict[str, float]] = {}

        for level in concurrency_levels:
            logger.info(f"Testing concurrency level: {level}")
            results = self._run_concurrent(
                engine,
                prompts,
                level,
                requests_per_level,
                max_tokens,
                temperature,
            )

            successes = [r for r in results if r.get("success")]
            failures = [r for r in results if not r.get("success")]

            if failures:
                for f in failures:
                    errors.append(f"Concurrency {level}: {f.get('error', 'unknown')}")

            if successes:
                tps_values = [r["tps"] for r in successes]
                latencies = [r["latency_ms"] for r in successes]
                total_tokens = sum(r.get("completion_tokens", 0) for r in successes)
                wall_time = max(r["latency_ms"] for r in successes) / 1000

                level_data = {
                    "concurrency": level,
                    "requests": len(successes),
                    "failed": len(failures),
                    "avg_tps": round(sum(tps_values) / len(tps_values), 2),
                    "throughput_total_tps": round(total_tokens / wall_time, 2)
                    if wall_time > 0
                    else 0,
                    "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
                    "min_latency_ms": round(min(latencies), 2),
                    "max_latency_ms": round(max(latencies), 2),
                    "total_tokens": total_tokens,
                }
                level_metrics[level] = level_data
                outputs.append(level_data)

        # Determine optimal concurrency
        metrics = self._compute_aggregate(level_metrics)

        return BenchmarkResult(
            test_name=self.name,
            test_version=self.version,
            passed=len(errors) == 0,
            metrics=metrics,
            outputs=outputs,
            errors=errors,
        )

    def _run_concurrent(
        self,
        engine,
        prompts: list[str],
        concurrency: int,
        num_requests: int,
        max_tokens: int,
        temperature: float,
    ) -> list[dict[str, Any]]:
        """Run concurrent requests and return per-request results."""
        results: list[dict[str, Any]] = []

        def _single_request(idx: int) -> dict[str, Any]:
            prompt = prompts[idx % len(prompts)]
            start = time.perf_counter()
            try:
                gen_result = engine.generate(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                elapsed_ms = (time.perf_counter() - start) * 1000
                return {
                    "success": True,
                    "tps": gen_result.metrics.tps,
                    "latency_ms": elapsed_ms,
                    "completion_tokens": gen_result.completion_tokens,
                }
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                return {
                    "success": False,
                    "error": str(e),
                    "latency_ms": elapsed_ms,
                }

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(_single_request, i) for i in range(num_requests)]
            for future in as_completed(futures):
                results.append(future.result())

        return results

    def _compute_aggregate(
        self, level_metrics: dict[int, dict[str, float]]
    ) -> dict[str, Any]:
        """Compute aggregate metrics across concurrency levels."""
        if not level_metrics:
            return {}

        # Find optimal concurrency (highest total throughput)
        best_level = max(
            level_metrics,
            key=lambda level: level_metrics[level].get("throughput_total_tps", 0),
        )

        metrics: dict[str, Any] = {
            "concurrency_levels_tested": list(level_metrics.keys()),
            "optimal_concurrency": best_level,
            "optimal_throughput_tps": level_metrics[best_level].get(
                "throughput_total_tps", 0
            ),
        }

        for level, data in level_metrics.items():
            metrics[f"throughput_at_{level}"] = data.get("throughput_total_tps", 0)
            metrics[f"latency_at_{level}"] = data.get("avg_latency_ms", 0)

        return metrics
