"""Capture subprocess logs and emit as SSE events."""

import contextlib
import json
import logging
import queue
import threading
from collections.abc import Generator

logger = logging.getLogger(__name__)


class LogStreamer:
    """Captures log lines and provides SSE-formatted output."""

    def __init__(self, command_id: str, max_buffer: int = 1000) -> None:
        self.command_id = command_id
        self._buffer: list[str] = []
        self._subscribers: dict[str, queue.Queue] = {}
        self._lock = threading.Lock()
        self._max_buffer = max_buffer

    def emit(self, line: str) -> None:
        """Add a log line and notify subscribers."""
        with self._lock:
            self._buffer.append(line)
            if len(self._buffer) > self._max_buffer:
                self._buffer = self._buffer[-self._max_buffer :]

            event = json.dumps({"command_id": self.command_id, "line": line})
            sse_data = f"event: log\ndata: {event}\n\n"

            for sub_queue in self._subscribers.values():
                with contextlib.suppress(queue.Full):
                    sub_queue.put_nowait(sse_data)

    def subscribe(self, subscriber_id: str) -> Generator[str, None, None]:
        """Subscribe to the log stream as SSE."""
        sub_queue: queue.Queue = queue.Queue(maxsize=200)

        with self._lock:
            self._subscribers[subscriber_id] = sub_queue
            for line in self._buffer:
                event = json.dumps({"command_id": self.command_id, "line": line})
                try:
                    sub_queue.put_nowait(f"event: log\ndata: {event}\n\n")
                except queue.Full:
                    break

        try:
            while True:
                try:
                    data = sub_queue.get(timeout=30)
                    yield data
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with self._lock:
                self._subscribers.pop(subscriber_id, None)

    def get_buffer(self) -> list[str]:
        """Get all buffered log lines."""
        with self._lock:
            return list(self._buffer)
