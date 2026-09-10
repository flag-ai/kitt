"""Vision-Language Model benchmark — image understanding tasks."""

import logging
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

# Built-in text-only VLM evaluation (no actual images — tests the API path)
BUILT_IN_VLM_TASKS: list[dict[str, Any]] = [
    {
        "prompt": "Describe what you see in this image.",
        "image_url": None,
        "expected_keywords": [],
        "description": "Basic image description (placeholder)",
    },
]


@register_benchmark
class VLMBenchmark(LLMBenchmark):
    """Benchmark vision-language model capabilities."""

    name = "vlm_benchmark"
    version = "1.0.0"
    category = "quality_standard"
    description = "Evaluate vision-language model image understanding"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        tasks = config.get("tasks", BUILT_IN_VLM_TASKS)
        max_tokens = config.get("max_tokens", 256)
        temperature = config.get("temperature", 0.0)
        sample_size = config.get("sample_size")

        if sample_size and sample_size < len(tasks):
            tasks = tasks[:sample_size]

        outputs: list[dict[str, Any]] = []
        errors: list[str] = []
        correct = 0
        total = len(tasks)

        # Check if engine supports chat/multimodal
        has_chat = hasattr(engine, "generate_chat")

        for i, task in enumerate(tasks):
            prompt = task["prompt"]
            image_url = task.get("image_url")
            expected_keywords = task.get("expected_keywords", [])

            try:
                if image_url and has_chat:
                    result = engine.generate_chat(
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": image_url},
                                    },
                                ],
                            }
                        ],
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                else:
                    result = engine.generate(
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )

                answer = result.output.strip()
                is_correct = True
                if expected_keywords:
                    answer_lower = answer.lower()
                    is_correct = any(
                        kw.lower() in answer_lower for kw in expected_keywords
                    )

                if is_correct:
                    correct += 1

                outputs.append(
                    {
                        "index": i,
                        "prompt": prompt[:100],
                        "has_image": image_url is not None,
                        "correct": is_correct,
                        "answer": answer[:200],
                        "latency_ms": result.metrics.total_latency_ms,
                    }
                )

            except Exception as e:
                errors.append(f"Task {i}: {e}")

        metrics = {
            "accuracy": round(correct / total, 4) if total else 0,
            "correct": correct,
            "total": total,
            "multimodal_supported": has_chat,
        }

        if outputs:
            latencies = [o.get("latency_ms", 0) for o in outputs if "latency_ms" in o]
            if latencies:
                metrics["avg_latency_ms"] = round(sum(latencies) / len(latencies), 2)

        return BenchmarkResult(
            test_name=self.name,
            test_version=self.version,
            passed=len(errors) == 0,
            metrics=metrics,
            outputs=outputs,
            errors=errors,
        )
