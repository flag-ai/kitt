"""Streaming latency benchmark — TTFT + inter-token latency via SSE."""

import logging
import statistics
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

DEFAULT_PROMPTS = [
    "Explain quantum computing in simple terms.",
    "Write a haiku about the ocean.",
    "What is the Pythagorean theorem?",
]


@register_benchmark
class StreamingLatencyBenchmark(LLMBenchmark):
    """Measure streaming latency: TTFT and inter-token latency.

    Sends requests with streaming enabled and measures:
    - Time to first token (TTFT)
    - Average inter-token latency
    - Token delivery jitter
    """

    name = "streaming_latency"
    version = "1.0.0"
    category = "performance"
    description = "Measure streaming TTFT and inter-token latency"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        prompts = config.get("prompts", DEFAULT_PROMPTS)
        max_tokens = config.get("max_tokens", 128)
        temperature = config.get("temperature", 0.0)
        iterations = config.get("iterations", len(prompts))

        outputs: list[dict[str, Any]] = []
        errors: list[str] = []

        # Check if engine supports streaming
        base_url = getattr(engine, "_base_url", None)
        model_name = getattr(engine, "_model_name", "default")

        if not base_url:
            return BenchmarkResult(
                test_name=self.name,
                test_version=self.version,
                passed=False,
                metrics={},
                outputs=[],
                errors=["Engine does not expose a base_url for streaming"],
            )

        from kitt.engines.openai_compat import openai_generate_stream

        for i in range(iterations):
            prompt = prompts[i % len(prompts)]
            try:
                chunks = list(
                    openai_generate_stream(
                        base_url,
                        prompt,
                        model=model_name,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                )

                if not chunks:
                    errors.append(f"No chunks received on iteration {i}")
                    continue

                ttft_ms = chunks[0].timestamp_ms
                inter_token_ms = []
                for j in range(1, len(chunks)):
                    delta = chunks[j].timestamp_ms - chunks[j - 1].timestamp_ms
                    inter_token_ms.append(delta)

                total_ms = chunks[-1].timestamp_ms
                total_tokens = len(chunks)

                outputs.append(
                    {
                        "iteration": i,
                        "prompt": prompt[:100],
                        "total_tokens": total_tokens,
                        "metrics": {
                            "ttft_ms": round(ttft_ms, 2),
                            "avg_inter_token_ms": round(
                                statistics.mean(inter_token_ms), 2
                            )
                            if inter_token_ms
                            else 0,
                            "max_inter_token_ms": round(max(inter_token_ms), 2)
                            if inter_token_ms
                            else 0,
                            "jitter_ms": round(statistics.stdev(inter_token_ms), 2)
                            if len(inter_token_ms) > 1
                            else 0,
                            "total_latency_ms": round(total_ms, 2),
                        },
                    }
                )

            except Exception as e:
                errors.append(f"Error on iteration {i}: {e}")

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
        if not outputs:
            return {}

        ttft_values = [o["metrics"]["ttft_ms"] for o in outputs]
        inter_token = [o["metrics"]["avg_inter_token_ms"] for o in outputs]

        return {
            "total_iterations": len(outputs),
            "ttft_ms": {
                "avg": round(statistics.mean(ttft_values), 2),
                "min": round(min(ttft_values), 2),
                "max": round(max(ttft_values), 2),
            },
            "avg_inter_token_ms": {
                "avg": round(statistics.mean(inter_token), 2) if inter_token else 0,
                "min": round(min(inter_token), 2) if inter_token else 0,
                "max": round(max(inter_token), 2) if inter_token else 0,
            },
        }
