"""In-process fan-out bus for live dashboard events. Modified for Drift in 2026."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from .models import WorkflowEvent


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[WorkflowEvent]] = set()

    async def publish(self, event: WorkflowEvent) -> None:
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                queue.put_nowait(event)

    async def subscribe(self) -> AsyncIterator[WorkflowEvent]:
        queue: asyncio.Queue[WorkflowEvent] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)


bus = EventBus()
