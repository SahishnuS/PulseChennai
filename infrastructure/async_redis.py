"""
Async Redis Client
===================
redis.asyncio-based client for the Speed Layer.
Handles bus state, pub/sub for WebSocket, and passenger ping geospatial ops.
Gracefully degrades to in-memory fallback if Redis is unreachable.
"""

import json
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_client = None
_fallback_store: dict[str, dict] = {}  # In-memory fallback
_pubsub_subscribers: list = []


async def connect(redis_url: str = "redis://localhost:6379/0"):
    """Initialize the async Redis client."""
    global _client
    try:
        import redis.asyncio as aioredis
        _client = aioredis.from_url(
            redis_url,
            decode_responses=True,
            max_connections=20,
        )
        await _client.ping()
        logger.info(f"Redis connected: {redis_url}")
    except Exception as e:
        logger.warning(f"Redis unavailable ({e}). Using in-memory fallback.")
        _client = None


async def disconnect():
    """Close the Redis connection."""
    global _client
    if _client:
        await _client.aclose()
        _client = None
        logger.info("Redis disconnected.")


async def set_bus_state(bus_id: str, state: dict, ttl: int = 300):
    """Store a bus state as a Redis hash with TTL."""
    if _client:
        try:
            key = f"bus:{bus_id}"
            # Flatten all values to strings for Redis hash
            flat = {k: str(v) for k, v in state.items()}
            flat["_updated"] = str(time.time())
            await _client.hset(key, mapping=flat)
            await _client.expire(key, ttl)
            return
        except Exception as e:
            logger.warning(f"Redis set_bus_state failed: {e}")
    # Fallback
    _fallback_store[f"bus:{bus_id}"] = {**state, "_updated": time.time()}


async def get_bus_state(bus_id: str) -> Optional[dict]:
    """Get a single bus state from Redis or fallback."""
    if _client:
        try:
            data = await _client.hgetall(f"bus:{bus_id}")
            if data:
                return _parse_bus_hash(data)
        except Exception as e:
            logger.warning(f"Redis get_bus_state failed: {e}")
    # Fallback
    return _fallback_store.get(f"bus:{bus_id}")


async def get_all_bus_states() -> list[dict]:
    """Get all active bus states."""
    buses = []
    if _client:
        try:
            cursor = 0
            while True:
                cursor, keys = await _client.scan(cursor=cursor, match="bus:*", count=100)
                if keys:
                    pipe = _client.pipeline()
                    for key in keys:
                        pipe.hgetall(key)
                    results = await pipe.execute()
                    for key, data in zip(keys, results):
                        if data:
                            parsed = _parse_bus_hash(data)
                            parsed["trip_id"] = key.replace("bus:", "")
                            buses.append(parsed)
                if cursor == 0:
                    break
            return buses
        except Exception as e:
            logger.warning(f"Redis get_all_bus_states failed: {e}")
    # Fallback
    for key, state in _fallback_store.items():
        if key.startswith("bus:"):
            buses.append({**state, "trip_id": key.replace("bus:", "")})
    return buses


async def publish_update(channel: str, data: dict):
    """Publish an update to a Redis pub/sub channel (for WebSocket broadcasting)."""
    if _client:
        try:
            await _client.publish(channel, json.dumps(data))
            return
        except Exception as e:
            logger.warning(f"Redis publish failed: {e}")


async def subscribe(channel: str):
    """Subscribe to a Redis pub/sub channel. Returns an async iterator of messages."""
    if _client:
        try:
            pubsub = _client.pubsub()
            await pubsub.subscribe(channel)
            return pubsub
        except Exception as e:
            logger.warning(f"Redis subscribe failed: {e}")
    return None


async def set_tomtom_cache(segment: str, data: dict, ttl: int = 120):
    """Cache a TomTom traffic response."""
    if _client:
        try:
            await _client.set(
                f"tomtom:{segment}",
                json.dumps(data),
                ex=ttl,
            )
        except Exception as e:
            logger.warning(f"Redis set_tomtom_cache failed: {e}")


async def get_tomtom_cache(segment: str) -> Optional[dict]:
    """Get a cached TomTom response."""
    if _client:
        try:
            raw = await _client.get(f"tomtom:{segment}")
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning(f"Redis get_tomtom_cache failed: {e}")
    return None


async def geoadd_passenger_ping(session_token: str, lat: float, lon: float):
    """Add a passenger ping to the geospatial index."""
    if _client:
        try:
            await _client.geoadd("passenger_pings", (lon, lat, session_token))
            await _client.expire("passenger_pings", 120)  # 2-minute TTL
        except Exception as e:
            logger.warning(f"Redis geoadd failed: {e}")


async def georadius_passenger_pings(lat: float, lon: float, radius_m: float = 200) -> list[dict]:
    """Find passenger pings near a location using Redis GEOSEARCH."""
    if _client:
        try:
            results = await _client.geosearch(
                "passenger_pings",
                longitude=lon,
                latitude=lat,
                radius=radius_m,
                unit="m",
                withcoord=True,
            )
            pings = []
            for item in results:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    name = item[0] if isinstance(item[0], str) else str(item[0])
                    coords = item[1] if len(item) > 1 else None
                    if coords and len(coords) >= 2:
                        pings.append({
                            "session_token": name,
                            "lon": float(coords[0]),
                            "lat": float(coords[1]),
                        })
            return pings
        except Exception as e:
            logger.warning(f"Redis georadius failed: {e}")
    return []


async def health_check() -> dict:
    """Check Redis connectivity."""
    if _client:
        try:
            await _client.ping()
            info = await _client.info("memory")
            return {
                "status": "connected",
                "used_memory_human": info.get("used_memory_human", "unknown"),
            }
        except Exception:
            return {"status": "error"}
    return {"status": "fallback_mode"}


def _parse_bus_hash(data: dict) -> dict:
    """Parse Redis hash string values back to proper types."""
    return {
        "lat": float(data.get("lat", 0)),
        "lng": float(data.get("lng", 0)),
        "speed": float(data.get("speed", 0)),
        "heading": float(data.get("heading", 0)),
        "hw_score": float(data.get("hw_score", 1)),
        "is_ghost": data.get("is_ghost", "False") == "True",
        "status": data.get("status", "unknown"),
        "route_id": data.get("route_id", ""),
        "h3_cell": data.get("h3_cell", ""),
        "passenger_count": int(float(data.get("passenger_count", 0))),
        "source": data.get("source", "AIS140"),
        "confidence": float(data.get("confidence", 1.0)),
        "last_seen": float(data.get("_updated", 0)),
    }
