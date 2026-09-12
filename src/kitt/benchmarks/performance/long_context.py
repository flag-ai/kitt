"""Long-context benchmark — quality at varying context lengths."""

import logging
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

# Filler text for padding context
_FILLER_SENTENCE = (
    "The quick brown fox jumps over the lazy dog. "
    "This sentence is used as filler to pad context length. "
)

# The "needle" — a specific fact hidden in context
_DEFAULT_NEEDLE = "The secret code is KITT-42-BENCHMARK."
_DEFAULT_QUESTION = "What is the secret code?"


@register_benchmark
class LongContextBenchmark(LLMBenchmark):
    """Test quality degradation at varying context lengths.

    Uses a needle-in-haystack approach: hides a fact at different
    positions within increasing context lengths and checks if the
    model can retrieve it.

    Context lengths: 4K, 8K, 16K, 32K tokens (configurable).
    """

    name = "long_context"
    version = "1.0.0"
    category = "performance"
    description = "Test quality at long context lengths (needle-in-haystack)"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        needle = config.get("needle", _DEFAULT_NEEDLE)
        question = config.get("question", _DEFAULT_QUESTION)
        context_lengths = config.get("context_lengths", [4096, 8192, 16384, 32768])
        needle_positions = config.get("needle_positions", [0.25, 0.5, 0.75])
        max_tokens = config.get("max_tokens", 128)
        temperature = config.get("temperature", 0.0)

        outputs: list[dict[str, Any]] = []
        errors: list[str] = []

        for target_length in context_lengths:
            for position in needle_positions:
                try:
                    prompt = self._build_prompt(
                        needle, question, target_length, position
                    )

                    result = engine.generate(
                        prompt=prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )

                    response = result.output.strip()
                    found = (
                        needle.lower() in response.lower()
                        or "kitt-42" in response.lower()
                    )

                    outputs.append(
                        {
                            "context_length": target_length,
                            "needle_position": position,
                            "prompt_tokens": result.prompt_tokens,
                            "found_needle": found,
                            "response_preview": response[:200],
                            "latency_ms": result.metrics.total_latency_ms,
                        }
                    )

                except Exception as e:
                    error_msg = f"Error at length={target_length}, pos={position}: {e}"
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

    def _build_prompt(
        self,
        needle: str,
        question: str,
        target_chars: int,
        position: float,
    ) -> str:
        """Build a prompt with the needle hidden at a specific position."""
        # Approximate chars needed (rough: 4 chars per token)
        filler_chars = max(0, target_chars - len(needle) - len(question) - 100)
        filler_len = len(_FILLER_SENTENCE)
        num_sentences = filler_chars // filler_len if filler_len > 0 else 0

        # Place needle at the specified position
        needle_index = int(num_sentences * position)

        parts = []
        parts.append(
            "Read the following text carefully and answer the question at the end.\n\n"
        )
        for i in range(num_sentences):
            if i == needle_index:
                parts.append(f"{needle} ")
            parts.append(_FILLER_SENTENCE)

        parts.append(f"\n\nQuestion: {question}\nAnswer:")
        return "".join(parts)

    def _aggregate_metrics(self, outputs: list[dict[str, Any]]) -> dict[str, Any]:
        if not outputs:
            return {}

        total = len(outputs)
        found = sum(1 for o in outputs if o["found_needle"])
        overall_accuracy = found / total if total > 0 else 0

        # Accuracy by context length
        by_length: dict[int, list[bool]] = {}
        for o in outputs:
            length = o["context_length"]
            by_length.setdefault(length, []).append(o["found_needle"])

        accuracy_by_length = {
            str(length): round(sum(vals) / len(vals), 4)
            for length, vals in sorted(by_length.items())
        }

        return {
            "total_tests": total,
            "needles_found": found,
            "overall_accuracy": round(overall_accuracy, 4),
            "accuracy_by_context_length": accuracy_by_length,
        }
