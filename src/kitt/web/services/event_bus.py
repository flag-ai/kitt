"""In-process pub/sub event bus for SSE streaming.

Clients subscribe to channels and receive events as they are published.
Used for real-time log streaming, status updates, and notifications.
"""

import contextlib
import json
import logging
import queue
import threading
import time
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """A single event on the bus."""

    event_type: str
    source_id: str
    data: dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        """Format as a Server-Sent Event string."""
        payload = json.dumps(self.data, default=str)
        lines = [
            f"event: {self.event_type}",
            f"data: {payload}",
            "",
            "",
        ]
        return "\n".join(lines)


class EventBus:
    """Thread-safe in-process pub/sub for SSE events."""

    def __init__(self, max_history: int = 200) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, queue.Queue] = {}
        self._history: list[Event] = []
        self._max_history = max_history
        self._counter = 0

    def publish(self, event_type: str, source_id: str, data: dict[str, Any]) -> None:
        """Publish an event to all subscribers.

        Args:
            event_type: Event type (e.g., "log", "status", "heartbeat").
            source_id: Source identifier (e.g., agent_id, campaign_id).
            data: Event payload.
        """
        event = Event(event_type=event_type, source_id=source_id, data=data)

        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]
            self._counter += 1

            for sub_queue in self._subscribers.values():
                with contextlib.suppress(queue.Full):
                    sub_queue.put_nowait(event)

    def subscribe(
        self,
        subscriber_id: str,
        source_filter: str | None = None,
        max_queue_size: int = 100,
    ) -> Generator[str, None, None]:
        """Subscribe to events and yield SSE-formatted strings.

        Args:
            subscriber_id: Unique subscriber identifier.
            source_filter: If set, only yield events from this source_id.
            max_queue_size: Max events to buffer per subscriber.

        Yields:
            SSE-formatted event strings.
        """
        sub_queue: queue.Queue = queue.Queue(maxsize=max_queue_size)

        with self._lock:
            self._subscribers[subscriber_id] = sub_queue

        try:
            while True:
                try:
                    event = sub_queue.get(timeout=30)
                    if source_filter and event.source_id != source_filter:
                        continue
                    yield event.to_sse()
                except queue.Empty:
                    # Send keepalive comment to prevent connection timeout
                    yield ": keepalive\n\n"
        finally:
            with self._lock:
                self._subscribers.pop(subscriber_id, None)

    def unsubscribe(self, subscriber_id: str) -> None:
        """Remove a subscriber."""
        with self._lock:
            self._subscribers.pop(subscriber_id, None)

    def get_history(
        self,
        source_id: str | None = None,
        limit: int = 50,
    ) -> list[Event]:
        """Get recent events, optionally filtered by source."""
        with self._lock:
            events = self._history
            if source_id:
                events = [e for e in events if e.source_id == source_id]
            return events[-limit:]

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


# Global event bus instance
event_bus = EventBus()
