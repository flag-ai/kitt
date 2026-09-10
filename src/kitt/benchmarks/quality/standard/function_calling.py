"""Function calling benchmark — evaluate tool use capabilities."""

import json
import logging
import re
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

# Built-in tool definitions for testing
TOOL_DEFINITIONS = [
    {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "parameters": {
            "location": {"type": "string", "required": True},
            "unit": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"],
                "required": False,
            },
        },
    },
    {
        "name": "search_web",
        "description": "Search the web for information",
        "parameters": {
            "query": {"type": "string", "required": True},
            "max_results": {"type": "integer", "required": False},
        },
    },
    {
        "name": "calculate",
        "description": "Perform a mathematical calculation",
        "parameters": {
            "expression": {"type": "string", "required": True},
        },
    },
    {
        "name": "send_email",
        "description": "Send an email to a recipient",
        "parameters": {
            "to": {"type": "string", "required": True},
            "subject": {"type": "string", "required": True},
            "body": {"type": "string", "required": True},
        },
    },
]

# Test cases: (user_query, expected_function, expected_args_subset)
TEST_CASES = [
    ("What's the weather like in Tokyo?", "get_weather", {"location": "Tokyo"}),
    (
        "Search for the latest news about AI",
        "search_web",
        {"query": "latest news about AI"},
    ),
    ("What is 15 * 23?", "calculate", {"expression": "15 * 23"}),
    (
        "Send an email to alice@example.com with subject Hello",
        "send_email",
        {"to": "alice@example.com"},
    ),
    (
        "What's the temperature in Paris in celsius?",
        "get_weather",
        {"location": "Paris"},
    ),
    ("Look up 'quantum computing breakthroughs'", "search_web", {}),
    ("Calculate the square root of 144", "calculate", {}),
    (
        "Email bob@test.com about the meeting tomorrow",
        "send_email",
        {"to": "bob@test.com"},
    ),
]


@register_benchmark
class FunctionCallingBenchmark(LLMBenchmark):
    """Evaluate function/tool calling capabilities."""

    name = "function_calling"
    version = "1.0.0"
    category = "quality_standard"
    description = "Evaluate function selection and argument generation accuracy"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        tools = config.get("tools", TOOL_DEFINITIONS)
        test_cases = config.get("test_cases", TEST_CASES)
        max_tokens = config.get("max_tokens", 512)
        temperature = config.get("temperature", 0.0)
        sample_size = config.get("sample_size")

        if sample_size and sample_size < len(test_cases):
            test_cases = test_cases[:sample_size]

        tools_desc = self._format_tools(tools)
        tool_names = {t["name"] for t in tools}

        outputs: list[dict[str, Any]] = []
        errors: list[str] = []
        correct_function = 0
        correct_args = 0
        json_parse_success = 0
        hallucinated_functions = 0
        total = len(test_cases)

        for i, (query, expected_func, expected_args) in enumerate(test_cases):
            prompt = self._build_prompt(tools_desc, query)
            try:
                result = engine.generate(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

                raw_output = result.output.strip()
                parsed = self._parse_function_call(raw_output)

                is_json_valid = parsed is not None
                if is_json_valid:
                    json_parse_success += 1

                func_name = parsed.get("name", "") if parsed else ""
                func_args = parsed.get("arguments", {}) if parsed else {}

                func_correct = func_name == expected_func
                if func_correct:
                    correct_function += 1

                # Check if function is hallucinated
                if func_name and func_name not in tool_names:
                    hallucinated_functions += 1

                # Check args
                args_correct = (
                    all(func_args.get(k) is not None for k in expected_args)
                    if func_correct and expected_args
                    else func_correct
                )

                if args_correct:
                    correct_args += 1

                outputs.append(
                    {
                        "index": i,
                        "query": query,
                        "expected_function": expected_func,
                        "predicted_function": func_name,
                        "function_correct": func_correct,
                        "args_correct": args_correct,
                        "json_valid": is_json_valid,
                        "raw_output": raw_output[:300],
                    }
                )

            except Exception as e:
                errors.append(f"Test {i}: {e}")
                outputs.append(
                    {
                        "index": i,
                        "query": query,
                        "expected_function": expected_func,
                        "error": str(e),
                    }
                )

        metrics = {
            "correct_function_selection_rate": round(correct_function / total, 4)
            if total
            else 0,
            "argument_accuracy": round(correct_args / total, 4) if total else 0,
            "json_parse_success_rate": round(json_parse_success / total, 4)
            if total
            else 0,
            "hallucinated_function_rate": round(hallucinated_functions / total, 4)
            if total
            else 0,
            "correct_functions": correct_function,
            "correct_args": correct_args,
            "total": total,
        }

        return BenchmarkResult(
            test_name=self.name,
            test_version=self.version,
            passed=len(errors) == 0
            and (correct_function / total >= 0.5 if total else False),
            metrics=metrics,
            outputs=outputs,
            errors=errors,
        )

    def _format_tools(self, tools: list[dict]) -> str:
        """Format tool definitions for prompt."""
        parts = []
        for tool in tools:
            params = ", ".join(
                f"{k}: {v.get('type', 'string')}"
                + (" (required)" if v.get("required") else "")
                for k, v in tool.get("parameters", {}).items()
            )
            parts.append(f"- {tool['name']}({params}): {tool['description']}")
        return "\n".join(parts)

    def _build_prompt(self, tools_desc: str, query: str) -> str:
        return (
            f"You are a helpful assistant with access to the following tools:\n\n"
            f"{tools_desc}\n\n"
            f"When the user asks you to do something, respond with a JSON object "
            f"containing the function name and arguments.\n"
            f'Format: {{"name": "function_name", "arguments": {{"arg1": "value1"}}}}\n\n'
            f"User: {query}\n\n"
            f"Response (JSON only):"
        )

    def _parse_function_call(self, output: str) -> dict[str, Any] | None:
        """Try to parse a function call from model output."""
        # Try direct JSON parse
        try:
            parsed = json.loads(output)
            if isinstance(parsed, dict) and "name" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

        # Try to find JSON in output
        json_match = re.search(r'\{[^{}]*"name"[^{}]*\}', output, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                if isinstance(parsed, dict) and "name" in parsed:
                    return parsed
            except json.JSONDecodeError:
                pass

        # Try nested JSON
        json_match = re.search(r'\{.*"name".*\}', output, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                if isinstance(parsed, dict) and "name" in parsed:
                    return parsed
            except json.JSONDecodeError:
                pass

        return None
