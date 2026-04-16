#!/usr/bin/env python3
"""Long-context benchmark — quality degradation at 16k/32k/128k.

"Needle in a haystack" style: injects a known fact at a configurable
depth inside a long filler context and checks whether the model can
recover it. Measures retrieval accuracy at each tested context length
so the result captures per-length degradation, not just a single
average.

The reference data is synthetic filler — repeated sentences of the
quick brown fox style — which is good enough to exercise the
container protocol without shipping a large dataset.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

FILLER_SENTENCE = "The quick brown fox jumps over the lazy dog. "
NEEDLE_TEMPLATE = "Remember: the secret code is {code}. "
PROMPT_SUFFIX = "\n\nBased on the passage above, what is the secret code? Answer with just the code."


def build_prompt(target_chars: int, code: str, depth_ratio: float) -> str:
    needle = NEEDLE_TEMPLATE.format(code=code)
    filler_needed = max(0, target_chars - len(needle))
    front_chars = int(filler_needed * depth_ratio)
    back_chars = filler_needed - front_chars
    front = (FILLER_SENTENCE * ((front_chars // len(FILLER_SENTENCE)) + 1))[:front_chars]
    back = (FILLER_SENTENCE * ((back_chars // len(FILLER_SENTENCE)) + 1))[:back_chars]
    return front + needle + back + PROMPT_SUFFIX


def ask(url: str, model: str, prompt: str, max_tokens: int) -> str:
    body = {"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0.0}
    with httpx.Client(timeout=180.0) as client:
        r = client.post(url, json=body)
        r.raise_for_status()
        data = r.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    return choices[0].get("text") or choices[0].get("message", {}).get("content", "") or ""


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

    # Approx 4 chars per token, so 16k tokens ≈ 64k chars. Keep it
    # approximate — the real harness would tokenize.
    context_lengths_tokens = cfg.get("context_lengths", [16000, 32000, 128000])
    depths = cfg.get("depths", [0.1, 0.5, 0.9])
    trials_per_cell = int(cfg.get("trials_per_cell", 1))
    max_tokens = int(cfg.get("max_tokens", 32))
    url = args.engine_url.rstrip("/") + "/v1/completions"

    start = time.monotonic()
    per_length: dict[str, dict[str, Any]] = {}
    for ctx_tokens in context_lengths_tokens:
        target_chars = int(ctx_tokens) * 4
        passed = 0
        total = 0
        for depth in depths:
            for trial in range(trials_per_cell):
                code = f"KC-{ctx_tokens}-{int(depth*100)}-{trial}"
                prompt = build_prompt(target_chars, code, float(depth))
                try:
                    resp = ask(url, args.model_name, prompt, max_tokens)
                except httpx.HTTPError as exc:
                    print(f"long-context request failed at {ctx_tokens}/{depth}: {exc}", file=sys.stderr)
                    resp = ""
                ok = code in resp
                total += 1
                if ok:
                    passed += 1
        per_length[str(ctx_tokens)] = {
            "accuracy": (passed / total) if total else 0.0,
            "passed": passed,
            "total": total,
        }
    duration_ms = int((time.monotonic() - start) * 1000)

    # Overall score = mean accuracy across context lengths.
    scores = [entry["accuracy"] for entry in per_length.values()]
    overall = sum(scores) / len(scores) if scores else 0.0

    payload = {
        "benchmark": "long-context",
        "score": overall,
        "metrics": {
            "overall_accuracy": overall,
            "per_length": per_length,
            "lengths_tested": context_lengths_tokens,
            "depths_tested": depths,
            "trials_per_cell": trials_per_cell,
        },
        "duration_ms": duration_ms,
        "metadata": {"model": args.model_name},
    }
    out = Path(args.results)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"long-context: overall={overall:.3f} across {context_lengths_tokens}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
