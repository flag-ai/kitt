"""HellaSwag benchmark."""

import logging
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = (
    "Complete the following sentence with the most logical continuation.\n\n"
    "{context}\n\n"
    "A. {choice_a}\n"
    "B. {choice_b}\n"
    "C. {choice_c}\n"
    "D. {choice_d}\n\n"
    "Answer:"
)

LABEL_MAP = {0: "A", 1: "B", 2: "C", 3: "D"}


@register_benchmark
class HellaSwagBenchmark(LLMBenchmark):
    """HellaSwag benchmark.

    Tests commonsense natural language inference - can the model
    pick the most plausible continuation of a given context?
    """

    name = "hellaswag"
    version = "1.0.0"
    category = "quality_standard"
    description = "HellaSwag - Commonsense NLI for sentence completion"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        """Run HellaSwag evaluation."""
        sampling = config.get("sampling", {})
        max_tokens = sampling.get("max_tokens", 10)
        temperature = sampling.get("temperature", 0.0)

        prompts_config = config.get("prompts", {})
        template = prompts_config.get("template", DEFAULT_TEMPLATE)

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
            context = question.get("ctx", question.get("context", ""))
            endings = question.get("endings", [])
            label = question.get("label", -1)

            if len(endings) < 4:
                endings.extend([""] * (4 - len(endings)))

            prompt = template.format(
                context=context,
                choice_a=endings[0],
                choice_b=endings[1],
                choice_c=endings[2],
                choice_d=endings[3],
            )

            try:
                result = engine.generate(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                predicted = self._extract_answer(result.output)
                expected = (
                    LABEL_MAP.get(label, "") if isinstance(label, int) else str(label)
                )

                is_correct = predicted.upper() == expected.upper()
                if is_correct:
                    correct += 1
                total += 1

                outputs.append(
                    {
                        "index": i,
                        "context": context[:200],
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

        accuracy = correct / total if total > 0 else 0.0

        metrics = {
            "accuracy": round(accuracy, 4),
            "correct": correct,
            "total": total,
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
        """Load HellaSwag questions."""
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
        return questions

    @staticmethod
    def _extract_answer(output: str) -> str:
        """Extract answer letter from model output."""
        import re

        output = output.strip()
        match = re.search(r"\b([ABCD])\b", output)
        if match:
            return match.group(1)
        if output and output[0].upper() in "ABCD":
            return output[0].upper()
        return ""
