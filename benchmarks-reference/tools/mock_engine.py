#!/usr/bin/env python3
"""Tiny OpenAI-compatible mock engine used by smoke tests.

Implements just enough of the API surface (health, completions, chat,
models, tokenize-ish) to let every reference benchmark container
complete its protocol and write /results/out.json. Deliberately
zero-dependency — stdlib only.

Run directly:
    python3 mock_engine.py [PORT]

Or import MockEngineServer to embed.
"""

from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any


class _Handler(BaseHTTPRequestHandler):
    """Servers deterministic-ish answers suited to letter-choice /
    extractable-number / "Paris"-style smoke tests."""

    # Keep logs off by default.
    def log_message(self, *_args: Any) -> None:  # noqa: D401, ANN401
        return

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/health", "/healthz", "/ready", "/v1/models"):
            self._send_json(200, {"status": "ok", "data": [{"id": "mock-model"}]})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802, C901
        body = self._read_json()
        text: str
        # Respond with something parseable for every benchmark.
        # - If prompt looks like an A/B/C/D multiple-choice item, emit "A".
        # - If it mentions "####" (GSM8K few-shot style), emit "#### 42".
        # - If it asks about Paris/Shakespeare/etc., echo the expected token.
        # - Otherwise, a short deterministic string.
        prompt_field = body.get("prompt") or ""
        if isinstance(prompt_field, list):
            prompt_field = " ".join(str(p) for p in prompt_field)
        messages = body.get("messages") or []
        if messages and not prompt_field:
            parts: list[str] = []
            for m in messages:
                if not isinstance(m, dict):
                    continue
                c = m.get("content", "")
                if isinstance(c, str):
                    parts.append(c)
                elif isinstance(c, list):
                    # Content parts (vision shape): pick text parts.
                    for p in c:
                        if isinstance(p, dict) and p.get("type") == "text":
                            parts.append(str(p.get("text", "")))
            prompt_field = "\n".join(parts)
        prompt_lower = prompt_field.lower()

        if "####" in prompt_field or "grade school" in prompt_lower:
            text = "#### 42"
        elif any(tag in prompt_field for tag in ("A. ", "B. ", "C. ", "D. ")):
            text = "A"
        elif "paris" in prompt_lower or "capital of france" in prompt_lower:
            text = "Paris"
        elif "shakespeare" in prompt_lower or "romeo" in prompt_lower:
            text = "Shakespeare"
        elif "gold" in prompt_lower and "symbol" in prompt_lower:
            text = "Au"
        elif "red planet" in prompt_lower:
            text = "Mars"
        elif "continents" in prompt_lower:
            text = "7"
        elif "ocean" in prompt_lower:
            text = "Pacific"
        elif "world war" in prompt_lower:
            text = "1945"
        elif "speed of light" in prompt_lower:
            text = "3.00e8"
        elif "def " in prompt_field or "solution" in prompt_lower:
            text = "def solution():\n    return 42\n"
        elif "tool" in prompt_lower or "function" in prompt_lower:
            text = json.dumps({"name": "lookup", "arguments": {"q": "x"}})
        else:
            text = "ok"

        if self.path.startswith("/v1/chat"):
            self._send_json(200, {
                "id": "mock-chat-1",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.get("model", "mock-model"),
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": max(1, len(text.split())), "total_tokens": 12},
            })
            return
        if self.path.startswith("/v1/completions") or self.path.startswith("/v1/generate"):
            self._send_json(200, {
                "id": "mock-cmpl-1",
                "object": "text_completion",
                "created": int(time.time()),
                "model": body.get("model", "mock-model"),
                "choices": [{
                    "index": 0,
                    "text": text,
                    "finish_reason": "stop",
                    "logprobs": None,
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": max(1, len(text.split())), "total_tokens": 12},
            })
            return
        self._send_json(404, {"error": "not found"})


class MockEngineServer:
    """Thin wrapper that runs the handler on a background thread."""

    def __init__(self, port: int = 0):
        self._server = HTTPServer(("127.0.0.1", port), _Handler)
        self.port = self._server.server_address[1]
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "MockEngineServer":
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self._server.shutdown()
        self._server.server_close()


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18080
    print(f"mock-engine listening on 127.0.0.1:{port}")
    srv = HTTPServer(("127.0.0.1", port), _Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
