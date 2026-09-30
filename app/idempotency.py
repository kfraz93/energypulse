import json

import redis.asyncio as aioredis
from fastapi import Header, HTTPException, status

# Initializing async Redis client for idempotency checks
redis_client = aioredis.from_url("redis://localhost:6379/0", decode_responses=True)


async def check_idempotency(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str | None:
    """
    Dependency that checks if an incoming request contains an Idempotency-Key.
    If the key exists in Redis, it short-circuits the request and returns the
    cached response.
    :param response:
    :param idempotency_key:
    :return:
    """
    if not idempotency_key:
        return None
    cache_key = f"idempotency:{idempotency_key}"
    cached_data = await redis_client.get(cache_key)

    if cached_data:
        # Replay the cached response immediately
        cached_json = json.loads(cached_data)
        raise HTTPException(
            status_code=status.HTTP_200_OK,
            detail={
                "status": "replayed",
                "message": "Duplicate request detected. Returning cached"
                " idempotent response",
                "cached_payload": cached_json,
            },
        )
    return idempotency_key


async def save_idempotency_response(
    idempotency_key: str | None, response_data: dict, expire_seconds: int = 86400
):
    """
    Saves the successful response payload against the idempotency key in Redis
     for 24 hours.
    :param idempotency_key:
    :param response_data:
    :param expire_seconds:
    :return:
    """
    if idempotency_key:
        cache_key = f"idempotency:{idempotency_key}"
        await redis_client.setex(cache_key, expire_seconds, json.dumps(response_data))
