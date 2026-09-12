"""Throughput benchmark implementation."""

import logging
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

DEFAULT_PROMPTS = [
    "Explain the theory of relativity in simple terms.",
    "Write a short story about a robot learning to paint.",
    "What are the main differences between Python and Rust?",
    "Summarize the key events of World War II in 200 words.",
    "Describe how a neural network learns from data.",
]


@register_benchmark
class ThroughputBenchmark(LLMBenchmark):
    """Measure inference throughput (tokens per second)."""

    name = "throughput"
    version = "1.0.0"
    category = "performance"
    description = "Measure inference throughput across multiple prompts"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        """Run throughput benchmark."""
        prompts = self._load_prompts(config)
        max_tokens = config.get("max_tokens", 256)
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

                outputs.append(
                    {
                        "iteration": i,
                        "prompt": prompt[:100],  # Truncate for storage
                        "output_length": len(result.output),
                        "metrics": {
                            "tps": result.metrics.tps,
                            "total_latency_ms": result.metrics.total_latency_ms,
                            "ttft_ms": result.metrics.ttft_ms,
                            "prompt_tokens": result.prompt_tokens,
                            "completion_tokens": result.completion_tokens,
                            "gpu_memory_peak_gb": result.metrics.gpu_memory_peak_gb,
                        },
                    }
                )

            except Exception as e:
                error_msg = f"Error on iteration {i}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Calculate aggregate metrics
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
        """Aggregate per-iteration metrics."""
        if not outputs:
            return {}

        tps_values = [o["metrics"]["tps"] for o in outputs]
        latencies = [o["metrics"]["total_latency_ms"] for o in outputs]
        total_tokens = sum(o["metrics"]["completion_tokens"] for o in outputs)
        total_time_s = sum(latencies) / 1000

        return {
            "total_iterations": len(outputs),
            "total_tokens_generated": total_tokens,
            "total_time_seconds": round(total_time_s, 3),
            "avg_tps": round(sum(tps_values) / len(tps_values), 2),
            "min_tps": round(min(tps_values), 2),
            "max_tps": round(max(tps_values), 2),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
            "p50_latency_ms": round(sorted(latencies)[len(latencies) // 2], 2),
            "p99_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.99)], 2),
        }
