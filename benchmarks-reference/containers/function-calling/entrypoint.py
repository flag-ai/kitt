#!/usr/bin/env python3
"""Function-calling benchmark — tool-schema validation.

For each item:
  1. Send a chat request with a "tools" array containing one or more
     function definitions.
  2. Pull the tool call from the response (OpenAI tool_calls shape).
  3. Validate the arguments against the function's JSON schema.
  4. Optionally check the chosen function name matches the expected
     one.

Score is the fraction of items where the chosen tool was correct AND
the arguments validated.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from jsonschema import Draft202012Validator, ValidationError

INLINE_ITEMS: list[dict[str, Any]] = [
    {
        "user": "What's the weather like in Paris?",
        "expected_tool": "get_weather",
        "tools": [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather for a city.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                        "units": {"type": "string", "enum": ["metric", "imperial"]},
                    },
                    "required": ["city"],
                    "additionalProperties": False,
                },
            },
        }],
    },
    {
        "user": "Look up the definition of entropy.",
        "expected_tool": "lookup",
        "tools": [{
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "Look up a term in a reference dictionary.",
                "parameters": {
                    "type": "object",
                    "properties": {"q": {"type": "string"}},
                    "required": ["q"],
                    "additionalProperties": False,
                },
            },
        }],
    },
]


def call(url: str, model: str, item: dict[str, Any]) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": item["user"]}],
        "tools": item["tools"],
        "tool_choice": "auto",
        "max_tokens": 256,
        "temperature": 0.0,
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, json=body)
        r.raise_for_status()
        return r.json()


def extract_tool_call(response: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Return (name, arguments_dict) from either the tool_calls or the
    legacy function_call response shapes. Falls back to parsing the
    message content as JSON so the mock-engine smoke test still
    exercises the validator path."""
    choices = response.get("choices") or []
    if not choices:
        return None
    msg = choices[0].get("message") or {}
    tool_calls = msg.get("tool_calls") or []
    if tool_calls:
        fn = tool_calls[0].get("function", {})
        name = fn.get("name", "")
        args_raw = fn.get("arguments", "{}")
    elif msg.get("function_call"):
        fc = msg["function_call"]
        name = fc.get("name", "")
        args_raw = fc.get("arguments", "{}")
    else:
        # Last resort: try to parse message content as a JSON object.
        content = msg.get("content") or choices[0].get("text", "") or ""
        try:
            obj = json.loads(content.strip())
        except json.JSONDecodeError:
            return None
        name = obj.get("name", "")
        args = obj.get("arguments", {}) or {}
        return name, args if isinstance(args, dict) else {}

    try:
        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
    except json.JSONDecodeError:
        args = {}
    if not isinstance(args, dict):
        args = {}
    return name, args


def validate(item: dict[str, Any], name: str, args: dict[str, Any]) -> tuple[bool, str]:
    expected = item.get("expected_tool")
    matching_tool = next(
        (t for t in item["tools"] if t.get("function", {}).get("name") == name),
        None,
    )
    if expected and name != expected:
        return False, f"wrong-tool: got {name!r} want {expected!r}"
    if matching_tool is None:
        return False, f"unknown-tool: {name!r}"
    schema = matching_tool["function"].get("parameters") or {}
    try:
        Draft202012Validator(schema).validate(args)
    except ValidationError as exc:
        return False, f"args-invalid: {exc.message}"
    return True, "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine-url", required=True)
    ap.add_argument("--model-name", required=True)
    ap.add_argument("--config", default="/config.json")
    ap.add_argument("--results", default="/results/out.json")
    args = ap.parse_args()

    cfg: dict[str, Any] = {}
    cfg_path = Path(args.config)
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
        except json.JSONDecodeError:
            cfg = {}

    items = cfg.get("items") or INLINE_ITEMS
    chat_url = args.engine_url.rstrip("/") + "/v1/chat/completions"

    start = time.monotonic()
    passed = 0
    total = 0
    details: list[dict[str, Any]] = []
    for item in items:
        total += 1
        try:
            resp = call(chat_url, args.model_name, item)
        except httpx.HTTPError as exc:
            details.append({"user": item["user"], "passed": False, "error": str(exc)})
            continue
        extracted = extract_tool_call(resp)
        if extracted is None:
            details.append({"user": item["user"], "passed": False, "error": "no-tool-call"})
            continue
        name, args_dict = extracted
        ok, detail = validate(item, name, args_dict)
        if ok:
            passed += 1
        details.append({"user": item["user"], "tool": name, "args": args_dict, "passed": ok, "detail": detail})
    duration_ms = int((time.monotonic() - start) * 1000)

    score = (passed / total) if total else 0.0
    payload = {
        "benchmark": "function-calling",
        "score": score,
        "metrics": {"accuracy": score, "passed": passed, "total": total, "details": details},
        "duration_ms": duration_ms,
        "metadata": {"model": args.model_name},
    }
    out = Path(args.results)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"function-calling: accuracy={score:.3f} ({passed}/{total})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
