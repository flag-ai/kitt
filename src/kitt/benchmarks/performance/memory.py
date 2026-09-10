"""Memory profiling benchmark implementation."""

import logging
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

SHORT_PROMPT = "Hello, how are you?"
MEDIUM_PROMPT = (
    "Write a detailed explanation of how neural networks learn, "
    "including backpropagation, gradient descent, and loss functions."
)
LONG_PROMPT = (
    "Write a comprehensive essay covering the history of artificial intelligence "
    "from the Dartmouth workshop in 1956 through to modern large language models. "
    "Cover key milestones including expert systems, the AI winters, the resurgence "
    "with deep learning, attention mechanisms, transformers, and the current era "
    "of foundation models. Discuss both the technical advances and the societal "
    "impact at each stage. Be thorough and detailed."
)


@register_benchmark
class MemoryBenchmark(LLMBenchmark):
    """Profile GPU memory usage during inference.

    Measures peak, average, and baseline GPU memory across
    varying prompt lengths and output sizes.
    """

    name = "memory_usage"
    version = "1.0.0"
    category = "performance"
    description = "Profile GPU memory usage during inference"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        """Run memory profiling benchmark."""
        temperature = config.get("temperature", 0.0)
        output_lengths = config.get("output_lengths", [32, 128, 512])
        prompt_configs = config.get(
            "prompt_configs",
            [
                {"name": "short", "prompt": SHORT_PROMPT},
                {"name": "medium", "prompt": MEDIUM_PROMPT},
                {"name": "long", "prompt": LONG_PROMPT},
            ],
        )

        outputs: list[dict[str, Any]] = []
        errors: list[str] = []

        for prompt_config in prompt_configs:
            prompt_name = prompt_config.get("name", "unknown")
            prompt = prompt_config.get("prompt", SHORT_PROMPT)

            for max_tokens in output_lengths:
                try:
                    result = engine.generate(
                        prompt=prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )

                    outputs.append(
                        {
                            "prompt_name": prompt_name,
                            "prompt_length_chars": len(prompt),
                            "max_tokens": max_tokens,
                            "actual_completion_tokens": result.completion_tokens,
                            "metrics": {
                                "gpu_memory_peak_gb": result.metrics.gpu_memory_peak_gb,
                                "gpu_memory_avg_gb": result.metrics.gpu_memory_avg_gb,
                                "total_latency_ms": result.metrics.total_latency_ms,
                                "tps": result.metrics.tps,
                            },
                        }
                    )

                except Exception as e:
                    error_msg = (
                        f"Error on {prompt_name}/max_tokens={max_tokens}: {str(e)}"
                    )
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
        """Aggregate memory metrics."""
        if not outputs:
            return {}

        peak_values = [o["metrics"]["gpu_memory_peak_gb"] for o in outputs]
        avg_values = [o["metrics"]["gpu_memory_avg_gb"] for o in outputs]

        # Group by prompt length
        by_prompt: dict[str, list[dict]] = {}
        for o in outputs:
            name = o["prompt_name"]
            if name not in by_prompt:
                by_prompt[name] = []
            by_prompt[name].append(o)

        per_prompt_peaks = {
            name: max(o["metrics"]["gpu_memory_peak_gb"] for o in items)
            for name, items in by_prompt.items()
        }

        return {
            "total_measurements": len(outputs),
            "overall_peak_gpu_memory_gb": round(max(peak_values), 3)
            if peak_values
            else 0,
            "overall_avg_gpu_memory_gb": (
                round(sum(avg_values) / len(avg_values), 3) if avg_values else 0
            ),
            "per_prompt_peak_gb": {k: round(v, 3) for k, v in per_prompt_peaks.items()},
            "memory_range_gb": round(max(peak_values) - min(peak_values), 3)
            if peak_values
            else 0,
        }
