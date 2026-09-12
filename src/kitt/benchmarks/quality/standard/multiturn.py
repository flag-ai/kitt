"""Multi-turn conversation benchmark."""

import logging
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

DEFAULT_CONVERSATIONS = [
    {
        "name": "math_consistency",
        "turns": [
            "What is 15 * 23?",
            "Now multiply that result by 2.",
            "What was the original number I asked you to multiply?",
        ],
    },
    {
        "name": "identity_recall",
        "turns": [
            "My name is Alice and I live in Portland.",
            "What is the population of my city?",
            "What is my name?",
        ],
    },
    {
        "name": "topic_coherence",
        "turns": [
            "Explain photosynthesis briefly.",
            "How does this relate to the carbon cycle?",
            "Summarize what we've discussed so far.",
        ],
    },
]


@register_benchmark
class MultiTurnBenchmark(LLMBenchmark):
    """Evaluate multi-turn conversation consistency.

    Tests whether the model maintains context across multiple turns
    of conversation. Scores based on coherence and factual consistency.
    """

    name = "multiturn"
    version = "1.0.0"
    category = "quality_standard"
    description = "Evaluate multi-turn conversation consistency"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        conversations = config.get("conversations", DEFAULT_CONVERSATIONS)
        max_tokens = config.get("max_tokens", 256)
        temperature = config.get("temperature", 0.0)

        outputs: list[dict[str, Any]] = []
        errors: list[str] = []

        for conv in conversations:
            conv_name = conv.get("name", "unnamed")
            turns = conv.get("turns", [])
            history = ""
            turn_outputs = []

            for turn_idx, user_msg in enumerate(turns):
                # Build multi-turn prompt with history
                if history:
                    prompt = f"{history}\nUser: {user_msg}\nAssistant:"
                else:
                    prompt = f"User: {user_msg}\nAssistant:"

                try:
                    result = engine.generate(
                        prompt=prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )

                    response = result.output.strip()
                    turn_outputs.append(
                        {
                            "turn": turn_idx,
                            "user": user_msg,
                            "assistant": response[:500],
                            "tokens": result.completion_tokens,
                        }
                    )

                    # Append to history
                    history = f"{prompt} {response}"

                except Exception as e:
                    errors.append(f"Error in {conv_name} turn {turn_idx}: {e}")
                    break

            # Score: did we get all turns completed?
            completion_rate = len(turn_outputs) / len(turns) if turns else 0

            outputs.append(
                {
                    "conversation": conv_name,
                    "turns_total": len(turns),
                    "turns_completed": len(turn_outputs),
                    "completion_rate": completion_rate,
                    "turn_details": turn_outputs,
                }
            )

        metrics = self._aggregate_metrics(outputs)

        return BenchmarkResult(
            test_name=self.name,
            test_version=self.version,
            passed=len(errors) == 0 and metrics.get("avg_completion_rate", 0) >= 0.8,
            metrics=metrics,
            outputs=outputs,
            errors=errors,
        )

    def _aggregate_metrics(self, outputs: list[dict[str, Any]]) -> dict[str, Any]:
        if not outputs:
            return {}

        completion_rates = [o["completion_rate"] for o in outputs]
        total_turns = sum(o["turns_completed"] for o in outputs)

        return {
            "total_conversations": len(outputs),
            "total_turns_completed": total_turns,
            "avg_completion_rate": round(
                sum(completion_rates) / len(completion_rates), 4
            ),
            "min_completion_rate": round(min(completion_rates), 4),
        }
