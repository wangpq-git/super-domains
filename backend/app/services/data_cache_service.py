import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any


_DEFAULT_TTL_SECONDS = 30
_cache: dict[str, tuple[float, Any]] = {}
_locks: dict[str, asyncio.Lock] = {}


def build_cache_key(namespace: str, **kwargs: Any) -> str:
    payload = json.dumps(kwargs, ensure_ascii=False, sort_keys=True, default=str)
    return f"{namespace}:{payload}"


async def get_or_set(
    key: str,
    loader: Callable[[], Awaitable[Any]],
    *,
    ttl_seconds: int | None = None,
) -> Any:
    resolved_ttl = _DEFAULT_TTL_SECONDS if ttl_seconds is None else max(int(ttl_seconds), 0)
    if resolved_ttl <= 0:
        return await loader()

    now = time.monotonic()
    cached = _cache.get(key)
    if cached and cached[0] > now:
        return cached[1]

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        cached = _cache.get(key)
        if cached and cached[0] > now:
            return cached[1]

        value = await loader()
        _cache[key] = (time.monotonic() + resolved_ttl, value)
        return value


def clear(prefix: str | None = None) -> None:
    if prefix is None:
        _cache.clear()
        _locks.clear()
        return

    keys = [key for key in _cache if key.startswith(prefix)]
    for key in keys:
        _cache.pop(key, None)
        _locks.pop(key, None)
