import json
import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


def _key(number: str) -> str:
    return f"cargo:tracking:{number.upper()}"


async def get_client() -> aioredis.Redis | None:
    global _redis
    if _redis is not None:
        return _redis
    try:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        await _redis.ping()
        return _redis
    except Exception as exc:
        logger.warning("Redis not available, caching disabled: %s", exc)
        _redis = None
        return None


async def get_cached(number: str) -> dict | None:
    client = await get_client()
    if client is None:
        return None
    try:
        raw = await client.get(_key(number))
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("Cache read error for %s: %s", number, exc)
        return None


async def set_cached(number: str, data: dict) -> None:
    client = await get_client()
    if client is None:
        return
    try:
        await client.setex(_key(number), settings.cache_ttl_seconds, json.dumps(data))
    except Exception as exc:
        logger.warning("Cache write error for %s: %s", number, exc)


async def close() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
