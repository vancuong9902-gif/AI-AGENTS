import asyncio
from collections.abc import Awaitable, Callable

from app.shared.errors import CircuitBreakerOpen


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3) -> None:
        self._failure_threshold = failure_threshold
        self._failures = 0
        self._open = False

    async def call(self, fn: Callable[[], Awaitable[dict]]) -> dict:
        if self._open:
            raise CircuitBreakerOpen("Circuit breaker is open")
        try:
            result = await fn()
            self._failures = 0
            return result
        except Exception:
            self._failures += 1
            if self._failures >= self._failure_threshold:
                self._open = True
            raise


async def retry_with_backoff(
    fn: Callable[[], Awaitable[dict]], retries: int = 3, base_delay: float = 0.2
) -> dict:
    for attempt in range(1, retries + 1):
        try:
            return await fn()
        except Exception:
            if attempt == retries:
                raise
            await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
    raise RuntimeError("Unreachable")
