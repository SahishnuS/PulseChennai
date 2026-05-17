"""
Upstash Redis REST Client — Free Tier Cache + Pub/Sub
=======================================================
Uses httpx for REST calls to Upstash Redis.
No redis-py dependency needed — works purely over HTTP.

Upstash REST API pattern:
  GET  https://{url}/get/{key}
  POST https://{url}/set/{key}/{value}?EX={seconds}
  POST https://{url}/publish/{channel}/{message}
"""

import os
import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_base_url: Optional[str] = None
_token: Optional[str] = None
_http_client: Optional[httpx.AsyncClient] = None


async def init():
    """Initialize the Upstash Redis REST client."""
    global _base_url, _token, _http_client

    _base_url = os.getenv("UPSTASH_REDIS_REST_URL", "")
    _token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

    if not _base_url or not _token:
        logger.warning(
            "UPSTASH_REDIS_REST_URL or UPSTASH_REDIS_REST_TOKEN not set. "
            "Upstash Redis features will be unavailable."
        )
        return

    # Remove trailing slash
    _base_url = _base_url.rstrip("/")

    _http_client = httpx.AsyncClient(
        timeout=5.0,
        headers={"Authorization": f"Bearer {_token}"},
    )
    logger.info(f"Upstash Redis REST client initialized: {_base_url[:40]}...")


async def close():
    """Close the HTTP client."""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None
        logger.info("Upstash Redis REST client closed.")


async def get(key: str) -> Optional[str]:
    """GET a value from Upstash Redis."""
    if not _http_client:
        return None
    try:
        resp = await _http_client.get(f"{_base_url}/get/{key}")
        data = resp.json()
        return data.get("result")
    except Exception as e:
        logger.warning(f"Upstash GET failed for key={key}: {e}")
        return None


async def set(key: str, value: str, ex: Optional[int] = None) -> bool:
    """SET a value in Upstash Redis, with optional expiry in seconds."""
    if not _http_client:
        return False
    try:
        if ex:
            # Use the command pipeline approach for SET with EX
            cmd = ["SET", key, value, "EX", str(ex)]
            resp = await _http_client.post(f"{_base_url}", json=cmd)
        else:
            cmd = ["SET", key, value]
            resp = await _http_client.post(f"{_base_url}", json=cmd)
        data = resp.json()
        return data.get("result") == "OK"
    except Exception as e:
        logger.warning(f"Upstash SET failed for key={key}: {e}")
        return False


async def set_json(key: str, value: dict, ex: Optional[int] = None) -> bool:
    """SET a JSON-serializable dict in Upstash Redis."""
    return await set(key, json.dumps(value), ex=ex)


async def get_json(key: str) -> Optional[dict]:
    """GET and parse a JSON value from Upstash Redis."""
    raw = await get(key)
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    return None


async def publish(channel: str, message: str) -> bool:
    """PUBLISH a message to an Upstash Redis channel."""
    if not _http_client:
        return False
    try:
        cmd = ["PUBLISH", channel, message]
        resp = await _http_client.post(f"{_base_url}", json=cmd)
        data = resp.json()
        return data.get("result", 0) >= 0
    except Exception as e:
        logger.warning(f"Upstash PUBLISH failed for channel={channel}: {e}")
        return False


async def publish_json(channel: str, data: dict) -> bool:
    """PUBLISH a JSON-serializable dict to an Upstash Redis channel."""
    return await publish(channel, json.dumps(data))


async def delete(key: str) -> bool:
    """DELETE a key from Upstash Redis."""
    if not _http_client:
        return False
    try:
        cmd = ["DEL", key]
        resp = await _http_client.post(f"{_base_url}", json=cmd)
        return True
    except Exception as e:
        logger.warning(f"Upstash DEL failed for key={key}: {e}")
        return False


async def health_check() -> dict:
    """Check Upstash Redis connectivity."""
    if not _http_client:
        return {"status": "not_configured"}
    try:
        resp = await _http_client.get(f"{_base_url}/ping")
        data = resp.json()
        if data.get("result") == "PONG":
            return {"status": "connected"}
        return {"status": "error", "detail": str(data)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
