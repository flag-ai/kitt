"""Latency benchmark implementation."""

import logging
import statistics
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

DEFAULT_PROMPTS = [
    "What is 2 + 2?",
    "Name the capital of France.",
    "Translate 'hello' to Spanish.",
    "What color is the sky?",
    "What is the speed of light?",
]


@register_benchmark
class LatencyBenchmark(LLMBenchmark):
    """Measure inference latency characteristics.

    Focuses on TTFT (time to first token), per-token latency,
    and end-to-end latency across varying prompt and output lengths.
    """

    name = "latency"
    version = "1.0.0"
    category = "performance"
    description = "Measure inference latency (TTFT, per-token, end-to-end)"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        """Run latency benchmark."""
        prompts = self._load_prompts(config)
        max_tokens = config.get("max_tokens", 128)
        temperature = config.get("temperature", 0.0)
        iterations = config.get("iterations", len(prompts))

        outputs: list[dict[str, Any]] = []
        errors: list[str] = []

        for i in range(iterations):
            prompt = prompts[i % len(prompts)]
            try:
                result = engine.generate(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                per_token_ms = (
                    result.metrics.total_latency_ms / result.completion_tokens
                    if result.completion_tokens > 0
                    else 0
                )

                outputs.append(
                    {
                        "iteration": i,
                        "prompt_length": len(prompt),
                        "completion_tokens": result.completion_tokens,
                        "metrics": {
                            "ttft_ms": result.metrics.ttft_ms,
                            "total_latency_ms": result.metrics.total_latency_ms,
                            "per_token_ms": round(per_token_ms, 2),
                            "tps": result.metrics.tps,
                        },
                    }
                )

            except Exception as e:
                error_msg = f"Error on iteration {i}: {str(e)}"
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

    def _load_prompts(self, config: dict[str, Any]) -> list[str]:
        """Load prompts from config, dataset_path, or defaults."""
        if "dataset_path" in config:
            from pathlib import Path

            dataset_path = Path(config["dataset_path"])
            if dataset_path.exists():
                lines = [
                    line.strip()
                    for line in dataset_path.read_text().splitlines()
                    if line.strip()
                ]
                if lines:
                    logger.info(f"Loaded {len(lines)} prompts from {dataset_path}")
                    return lines
            logger.warning(f"Dataset file not found: {dataset_path}, using defaults")
        return config.get("prompts", DEFAULT_PROMPTS)

    def _aggregate_metrics(self, outputs: list[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate latency metrics with percentiles."""
        if not outputs:
            return {}

        ttft_values = [o["metrics"]["ttft_ms"] for o in outputs]
        latencies = [o["metrics"]["total_latency_ms"] for o in outputs]
        per_token = [o["metrics"]["per_token_ms"] for o in outputs]

        def percentile(data: list[float], p: float) -> float:
            sorted_data = sorted(data)
            idx = int(len(sorted_data) * p / 100)
            idx = min(idx, len(sorted_data) - 1)
            return sorted_data[idx]

        return {
            "total_iterations": len(outputs),
            "ttft_ms": {
                "avg": round(statistics.mean(ttft_values), 2),
                "min": round(min(ttft_values), 2),
                "max": round(max(ttft_values), 2),
                "p50": round(percentile(ttft_values, 50), 2),
                "p95": round(percentile(ttft_values, 95), 2),
                "p99": round(percentile(ttft_values, 99), 2),
                "std_dev": round(statistics.stdev(ttft_values), 2)
                if len(ttft_values) > 1
                else 0,
            },
            "total_latency_ms": {
                "avg": round(statistics.mean(latencies), 2),
                "min": round(min(latencies), 2),
                "max": round(max(latencies), 2),
                "p50": round(percentile(latencies, 50), 2),
                "p95": round(percentile(latencies, 95), 2),
                "p99": round(percentile(latencies, 99), 2),
                "std_dev": round(statistics.stdev(latencies), 2)
                if len(latencies) > 1
                else 0,
            },
            "per_token_ms": {
                "avg": round(statistics.mean(per_token), 2),
                "min": round(min(per_token), 2),
                "max": round(max(per_token), 2),
            },
        }
