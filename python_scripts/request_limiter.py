from __future__ import annotations

import asyncio
import threading

from aiolimiter import AsyncLimiter


class RequestLimiterGate:
    def __init__(self, max_rate: int, time_period: int = 60) -> None:
        self.max_rate = max(1, int(max_rate))
        self.time_period = max(1, int(time_period))
        self._loop = asyncio.new_event_loop()
        self._started = threading.Event()
        self._limiter_ready = threading.Event()
        self._limiter: AsyncLimiter | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._started.wait()
        future = asyncio.run_coroutine_threadsafe(self._create_limiter(), self._loop)
        self._limiter = future.result()
        self._limiter_ready.set()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._started.set()
        self._loop.run_forever()

    async def _create_limiter(self) -> AsyncLimiter:
        return AsyncLimiter(max_rate=self.max_rate, time_period=self.time_period)

    def acquire(self) -> None:
        self._limiter_ready.wait()
        if self._limiter is None:
            return
        future = asyncio.run_coroutine_threadsafe(self._limiter.acquire(), self._loop)
        future.result()
