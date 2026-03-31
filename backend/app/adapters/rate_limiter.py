import asyncio
from datetime import datetime, timedelta
from collections import deque


class AsyncRateLimiter:
    def __init__(self, calls_per_minute: int = 60):
        self.calls_per_minute = calls_per_minute
        self.min_interval = 60.0 / calls_per_minute
        self._timestamps: deque = deque(maxlen=calls_per_minute)
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = datetime.now()

            while self._timestamps:
                oldest = self._timestamps[0]
                if now - oldest >= timedelta(seconds=self.min_interval):
                    self._timestamps.popleft()
                else:
                    wait_time = self.min_interval - (now - oldest).total_seconds()
                    if wait_time > 0:
                        await asyncio.sleep(wait_time)
                    break

            self._timestamps.append(datetime.now())

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *args):
        pass
