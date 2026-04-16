#!/usr/bin/env python3
"""RAG pipeline — retrieval-augmented generation accuracy.

The reference implementation ships a tiny inline corpus and uses a
trivial bag-of-words overlap "retriever" so the container stays
zero-dependency. For each question we:

  1. Retrieve top_k passages by overlap with the question tokens.
  2. Stuff the passages into the prompt as context.
  3. Ask the engine.
  4. Check the expected answer is contained in the response.

Real RAG evaluation would swap the retriever for an actual embedding
store (FAISS, pgvector, LanceDB) via the config.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

INLINE_CORPUS: list[str] = [
    "The Great Barrier Reef is located off the coast of Queensland, Australia, and is the world's largest coral reef system.",
    "Mount Kilimanjaro, the highest peak in Africa, is located in Tanzania and rises approximately 5,895 meters above sea level.",
    "The Amazon River in South America is the second-longest river in the world and has the largest drainage basin of any river.",
    "The Sahara, spanning North Africa, is the largest hot desert on Earth, covering about 9.2 million square kilometers.",
    "The Mariana Trench in the western Pacific Ocean is the deepest known part of the world's oceans, reaching about 10,935 meters.",
    "Angel Falls in Venezuela is the world's highest uninterrupted waterfall, with a drop of 979 meters.",
]

INLINE_QUESTIONS: list[dict[str, Any]] = [
    {"question": "Where is the Great Barrier Reef located?", "answer": "Australia"},
    {"question": "What country is Mount Kilimanjaro in?", "answer": "Tanzania"},
    {"question": "What is the deepest part of the ocean?", "answer": "Mariana"},
    {"question": "What is the highest waterfall in the world?", "answer": "Angel"},
]


def tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z]+", text.lower()) if len(t) > 2}


def retrieve(corpus: list[str], question: str, top_k: int) -> list[str]:
    q_tokens = tokenize(question)
    scored = [(len(q_tokens & tokenize(passage)), passage) for passage in corpus]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [p for score, p in scored[:top_k] if score > 0] or [corpus[0]]


def ask(url: str, model: str, prompt: str, max_tokens: int) -> str:
    body = {"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0.0}
    with httpx.Client(timeout=120.0) as client:
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

    corpus = cfg.get("corpus") or INLINE_CORPUS
    questions = cfg.get("questions") or INLINE_QUESTIONS
    top_k = int(cfg.get("top_k", 3))
    max_tokens = int(cfg.get("max_tokens", 64))
    url = args.engine_url.rstrip("/") + "/v1/completions"

    start = time.monotonic()
    passed = 0
    total = 0
    details: list[dict[str, Any]] = []
    for q in questions:
        total += 1
        passages = retrieve(corpus, q["question"], top_k)
        context = "\n- " + "\n- ".join(passages)
        prompt = (
            "Use the context below to answer the question. If the context does not contain "
            "the answer, say so.\n\nContext:" + context + f"\n\nQuestion: {q['question']}\nAnswer:"
        )
        try:
            response = ask(url, args.model_name, prompt, max_tokens)
        except httpx.HTTPError as exc:
            details.append({"question": q["question"], "passed": False, "error": str(exc)})
            continue
        ok = str(q["answer"]).lower() in response.lower()
        if ok:
            passed += 1
        details.append({
            "question": q["question"],
            "passed": ok,
            "response": response[:120],
            "retrieved": len(passages),
        })
    duration_ms = int((time.monotonic() - start) * 1000)

    accuracy = (passed / total) if total else 0.0
    payload = {
        "benchmark": "rag-pipeline",
        "score": accuracy,
        "metrics": {
            "accuracy": accuracy,
            "passed": passed,
            "total": total,
            "top_k": top_k,
            "details": details,
        },
        "duration_ms": duration_ms,
        "metadata": {"model": args.model_name, "corpus_size": len(corpus)},
    }
    out = Path(args.results)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"rag-pipeline: accuracy={accuracy:.3f} ({passed}/{total})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
