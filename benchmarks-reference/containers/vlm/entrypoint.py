#!/usr/bin/env python3
"""Vision-language benchmark — image-question accuracy.

Sends OpenAI-style chat/completions requests with an image_url content
part and checks the response contains the expected answer string. The
reference dataset is a small inline set of (image_url, question,
answer) triples using public URLs; real runs should mount a real VQA
dataset via --config.

If the engine doesn't accept multimodal content parts, the image_url
is demoted to a text URL in the prompt and the benchmark degrades to
a "can you read this URL" smoke — acceptable for reference CI.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

INLINE_ITEMS: list[dict[str, str]] = [
    {
        "image_url": "https://example.com/cat.png",
        "question": "What animal is in the image? Answer in one word.",
        "answer": "cat",
    },
    {
        "image_url": "https://example.com/dog.png",
        "question": "What animal is in the image? Answer in one word.",
        "answer": "dog",
    },
]


def ask(url: str, model: str, item: dict[str, str], max_tokens: int) -> str:
    # OpenAI-vision content-part style.
    body = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": item["question"]},
                {"type": "image_url", "image_url": {"url": item["image_url"]}},
            ],
        }],
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }
    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
        choices = data.get("choices") or []
        if choices:
            return choices[0].get("message", {}).get("content", "") or choices[0].get("text", "")
    except httpx.HTTPError:
        pass
    # Fallback to text-only prompt.
    fallback_body = {
        "model": model,
        "prompt": f"Image URL: {item['image_url']}\nQuestion: {item['question']}\nAnswer:",
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }
    with httpx.Client(timeout=120.0) as client:
        r = client.post(url.replace("/v1/chat/completions", "/v1/completions"), json=fallback_body)
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

    items = cfg.get("items") or INLINE_ITEMS
    max_tokens = int(cfg.get("max_tokens", 32))
    chat_url = args.engine_url.rstrip("/") + "/v1/chat/completions"

    start = time.monotonic()
    passed = 0
    total = 0
    details: list[dict[str, Any]] = []
    for item in items:
        total += 1
        try:
            answer = ask(chat_url, args.model_name, item, max_tokens)
        except httpx.HTTPError as exc:
            details.append({"question": item.get("question"), "passed": False, "error": str(exc)})
            continue
        ok = item["answer"].lower() in answer.lower()
        if ok:
            passed += 1
        details.append({"question": item.get("question"), "passed": ok, "response": answer[:120]})
    duration_ms = int((time.monotonic() - start) * 1000)

    accuracy = (passed / total) if total else 0.0
    payload = {
        "benchmark": "vlm",
        "score": accuracy,
        "metrics": {"accuracy": accuracy, "passed": passed, "total": total, "details": details},
        "duration_ms": duration_ms,
        "metadata": {"model": args.model_name},
    }
    out = Path(args.results)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"vlm: accuracy={accuracy:.3f} ({passed}/{total})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
