"""Shared HTTP client for OpenAI-compatible /v1/completions endpoints.

Used by vLLM and llama.cpp engines which expose OpenAI-compatible APIs.
Uses urllib.request (no external dependencies).
"""

import json
import logging
import time
import urllib.request
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .base import GenerationMetrics, GenerationResult

logger = logging.getLogger(__name__)


def openai_generate(
    base_url: str,
    prompt: str,
    model: str = "default",
    temperature: float = 0.0,
    top_p: float = 1.0,
    top_k: int = 50,
    max_tokens: int = 2048,
) -> dict[str, Any]:
    """Send a completion request to an OpenAI-compatible endpoint.

    Args:
        base_url: Base URL of the server (e.g. "http://localhost:8000").
        prompt: Input prompt text.
        model: Model name to pass in the request.
        temperature: Sampling temperature.
        top_p: Nucleus sampling parameter.
        top_k: Top-k sampling parameter (ignored by standard OpenAI API).
        max_tokens: Maximum tokens to generate.

    Returns:
        Parsed JSON response dict.

    Raises:
        RuntimeError: If the request fails.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
    }

    data = json.dumps(payload).encode("utf-8")
    url = f"{base_url.rstrip('/')}/v1/completions"
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API request failed ({e.code}): {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot connect to engine at {base_url}: {e}") from e


def parse_openai_result(
    response: dict[str, Any],
    total_latency_ms: float,
    gpu_tracker: Any,
) -> GenerationResult:
    """Parse an OpenAI completions response into a GenerationResult.

    Args:
        response: Parsed JSON response from the OpenAI API.
        total_latency_ms: Total request latency in milliseconds.
        gpu_tracker: GPUMemoryTracker instance with memory samples.

    Returns:
        GenerationResult with extracted metrics.
    """
    choices = response.get("choices", [])
    output = choices[0]["text"] if choices else ""

    usage = response.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    tps = (
        completion_tokens / (total_latency_ms / 1000)
        if total_latency_ms > 0 and completion_tokens > 0
        else 0
    )

    metrics = GenerationMetrics(
        ttft_ms=0,
        tps=tps,
        total_latency_ms=total_latency_ms,
        gpu_memory_peak_gb=gpu_tracker.get_peak_memory_mb() / 1024,
        gpu_memory_avg_gb=gpu_tracker.get_average_memory_mb() / 1024,
        timestamp=datetime.now(),
    )

    return GenerationResult(
        output=output,
        metrics=metrics,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


@dataclass
class StreamChunk:
    """A single token chunk from a streaming response."""

    token: str
    timestamp_ms: float  # Time since request start in milliseconds


def openai_generate_stream(
    base_url: str,
    prompt: str,
    model: str = "default",
    temperature: float = 0.0,
    top_p: float = 1.0,
    max_tokens: int = 2048,
) -> Generator[StreamChunk, None, None]:
    """Send a streaming completion request and yield token chunks.

    Uses SSE (Server-Sent Events) to receive tokens as they're generated.

    Args:
        base_url: Base URL of the server.
        prompt: Input prompt text.
        model: Model name.
        temperature: Sampling temperature.
        top_p: Nucleus sampling parameter.
        max_tokens: Maximum tokens to generate.

    Yields:
        StreamChunk with token text and timestamp.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "stream": True,
    }

    data = json.dumps(payload).encode("utf-8")
    url = f"{base_url.rstrip('/')}/v1/completions"
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )

    start_time = time.perf_counter()

    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data: "):
                    line = line[6:]
                if line == "[DONE]":
                    break
                try:
                    chunk_data = json.loads(line)
                    choices = chunk_data.get("choices", [])
                    if choices:
                        token = choices[0].get("text", "")
                        if token:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000
                            yield StreamChunk(
                                token=token,
                                timestamp_ms=elapsed_ms,
                            )
                except json.JSONDecodeError:
                    continue
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Streaming request failed ({e.code}): {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot connect for streaming at {base_url}: {e}") from e
