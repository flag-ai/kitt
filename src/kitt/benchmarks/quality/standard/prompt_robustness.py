"""Prompt robustness benchmark — measure consistency across paraphrases."""

import logging
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

# Default prompt variants: same question, different phrasing
DEFAULT_PROMPT_GROUPS = [
    {
        "canonical": "What is the capital of France?",
        "variants": [
            "Tell me the capital city of France.",
            "Which city is France's capital?",
            "Name the capital of France.",
        ],
    },
    {
        "canonical": "Explain photosynthesis in simple terms.",
        "variants": [
            "Can you describe photosynthesis simply?",
            "How does photosynthesis work? Keep it simple.",
            "Give a simple explanation of photosynthesis.",
        ],
    },
    {
        "canonical": "What are the three states of matter?",
        "variants": [
            "List the three states of matter.",
            "Name the three phases of matter.",
            "What forms can matter take? Name three.",
        ],
    },
]


@register_benchmark
class PromptRobustnessBenchmark(LLMBenchmark):
    """Measure output consistency across paraphrased prompts."""

    name = "prompt_robustness"
    version = "1.0.0"
    category = "quality_standard"
    description = "Evaluate consistency of outputs across prompt paraphrases"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        prompt_groups = config.get("prompt_groups", DEFAULT_PROMPT_GROUPS)
        max_tokens = config.get("max_tokens", 256)
        temperature = config.get("temperature", 0.0)

        outputs: list[dict[str, Any]] = []
        errors: list[str] = []
        consistency_scores: list[float] = []

        for group_idx, group in enumerate(prompt_groups):
            canonical = group["canonical"]
            variants = group.get("variants", [])
            all_prompts = [canonical] + variants

            group_outputs: list[str] = []

            for prompt in all_prompts:
                try:
                    result = engine.generate(
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    group_outputs.append(result.output.strip().lower())
                except Exception as e:
                    errors.append(f"Group {group_idx}, prompt failed: {e}")
                    group_outputs.append("")

            # Compute pairwise consistency
            score = self._compute_consistency(group_outputs)
            consistency_scores.append(score)

            outputs.append(
                {
                    "group_index": group_idx,
                    "canonical": canonical,
                    "num_variants": len(variants),
                    "consistency_score": round(score, 4),
                    "outputs": [o[:200] for o in group_outputs],
                }
            )

        # Aggregate
        avg_consistency = (
            sum(consistency_scores) / len(consistency_scores)
            if consistency_scores
            else 0
        )
        worst = min(consistency_scores) if consistency_scores else 0

        metrics = {
            "consistency_score": round(avg_consistency, 4),
            "semantic_stability": round(avg_consistency, 4),
            "worst_case_divergence": round(1 - worst, 4),
            "num_groups": len(prompt_groups),
            "total_prompts": sum(1 + len(g.get("variants", [])) for g in prompt_groups),
        }

        return BenchmarkResult(
            test_name=self.name,
            test_version=self.version,
            passed=len(errors) == 0 and avg_consistency >= 0.3,
            metrics=metrics,
            outputs=outputs,
            errors=errors,
        )

    def _compute_consistency(self, outputs: list[str]) -> float:
        """Compute word-overlap-based consistency score.

        Uses Jaccard similarity between word sets of all output pairs.
        """
        if len(outputs) < 2:
            return 1.0

        non_empty = [o for o in outputs if o]
        if len(non_empty) < 2:
            return 0.0

        word_sets = [set(o.split()) for o in non_empty]
        similarities = []

        for i in range(len(word_sets)):
            for j in range(i + 1, len(word_sets)):
                intersection = word_sets[i] & word_sets[j]
                union = word_sets[i] | word_sets[j]
                if union:
                    similarities.append(len(intersection) / len(union))
                else:
                    similarities.append(0.0)

        return sum(similarities) / len(similarities) if similarities else 0.0
