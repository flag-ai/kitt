#!/usr/bin/env python3
"""HumanEval — code-generation evaluation via sandboxed execution.

For each problem:
  1. Prompt the engine with the canonical HumanEval prompt.
  2. Extract the completion.
  3. Execute ``prompt + completion + test`` in a subprocess with a
     short timeout and an rlimit on CPU time and address space.
  4. Score pass/fail.

The reference dataset is a small inline set of three problems so the
container builds/runs without downloading anything at image-build or
run time. Real evaluation should mount openai/humaneval or
openai_humaneval via the config.
"""

from __future__ import annotations

import argparse
import json
import os
import resource  # noqa: I001  (stdlib ordering is fine; resource is POSIX-only)
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

INLINE_PROBLEMS: list[dict[str, str]] = [
    {
        "task_id": "inline/1",
        "prompt": "def add(a, b):\n    \"\"\"Return the sum of a and b.\"\"\"\n",
        "test": (
            "def check(candidate):\n"
            "    assert candidate(1, 2) == 3\n"
            "    assert candidate(-1, 1) == 0\n"
            "    assert candidate(0, 0) == 0\n"
        ),
        "entry_point": "add",
    },
    {
        "task_id": "inline/2",
        "prompt": "def is_even(n):\n    \"\"\"Return True if n is even, else False.\"\"\"\n",
        "test": (
            "def check(candidate):\n"
            "    assert candidate(2) is True\n"
            "    assert candidate(3) is False\n"
            "    assert candidate(0) is True\n"
        ),
        "entry_point": "is_even",
    },
    {
        "task_id": "inline/3",
        "prompt": "def factorial(n):\n    \"\"\"Return n! for n >= 0.\"\"\"\n",
        "test": (
            "def check(candidate):\n"
            "    assert candidate(0) == 1\n"
            "    assert candidate(1) == 1\n"
            "    assert candidate(5) == 120\n"
        ),
        "entry_point": "factorial",
    },
]


def ask_engine(url: str, model: str, prompt: str, max_tokens: int) -> str:
    body = {"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0.0, "stop": ["\ndef ", "\nclass "]}
    with httpx.Client(timeout=120.0) as client:
        r = client.post(url, json=body)
        r.raise_for_status()
        data = r.json()
    if not data.get("choices"):
        return ""
    return data["choices"][0].get("text") or data["choices"][0].get("message", {}).get("content", "") or ""


def _limit_resources() -> None:
    # 4s CPU, 256 MB address space. Called in the child via preexec_fn.
    resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))


def run_candidate(prompt: str, completion: str, test: str, entry_point: str, timeout_s: float) -> tuple[bool, str]:
    """Concatenate prompt+completion+test, execute, return (passed, detail)."""
    program = f"{prompt}{completion}\n\n{test}\ncheck({entry_point})\n"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(program)
        script_path = f.name
    try:
        proc = subprocess.run(  # noqa: S603 — controlled input + rlimits + timeout
            [sys.executable, script_path],
            timeout=timeout_s,
            capture_output=True,
            preexec_fn=_limit_resources,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except OSError as exc:
        return False, f"exec-error: {exc}"
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass
    if proc.returncode == 0:
        return True, "ok"
    stderr = proc.stderr.decode("utf-8", errors="replace")[-200:]
    return False, stderr or f"rc={proc.returncode}"


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

    problems = cfg.get("problems") or INLINE_PROBLEMS
    max_tokens = int(cfg.get("max_tokens", 256))
    timeout_s = float(cfg.get("timeout_s", 5.0))
    url = args.engine_url.rstrip("/") + "/v1/completions"

    start = time.monotonic()
    passed = 0
    total = 0
    per_task: list[dict[str, Any]] = []
    for problem in problems:
        total += 1
        try:
            completion = ask_engine(url, args.model_name, problem["prompt"], max_tokens)
        except httpx.HTTPError as exc:
            per_task.append({"task_id": problem["task_id"], "passed": False, "detail": f"engine-error: {exc}"})
            continue
        ok, detail = run_candidate(
            problem["prompt"], completion, problem["test"], problem["entry_point"], timeout_s
        )
        if ok:
            passed += 1
        per_task.append({"task_id": problem["task_id"], "passed": ok, "detail": detail})
    duration_ms = int((time.monotonic() - start) * 1000)

    pass_at_1 = (passed / total) if total else 0.0
    payload = {
        "benchmark": "humaneval",
        "score": pass_at_1,
        "metrics": {
            "pass@1": pass_at_1,
            "passed": passed,
            "total": total,
            "per_task": per_task,
        },
        "duration_ms": duration_ms,
        "metadata": {"model": args.model_name, "timeout_s": timeout_s},
    }
    out = Path(args.results)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"humaneval: pass@1={pass_at_1:.3f} ({passed}/{total})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
