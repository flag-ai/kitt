#!/usr/bin/env python3
"""Multi-turn consistency — does the model keep track of context?

For each scenario we run a scripted N-turn conversation where the
final turn asks something that depends on facts introduced earlier.
Score is the fraction of conversations where the final answer
contains the expected token(s).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

INLINE_SCENARIOS: list[dict[str, Any]] = [
    {
        "turns": [
            {"role": "user", "content": "My name is Alice and I am 30 years old."},
            {"role": "user", "content": "I live in Berlin."},
            {"role": "user", "content": "What is my name? Answer with just the name."},
        ],
        "expected": "Alice",
    },
    {
        "turns": [
            {"role": "user", "content": "Please remember that my favorite color is teal."},
            {"role": "user", "content": "I also like the number 42."},
            {"role": "user", "content": "What is my favorite color? Answer with one word."},
        ],
        "expected": "teal",
    },
]


def chat(url: str, model: str, history: list[dict[str, str]], max_tokens: int) -> tuple[str, list[dict[str, str]]]:
    body = {"model": model, "messages": history, "max_tokens": max_tokens, "temperature": 0.0}
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, json=body)
        r.raise_for_status()
        data = r.json()
    choices = data.get("choices") or []
    if not choices:
        return "", history
    msg = choices[0].get("message") or {}
    content = msg.get("content") or choices[0].get("text", "") or ""
    return content, history + [{"role": "assistant", "content": content}]


def run_scenario(url: str, model: str, scenario: dict[str, Any], max_tokens: int) -> tuple[bool, str]:
    """Walk through scenario['turns'] interleaving assistant replies.

    The expected answer is checked only against the FINAL assistant
    response — earlier responses are just context builders.
    """
    history: list[dict[str, str]] = []
    last_reply = ""
    for turn in scenario["turns"]:
        history.append(turn)
        last_reply, history = chat(url, model, history, max_tokens)
    expected = str(scenario["expected"]).lower()
    return expected in last_reply.lower(), last_reply


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

    scenarios = cfg.get("scenarios") or INLINE_SCENARIOS
    max_tokens = int(cfg.get("max_tokens", 32))
    url = args.engine_url.rstrip("/") + "/v1/chat/completions"

    start = time.monotonic()
    passed = 0
    total = 0
    details: list[dict[str, Any]] = []
    for idx, scenario in enumerate(scenarios):
        total += 1
        try:
            ok, last = run_scenario(url, args.model_name, scenario, max_tokens)
        except httpx.HTTPError as exc:
            details.append({"scenario": idx, "passed": False, "error": str(exc)})
            continue
        if ok:
            passed += 1
        details.append({
            "scenario": idx,
            "passed": ok,
            "final_reply": last[:120],
            "expected": scenario.get("expected"),
        })
    duration_ms = int((time.monotonic() - start) * 1000)

    score = (passed / total) if total else 0.0
    payload = {
        "benchmark": "multiturn",
        "score": score,
        "metrics": {"consistency": score, "passed": passed, "total": total, "details": details},
        "duration_ms": duration_ms,
        "metadata": {"model": args.model_name},
    }
    out = Path(args.results)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"multiturn: consistency={score:.3f} ({passed}/{total})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
