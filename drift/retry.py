"""Bounded retry helper for side-effecting integrations."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    initial_delay: float = 0.2,
    retryable: Callable[[Exception], bool] | None = None,
) -> tuple[T, int]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await operation(), attempt
        except Exception as exc:  # integration boundaries normalize below
            last_error = exc
            if retryable is not None and not retryable(exc):
                raise
            if attempt == attempts:
                break
            await asyncio.sleep(initial_delay * (2 ** (attempt - 1)))
    assert last_error is not None
    raise last_error
