#!/usr/bin/env python3
"""Streaming latency — SSE token arrival timing.

Similar to latency/, but focused on the *streaming* experience rather
than overall request latency: measures token arrival jitter (stdev of
inter-arrival times), tokens-per-second sustained across the stream,
and any stalls longer than a configurable threshold.
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


def run_one(url: str, model: str, prompt: str, max_tokens: int, stall_threshold_ms: float) -> dict[str, Any]:
    body = {"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0.0, "stream": True}
    arrivals: list[float] = []
    start = time.monotonic()
    stalls = 0
    last: float | None = None
    with httpx.Client(timeout=120.0) as client:
        with client.stream("POST", url, json=body) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload_text = line[len(b"data:") if isinstance(line, bytes) else len("data:"):].strip()
                if not payload_text or payload_text == "[DONE]":
                    continue
                now = time.monotonic()
                arrivals.append((now - start) * 1000.0)
                if last is not None and (now - last) * 1000.0 > stall_threshold_ms:
                    stalls += 1
                last = now

    inter = [arrivals[i] - arrivals[i - 1] for i in range(1, len(arrivals))]
    return {
        "tokens": len(arrivals),
        "duration_ms": arrivals[-1] if arrivals else 0.0,
        "inter_arrival_ms": inter,
        "stalls": stalls,
    }


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

    runs = int(cfg.get("runs", 5))
    max_tokens = int(cfg.get("max_tokens", 128))
    stall_threshold_ms = float(cfg.get("stall_threshold_ms", 500.0))
    prompt = cfg.get("prompt", "Tell me a story in exactly 100 words.\n")
    url = args.engine_url.rstrip("/") + "/v1/completions"

    start = time.monotonic()
    all_inter: list[float] = []
    total_tokens = 0
    total_stalls = 0
    errors = 0
    run_tps: list[float] = []
    for _ in range(runs):
        try:
            r = run_one(url, args.model_name, prompt, max_tokens, stall_threshold_ms)
        except httpx.HTTPError as exc:
            errors += 1
            print(f"streaming run failed: {exc}", file=sys.stderr)
            continue
        all_inter.extend(r["inter_arrival_ms"])
        total_tokens += r["tokens"]
        total_stalls += r["stalls"]
        if r["duration_ms"] > 0:
            run_tps.append(r["tokens"] / (r["duration_ms"] / 1000.0))
    duration_ms = int((time.monotonic() - start) * 1000)

    metrics = {
        "runs": runs,
        "errors": errors,
        "total_tokens": total_tokens,
        "stalls": total_stalls,
        "inter_arrival_mean_ms": statistics.fmean(all_inter) if all_inter else 0.0,
        "inter_arrival_stdev_ms": statistics.pstdev(all_inter) if len(all_inter) > 1 else 0.0,
        "tokens_per_second_mean": statistics.fmean(run_tps) if run_tps else 0.0,
    }
    payload = {
        "benchmark": "streaming-latency",
        "score": metrics["tokens_per_second_mean"],
        "metrics": metrics,
        "duration_ms": duration_ms,
        "metadata": {"model": args.model_name, "stall_threshold_ms": stall_threshold_ms},
    }
    out = Path(args.results)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"streaming-latency: mean={metrics['tokens_per_second_mean']:.2f} tok/s  stalls={total_stalls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
