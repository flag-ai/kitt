"""MMLU (Massive Multitask Language Understanding) benchmark."""

import logging
import re
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

ANSWER_MAP = {0: "A", 1: "B", 2: "C", 3: "D"}
LETTER_TO_INDEX = {"A": 0, "B": 1, "C": 2, "D": 3}

DEFAULT_TEMPLATE = (
    "The following are multiple choice questions (with answers) about {subject}.\n\n"
    "Question: {question}\n"
    "A. {choice_a}\n"
    "B. {choice_b}\n"
    "C. {choice_c}\n"
    "D. {choice_d}\n"
    "Answer:"
)


@register_benchmark
class MMLUBenchmark(LLMBenchmark):
    """Massive Multitask Language Understanding benchmark.

    Tests knowledge across 57 subjects in STEM, humanities, social sciences.
    Uses multiple choice format with answer extraction.
    """

    name = "mmlu"
    version = "1.0.0"
    category = "quality_standard"
    description = "MMLU - 57 subjects across STEM, humanities, social sciences"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        """Run MMLU evaluation."""
        config.get("dataset", {})
        prompts_config = config.get("prompts", {})
        eval_config = config.get("evaluation", {})
        sampling = config.get("sampling", {})

        template = prompts_config.get("template", DEFAULT_TEMPLATE)
        max_tokens = sampling.get("max_tokens", 10)
        temperature = sampling.get("temperature", 0.0)

        extraction_method = eval_config.get("answer_extraction", {}).get(
            "method", "first_letter"
        )

        # Load questions (from dataset manager or inline)
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
        per_subject: dict[str, dict[str, int]] = {}

        for i, question in enumerate(questions):
            subject = question.get("subject", "unknown")
            if subject not in per_subject:
                per_subject[subject] = {"correct": 0, "total": 0}

            prompt = self._format_prompt(template, question)

            try:
                result = engine.generate(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                predicted = self._extract_answer(result.output, extraction_method)
                expected = question.get("answer", "")
                if isinstance(expected, int):
                    expected = ANSWER_MAP.get(expected, "")

                is_correct = predicted.upper() == expected.upper()
                if is_correct:
                    correct += 1
                    per_subject[subject]["correct"] += 1
                total += 1
                per_subject[subject]["total"] += 1

                outputs.append(
                    {
                        "index": i,
                        "subject": subject,
                        "predicted": predicted,
                        "expected": expected,
                        "correct": is_correct,
                        "raw_output": result.output[:200],
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
                per_subject[subject]["total"] += 1

        # Calculate metrics
        accuracy = correct / total if total > 0 else 0.0
        subject_accuracies = {
            s: stats["correct"] / stats["total"] if stats["total"] > 0 else 0.0
            for s, stats in per_subject.items()
        }

        metrics = {
            "accuracy": round(accuracy, 4),
            "correct": correct,
            "total": total,
            "per_subject_accuracy": subject_accuracies,
            "num_subjects": len(per_subject),
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
        """Load MMLU questions from dataset."""
        dataset_config = config.get("dataset", {})
        source = dataset_config.get("source")
        local_path = dataset_config.get("local_path")
        sample_size = dataset_config.get("sample_size")

        if source:
            try:
                from kitt.benchmarks.dataset_manager import DatasetManager

                raw = DatasetManager.load_from_huggingface(
                    source,
                    split=dataset_config.get("split", "test"),
                    sample_size=sample_size,
                )
                return self._parse_raw_dataset(raw)
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
                return self._parse_raw_dataset(raw)
            except Exception as e:
                logger.warning(f"Failed to load local dataset: {e}")
                return []

        return []

    def _parse_raw_dataset(self, raw_items: list[Any]) -> list[dict[str, Any]]:
        """Parse raw dataset items into question format."""
        questions = []
        for item in raw_items:
            if isinstance(item, dict):
                questions.append(item)
            elif isinstance(item, str):
                # Try to parse as a formatted question
                questions.append({"question": item, "subject": "unknown"})
        return questions

    def _format_prompt(self, template: str, question: dict[str, Any]) -> str:
        """Format a question into a prompt string."""
        choices = question.get("choices", ["", "", "", ""])
        return template.format(
            subject=question.get("subject", "general knowledge"),
            question=question.get("question", ""),
            choice_a=choices[0] if len(choices) > 0 else "",
            choice_b=choices[1] if len(choices) > 1 else "",
            choice_c=choices[2] if len(choices) > 2 else "",
            choice_d=choices[3] if len(choices) > 3 else "",
            **{f"choices[{i}]": c for i, c in enumerate(choices)},
        )

    @staticmethod
    def _extract_answer(output: str, method: str = "first_letter") -> str:
        """Extract answer letter from model output."""
        output = output.strip()

        if method == "first_letter":
            # Look for first occurrence of A, B, C, or D
            match = re.search(r"\b([ABCD])\b", output)
            if match:
                return match.group(1)
            # Fallback: first character
            if output and output[0].upper() in "ABCD":
                return output[0].upper()

        return ""
