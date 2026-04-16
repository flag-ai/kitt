#!/usr/bin/env python3
"""kitt-yaml-runner — executes a declarative YAML benchmark spec.

Reads a YAML spec from --spec, talks to an OpenAI-compatible engine
at --engine-url, and writes /results/out.json matching the container
protocol documented in benchmarks-reference/README.md.

The runner is deliberately minimal — just enough logic to parse the
five reference specs (MMLU, GSM8K, HellaSwag, TruthfulQA,
prompt-robustness). Future spec features (judge models, multi-turn,
custom metrics) layer on top of this shape.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import string
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

DEFAULT_RESULTS = Path("/results/out.json")


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_dataset_items(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Materialize the dataset referenced by spec['dataset'] into a list."""
    ds = spec.get("dataset") or {}
    source = ds.get("source", "inline")
    if source == "inline":
        return list(ds.get("items") or [])
    if source != "huggingface":
        raise ValueError(f"unsupported dataset source: {source}")

    # HF datasets — import lazily so inline-only specs don't pay the
    # import cost.
    from datasets import load_dataset  # type: ignore[import-not-found]

    kwargs: dict[str, Any] = {}
    if ds.get("subset"):
        kwargs["name"] = ds["subset"]
    ds_loaded = load_dataset(ds["id"], split=ds.get("split", "test"), **kwargs)
    items = list(ds_loaded)
    if ds.get("shuffle_seed") is not None:
        rng = random.Random(ds["shuffle_seed"])
        rng.shuffle(items)
    sample_size = ds.get("sample_size")
    if sample_size:
        items = items[: int(sample_size)]
    return items


def render_prompt(template: str, item: dict[str, Any], fewshot: str = "") -> str:
    """Substitute {field} placeholders from item + fewshot block."""
    mapping = {**item, "fewshot": fewshot}
    # Missing keys render as empty string — forgiving to keep the
    # reference specs small.
    class _SafeDict(dict):
        def __missing__(self, key: str) -> str:  # noqa: D401
            return ""

    return string.Formatter().vformat(template, (), _SafeDict(mapping))


def call_engine(engine_url: str, model: str, prompt: str, sampling: dict[str, Any]) -> str:
    """POST to /v1/completions and return the generated text."""
    body = {
        "model": model,
        "prompt": prompt,
        "temperature": sampling.get("temperature", 0.0),
        "top_p": sampling.get("top_p", 1.0),
        "max_tokens": sampling.get("max_tokens", 64),
    }
    if sampling.get("stop"):
        body["stop"] = sampling["stop"]
    url = engine_url.rstrip("/") + "/v1/completions"
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, json=body)
        resp.raise_for_status()
        data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    # Accept either OpenAI chat or completions shape.
    first = choices[0]
    return first.get("text") or first.get("message", {}).get("content", "") or ""


def parse_response(raw: str, parse_cfg: dict[str, Any]) -> str:
    method = parse_cfg.get("method", "exact-match")
    text = raw.strip()
    if method == "letter-choice":
        choices = parse_cfg.get("choices", ["A", "B", "C", "D"])
        if choices == "auto":
            choices = list("ABCDEFGHIJKL")
        for ch in text:
            if ch.upper() in choices:
                return ch.upper()
        return ""
    if method == "regex":
        pat = parse_cfg.get("pattern", "")
        m = re.search(pat, text)
        if not m:
            return ""
        val = m.group(1) if m.groups() else m.group(0)
        if parse_cfg.get("normalize") == "number":
            val = val.replace(",", "").strip()
        return val
    if method == "contains":
        return text
    # default: exact-match on trimmed text
    return text


def score_item(parsed: str, expected: Any, parse_cfg: dict[str, Any], score_cfg: dict[str, Any]) -> bool:
    method = score_cfg.get("method", "accuracy")
    exp = str(expected).strip()
    if method == "exact-match":
        return parsed.strip() == exp
    if method == "accuracy":
        return parsed.strip().upper() == exp.upper()
    if method == "pass-rate":
        # Used with parse.method == "contains".
        if parse_cfg.get("case_sensitive") is False:
            return exp.lower() in parsed.lower()
        return exp in parsed
    return parsed == exp


def expected_answer(item: dict[str, Any]) -> Any:
    """Heuristically find the ground truth in an item row."""
    for key in ("answer", "label", "gold", "correct"):
        if key in item:
            return item[key]
    return None


def write_result(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="kitt-yaml-runner")
    ap.add_argument("--engine-url", required=True)
    ap.add_argument("--model-name", required=True)
    ap.add_argument("--config", default="/config.json")
    ap.add_argument("--spec", default="/spec.yaml")
    ap.add_argument("--results", default=str(DEFAULT_RESULTS))
    args = ap.parse_args()

    spec_path = Path(args.spec)
    results_path = Path(args.results)
    if not spec_path.exists():
        print(f"spec not found: {spec_path}", file=sys.stderr)
        return 2

    spec = load_yaml(spec_path)
    cfg = load_config(Path(args.config))

    # Runtime overrides from cfg (sample_size, shuffle_seed) win over
    # the spec defaults so operators can shrink an eval at dispatch
    # time without editing the YAML.
    if cfg.get("sample_size"):
        spec.setdefault("dataset", {})["sample_size"] = cfg["sample_size"]

    templates = (spec.get("prompt") or {}).get("templates")
    single_template = (spec.get("prompt") or {}).get("template")
    sampling = spec.get("sampling") or {}
    parse_cfg = spec.get("parse") or {}
    score_cfg = spec.get("score") or {}

    items = load_dataset_items(spec)
    start = time.monotonic()

    evaluated = 0
    passed = 0
    skipped = 0
    for item in items:
        expected = expected_answer(item)
        if expected is None:
            skipped += 1
            continue
        prompt_variants = templates if templates else [single_template or "{question}"]
        for tpl in prompt_variants:
            prompt = render_prompt(tpl, item)
            try:
                raw = call_engine(args.engine_url, args.model_name, prompt, sampling)
            except httpx.HTTPError as exc:
                print(f"engine call failed: {exc}", file=sys.stderr)
                skipped += 1
                continue
            parsed = parse_response(raw, parse_cfg)
            ok = score_item(parsed, expected, parse_cfg, score_cfg)
            evaluated += 1
            if ok:
                passed += 1

    duration_ms = int((time.monotonic() - start) * 1000)
    score_value = (passed / evaluated) if evaluated else 0.0
    payload = {
        "benchmark": spec.get("name", spec_path.stem),
        "score": score_value,
        "metrics": {
            score_cfg.get("method", "accuracy"): score_value,
            "items_evaluated": evaluated,
            "items_passed": passed,
            "items_skipped": skipped,
        },
        "duration_ms": duration_ms,
        "metadata": {
            "dataset_id": (spec.get("dataset") or {}).get("id", ""),
            "split": (spec.get("dataset") or {}).get("split", ""),
            "model": args.model_name,
            "engine_url": os.path.basename(args.engine_url),
        },
    }
    write_result(results_path, payload)
    print(f"wrote {results_path}: score={score_value:.4f} evaluated={evaluated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
