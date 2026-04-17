#!/usr/bin/env python3
"""Warmup analysis — early-run cache effects.

Issues N identical requests back-to-back and records the per-request
latency series. Typical engines show the first request taking
noticeably longer (CUDA kernel compilation, KV cache allocation,
weight paging) before settling at steady state. We report:

  - first request latency
  - steady-state mean (skipping the first K requests, default K=3)
  - warmup_ratio = first / steady_state_mean
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx


def one_request(url: str, model: str, prompt: str, max_tokens: int) -> float:
    body = {"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0.0}
    start = time.monotonic()
    with httpx.Client(timeout=120.0) as client:
        r = client.post(url, json=body)
        r.raise_for_status()
    return (time.monotonic() - start) * 1000.0


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

    runs = int(cfg.get("runs", 12))
    skip = int(cfg.get("skip_warmup", 3))
    max_tokens = int(cfg.get("max_tokens", 32))
    prompt = cfg.get("prompt", "Summarize the causes of the French Revolution.\n")
    url = args.engine_url.rstrip("/") + "/v1/completions"

    start = time.monotonic()
    series: list[float] = []
    errors = 0
    for _ in range(runs):
        try:
            series.append(one_request(url, args.model_name, prompt, max_tokens))
        except httpx.HTTPError as exc:
            errors += 1
            print(f"run failed: {exc}", file=sys.stderr)
    duration_ms = int((time.monotonic() - start) * 1000)

    first = series[0] if series else 0.0
    steady = series[skip:] if len(series) > skip else series
    steady_mean = statistics.fmean(steady) if steady else 0.0
    warmup_ratio = (first / steady_mean) if steady_mean > 0 else 0.0

    metrics = {
        "first_request_ms": first,
        "steady_state_mean_ms": steady_mean,
        "warmup_ratio": warmup_ratio,
        "runs": runs,
        "skip": skip,
        "errors": errors,
        "per_request_ms": series,
    }
    payload = {
        "benchmark": "warmup-analysis",
        # Lower warmup_ratio == flatter curve == better. Score maps to
        # 1 / (ratio - 1 + 1) so a ratio of 1 (no warmup) → 1.0 and
        # higher ratios → <1.0.
        "score": 1.0 / max(1.0, warmup_ratio),
        "metrics": metrics,
        "duration_ms": duration_ms,
        "metadata": {"model": args.model_name},
    }
    out = Path(args.results)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"warmup-analysis: first={first:.1f}ms steady={steady_mean:.1f}ms ratio={warmup_ratio:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
