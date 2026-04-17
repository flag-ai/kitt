#!/usr/bin/env python3
"""Tensor-parallel scaling — throughput vs. number of GPUs.

This benchmark is meant to be run multiple times at different
tensor_parallel_size settings; within a single invocation we measure
throughput at the currently configured TP size. The metrics JSON
includes the "gpus" field from config so the campaign runner can stitch
together the scaling curve.

Scoring is raw tokens/sec — the campaign-level analysis derives
efficiency (TPS_n / (n * TPS_1)).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx


async def one_request(client: httpx.AsyncClient, url: str, model: str, prompt: str, max_tokens: int) -> int:
    body = {"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0.0}
    r = await client.post(url, json=body, timeout=120.0)
    r.raise_for_status()
    data = r.json()
    usage = data.get("usage") or {}
    if "completion_tokens" in usage:
        return int(usage["completion_tokens"])
    text = (data.get("choices", [{}])[0]).get("text", "")
    return max(1, len(text.split()))


async def run(engine_url: str, model: str, cfg: dict[str, Any]) -> dict[str, Any]:
    concurrency = int(cfg.get("concurrency", 16))
    total_requests = int(cfg.get("requests", 64))
    max_tokens = int(cfg.get("max_tokens", 64))
    prompt = cfg.get("prompt", "Write a one-paragraph summary of photosynthesis.\n")
    url = engine_url.rstrip("/") + "/v1/completions"

    sem = asyncio.Semaphore(concurrency)

    async def guarded(client: httpx.AsyncClient) -> int:
        async with sem:
            return await one_request(client, url, model, prompt, max_tokens)

    start = time.monotonic()
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[guarded(client) for _ in range(total_requests)], return_exceptions=True)
    elapsed = time.monotonic() - start

    tokens = sum(r for r in results if isinstance(r, int))
    errors = sum(1 for r in results if isinstance(r, Exception))
    return {
        "tokens_per_second": tokens / elapsed if elapsed > 0 else 0.0,
        "total_tokens": tokens,
        "errors": errors,
        "concurrency": concurrency,
        "duration_s": elapsed,
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

    gpus = int(cfg.get("gpus", 1))
    start = time.monotonic()
    metrics = asyncio.run(run(args.engine_url, args.model_name, cfg))
    duration_ms = int((time.monotonic() - start) * 1000)

    metrics["gpus"] = gpus
    payload = {
        "benchmark": "tensor-parallel",
        "score": metrics["tokens_per_second"],
        "metrics": metrics,
        "duration_ms": duration_ms,
        "metadata": {"model": args.model_name, "tensor_parallel_size": gpus},
    }
    out = Path(args.results)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"tensor-parallel: {metrics['tokens_per_second']:.2f} tok/s at TP={gpus}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
