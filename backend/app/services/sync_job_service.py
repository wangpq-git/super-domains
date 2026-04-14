import json
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

SYNC_ALL_LOCK_KEY = "sync_all_accounts:lock"
SYNC_ALL_STATUS_KEY = "sync_all_accounts:status"
SYNC_ALL_STATUS_TTL_SECONDS = 24 * 3600
SYNC_ALL_LOCK_TTL_SECONDS = 3600


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _redis():
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def get_sync_all_status() -> dict[str, Any] | None:
    redis = await _redis()
    try:
        raw = await redis.get(SYNC_ALL_STATUS_KEY)
        return json.loads(raw) if raw else None
    finally:
        await redis.aclose()


async def set_sync_all_status(payload: dict[str, Any]) -> dict[str, Any]:
    redis = await _redis()
    try:
        await redis.set(SYNC_ALL_STATUS_KEY, json.dumps(payload), ex=SYNC_ALL_STATUS_TTL_SECONDS)
        return payload
    finally:
        await redis.aclose()


async def acquire_sync_all_lock(task_id: str) -> bool:
    redis = await _redis()
    try:
        return bool(await redis.set(SYNC_ALL_LOCK_KEY, task_id, nx=True, ex=SYNC_ALL_LOCK_TTL_SECONDS))
    finally:
        await redis.aclose()


async def get_sync_all_lock_owner() -> str | None:
    redis = await _redis()
    try:
        return await redis.get(SYNC_ALL_LOCK_KEY)
    finally:
        await redis.aclose()


async def refresh_sync_all_lock(task_id: str) -> bool:
    redis = await _redis()
    try:
        current = await redis.get(SYNC_ALL_LOCK_KEY)
        if current != task_id:
            return False
        await redis.expire(SYNC_ALL_LOCK_KEY, SYNC_ALL_LOCK_TTL_SECONDS)
        return True
    finally:
        await redis.aclose()


async def release_sync_all_lock(task_id: str) -> None:
    redis = await _redis()
    try:
        current = await redis.get(SYNC_ALL_LOCK_KEY)
        if current == task_id:
            await redis.delete(SYNC_ALL_LOCK_KEY)
    finally:
        await redis.aclose()
