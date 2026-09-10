"""GSM8K (Grade School Math 8K) benchmark."""

import logging
import re
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = (
    "Solve this math problem step by step.\n\n"
    "Question: {question}\n\n"
    "Show your work and provide the final numerical answer after ####."
)


@register_benchmark
class GSM8KBenchmark(LLMBenchmark):
    """GSM8K - Grade School Math benchmark.

    Tests mathematical reasoning with 8,500 grade school math problems.
    Answers are extracted from the #### delimiter format.
    """

    name = "gsm8k"
    version = "1.0.0"
    category = "quality_standard"
    description = "GSM8K - Grade school math reasoning with step-by-step solutions"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        """Run GSM8K evaluation."""
        sampling = config.get("sampling", {})
        max_tokens = sampling.get("max_tokens", 512)
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
            prompt = template.format(question=question.get("question", str(question)))

            try:
                result = engine.generate(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                predicted = self._extract_number(result.output)
                expected = question.get("answer", "")
                if isinstance(expected, str):
                    expected = self._extract_number(expected)

                is_correct = self._numbers_match(predicted, expected)
                if is_correct:
                    correct += 1
                total += 1

                outputs.append(
                    {
                        "index": i,
                        "predicted": predicted,
                        "expected": expected,
                        "correct": is_correct,
                        "raw_output": result.output[:500],
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
        """Load GSM8K questions."""
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
        """Parse raw items into question dicts."""
        questions = []
        for item in raw_items:
            if isinstance(item, dict):
                questions.append(item)
            elif isinstance(item, str):
                questions.append({"question": item})
        return questions

    @staticmethod
    def _extract_number(text: str) -> str:
        """Extract final numerical answer from text.

        Looks for #### delimiter first, then falls back to last number.
        """
        text = text.strip()

        # Look for #### delimiter (GSM8K format)
        match = re.search(r"####\s*([\-\d,\.]+)", text)
        if match:
            return match.group(1).replace(",", "").strip()

        # Fallback: find last number in text
        numbers = re.findall(r"[\-]?\d[\d,]*\.?\d*", text)
        if numbers:
            return numbers[-1].replace(",", "")

        return ""

    @staticmethod
    def _numbers_match(predicted: str, expected: str) -> bool:
        """Compare two numerical answers with tolerance."""
        try:
            p = float(predicted.replace(",", ""))
            e = float(expected.replace(",", ""))
            return abs(p - e) < 1e-6
        except (ValueError, TypeError):
            return predicted.strip() == expected.strip()
