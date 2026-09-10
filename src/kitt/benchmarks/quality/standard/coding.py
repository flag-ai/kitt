"""Coding benchmark — evaluate code generation with pass@k."""

import logging
import re
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

# Built-in simple test problems (no external dataset needed)
BUILT_IN_PROBLEMS = [
    {
        "prompt": "Write a Python function `is_palindrome(s: str) -> bool` that checks if a string is a palindrome.",
        "test_code": "assert is_palindrome('racecar') == True\nassert is_palindrome('hello') == False\nassert is_palindrome('') == True\nassert is_palindrome('a') == True",
        "entry_point": "is_palindrome",
    },
    {
        "prompt": "Write a Python function `fibonacci(n: int) -> int` that returns the n-th Fibonacci number (0-indexed).",
        "test_code": "assert fibonacci(0) == 0\nassert fibonacci(1) == 1\nassert fibonacci(10) == 55\nassert fibonacci(5) == 5",
        "entry_point": "fibonacci",
    },
    {
        "prompt": "Write a Python function `reverse_words(s: str) -> str` that reverses the order of words in a string.",
        "test_code": "assert reverse_words('hello world') == 'world hello'\nassert reverse_words('a') == 'a'\nassert reverse_words('') == ''",
        "entry_point": "reverse_words",
    },
    {
        "prompt": "Write a Python function `count_vowels(s: str) -> int` that counts vowels (a,e,i,o,u) in a string, case-insensitive.",
        "test_code": "assert count_vowels('hello') == 2\nassert count_vowels('AEIOU') == 5\nassert count_vowels('xyz') == 0",
        "entry_point": "count_vowels",
    },
    {
        "prompt": "Write a Python function `flatten(lst: list) -> list` that flattens a nested list.",
        "test_code": "assert flatten([1, [2, 3], [4, [5]]]) == [1, 2, 3, 4, 5]\nassert flatten([]) == []\nassert flatten([1, 2, 3]) == [1, 2, 3]",
        "entry_point": "flatten",
    },
]


@register_benchmark
class CodingBenchmark(LLMBenchmark):
    """Evaluate code generation with execution-based pass@k."""

    name = "coding"
    version = "1.0.0"
    category = "quality_standard"
    description = "Code generation benchmark with test execution"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        problems = config.get("problems", BUILT_IN_PROBLEMS)
        max_tokens = config.get("max_tokens", 512)
        temperature = config.get("temperature", 0.0)
        k_values = config.get("k_values", [1])
        sample_size = config.get("sample_size")

        if sample_size and sample_size < len(problems):
            problems = problems[:sample_size]

        outputs: list[dict[str, Any]] = []
        errors: list[str] = []
        total_pass: dict[int, int] = {k: 0 for k in k_values}
        total_problems = len(problems)
        syntax_errors = 0

        for i, problem in enumerate(problems):
            prompt = self._build_prompt(problem["prompt"])

            # Generate k samples
            samples: list[str] = []
            max_k = max(k_values)
            for _ in range(max_k):
                try:
                    result = engine.generate(
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    code = self._extract_code(result.output)
                    samples.append(code)
                except Exception as e:
                    errors.append(f"Problem {i}: {e}")
                    samples.append("")

            # Test samples
            pass_results = []
            for code in samples:
                if not code.strip():
                    pass_results.append(False)
                    continue

                passed, has_syntax_error = self._test_code(
                    code, problem["test_code"], problem.get("entry_point", "")
                )
                pass_results.append(passed)
                if has_syntax_error:
                    syntax_errors += 1

            # Calculate pass@k
            for k in k_values:
                if any(pass_results[:k]):
                    total_pass[k] += 1

            outputs.append(
                {
                    "index": i,
                    "entry_point": problem.get("entry_point", ""),
                    "pass_results": pass_results,
                    "pass_at_1": pass_results[0] if pass_results else False,
                    "code_sample": samples[0][:300] if samples else "",
                }
            )

        metrics: dict[str, Any] = {
            "total": total_problems,
            "syntax_error_rate": round(
                syntax_errors / (total_problems * max(k_values)), 4
            )
            if total_problems
            else 0,
        }
        for k in k_values:
            rate = total_pass[k] / total_problems if total_problems else 0
            metrics[f"pass_at_{k}"] = round(rate, 4)

        # Primary accuracy metric
        metrics["accuracy"] = metrics.get("pass_at_1", 0)

        return BenchmarkResult(
            test_name=self.name,
            test_version=self.version,
            passed=len(errors) == 0,
            metrics=metrics,
            outputs=outputs,
            errors=errors,
        )

    def _build_prompt(self, problem_text: str) -> str:
        return (
            f"{problem_text}\n\n"
            "Respond with only the Python code, no explanations.\n"
            "```python\n"
        )

    def _extract_code(self, output: str) -> str:
        """Extract Python code from model output."""
        # Try to find code block
        code_match = re.search(r"```(?:python)?\s*\n(.*?)```", output, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()

        # Try to find function definition
        func_match = re.search(r"(def \w+.*)", output, re.DOTALL)
        if func_match:
            return func_match.group(1).strip()

        return output.strip()

    def _test_code(
        self, code: str, test_code: str, entry_point: str
    ) -> tuple[bool, bool]:
        """Execute code and tests, return (passed, has_syntax_error)."""
        try:
            # Compile to check syntax
            compile(code, "<generated>", "exec")
        except SyntaxError:
            return False, True

        try:
            namespace: dict[str, Any] = {}
            exec(code, namespace)
            exec(test_code, namespace)
            return True, False
        except AssertionError:
            return False, False
        except Exception:
            return False, False
