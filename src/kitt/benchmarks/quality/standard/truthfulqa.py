"""TruthfulQA benchmark."""

import logging
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = "Q: {question}\nA:"


@register_benchmark
class TruthfulQABenchmark(LLMBenchmark):
    """TruthfulQA benchmark.

    Tests whether a model generates truthful answers to questions
    that are designed to elicit common misconceptions and falsehoods.
    Uses multiple choice format from the mc1_targets / mc2_targets splits.
    """

    name = "truthfulqa"
    version = "1.0.0"
    category = "quality_standard"
    description = "TruthfulQA - Measures truthfulness in model responses"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        """Run TruthfulQA evaluation."""
        sampling = config.get("sampling", {})
        max_tokens = sampling.get("max_tokens", 256)
        temperature = sampling.get("temperature", 0.0)

        prompts_config = config.get("prompts", {})
        template = prompts_config.get("template", DEFAULT_TEMPLATE)
        eval_config = config.get("evaluation", {})
        eval_method = eval_config.get("method", "mc1")

        questions = self._load_questions(config)

        if not questions:
            return BenchmarkResult(
                test_name=self.name,
                test_version=self.version,
                passed=True,
                metrics={"total_samples": 0, "note": "No dataset loaded"},
                outputs=[],
                errors=["No questions loaded - dataset may not be available"],
            )

        outputs: list[dict[str, Any]] = []
        errors: list[str] = []
        correct = 0
        total = 0

        for i, question in enumerate(questions):
            q_text = question.get("question", str(question))
            prompt = template.format(question=q_text)

            try:
                result = engine.generate(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                # For MC evaluation, score against choices
                is_correct = False
                if eval_method == "mc1" and "mc1_targets" in question:
                    is_correct = self._evaluate_mc1(
                        result.output, question["mc1_targets"]
                    )
                elif "best_answer" in question:
                    is_correct = self._evaluate_open(
                        result.output, question["best_answer"]
                    )

                if is_correct:
                    correct += 1
                total += 1

                outputs.append(
                    {
                        "index": i,
                        "question": q_text[:200],
                        "output": result.output[:500],
                        "correct": is_correct,
                        "metrics": {
                            "tps": result.metrics.tps,
                            "total_latency_ms": result.metrics.total_latency_ms,
                        },
                    }
                )

            except Exception as e:
                error_msg = f"Error on question {i}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                total += 1

        accuracy = correct / total if total > 0 else 0.0

        metrics = {
            "accuracy": round(accuracy, 4),
            "correct": correct,
            "total": total,
            "eval_method": eval_method,
            "error_count": len(errors),
        }

        return BenchmarkResult(
            test_name=self.name,
            test_version=self.version,
            passed=len(errors) == 0,
            metrics=metrics,
            outputs=outputs,
            errors=errors,
        )

    def _load_questions(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Load TruthfulQA questions."""
        dataset_config = config.get("dataset", {})
        source = dataset_config.get("source")
        local_path = dataset_config.get("local_path")
        sample_size = dataset_config.get("sample_size")

        if source:
            try:
                from kitt.benchmarks.dataset_manager import DatasetManager

                raw = DatasetManager.load_from_huggingface(
                    source,
                    split=dataset_config.get("split", "validation"),
                    sample_size=sample_size,
                )
                return self._parse_raw(raw)
            except Exception as e:
                logger.warning(f"Failed to load HuggingFace dataset: {e}")
                return []

        if local_path:
            try:
                from pathlib import Path

                from kitt.benchmarks.dataset_manager import DatasetManager

                raw = DatasetManager.load_from_directory(
                    Path(local_path), sample_size=sample_size
                )
                return self._parse_raw(raw)
            except Exception as e:
                logger.warning(f"Failed to load local dataset: {e}")
                return []

        return []

    def _parse_raw(self, raw_items: list[Any]) -> list[dict[str, Any]]:
        """Parse raw dataset items."""
        questions = []
        for item in raw_items:
            if isinstance(item, dict):
                questions.append(item)
            elif isinstance(item, str):
                questions.append({"question": item})
        return questions

    @staticmethod
    def _evaluate_mc1(output: str, mc1_targets: dict[str, Any]) -> bool:
        """Evaluate using MC1 (single true answer).

        mc1_targets has 'choices' and 'labels' where labels[0]=1 is correct.
        """
        choices = mc1_targets.get("choices", [])
        labels = mc1_targets.get("labels", [])
        if not choices or not labels:
            return False

        # Find best matching choice in output
        output_lower = output.lower().strip()
        best_match_idx = -1
        best_match_len = 0

        for idx, choice in enumerate(choices):
            choice_lower = choice.lower().strip()
            if choice_lower in output_lower and len(choice_lower) > best_match_len:
                best_match_idx = idx
                best_match_len = len(choice_lower)

        if best_match_idx >= 0 and best_match_idx < len(labels):
            return labels[best_match_idx] == 1

        return False

    @staticmethod
    def _evaluate_open(output: str, best_answer: str) -> bool:
        """Simple open-ended evaluation: check if best answer is contained."""
        return best_answer.lower().strip() in output.lower().strip()
