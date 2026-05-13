"""
Async Kafka Producer
=====================
aiokafka-based producer with JSON serialization, retry logic,
and graceful degradation to direct processing if Kafka is unavailable.
"""

import json
import logging
import asyncio
from typing import Optional, Callable

logger = logging.getLogger(__name__)

_producer = None
_fallback_handler: Optional[Callable] = None


async def start(bootstrap_servers: str = "localhost:9092"):
    """Start the Kafka producer. Fails silently if Kafka is down."""
    global _producer
    try:
        from aiokafka import AIOKafkaProducer
        _producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",
            retries=3,
            retry_backoff_ms=500,
            request_timeout_ms=10000,
        )
        await _producer.start()
        logger.info(f"Kafka producer started: {bootstrap_servers}")
    except Exception as e:
        logger.warning(f"Kafka producer failed to start ({e}). Using direct processing fallback.")
        _producer = None


async def stop():
    """Stop the Kafka producer gracefully."""
    global _producer
    if _producer:
        await _producer.stop()
        _producer = None
        logger.info("Kafka producer stopped.")


def set_fallback_handler(handler: Callable):
    """Set a fallback handler for when Kafka is unavailable.
    The handler receives (topic: str, message: dict)."""
    global _fallback_handler
    _fallback_handler = handler


async def send(topic: str, message: dict, key: Optional[str] = None) -> bool:
    """Send a message to a Kafka topic.

    If Kafka is unavailable, routes to the fallback handler (direct processing).

    Args:
        topic: Kafka topic name
        message: Dict to serialize as JSON
        key: Optional partition key

    Returns:
        True if sent successfully, False otherwise
    """
    if _producer:
        for attempt in range(3):
            try:
                key_bytes = key.encode("utf-8") if key else None
                await _producer.send_and_wait(topic, value=message, key=key_bytes)
                return True
            except Exception as e:
                wait = (2 ** attempt) * 0.5
                logger.warning(f"Kafka send attempt {attempt+1}/3 failed: {e}. Retrying in {wait}s...")
                await asyncio.sleep(wait)
        logger.error(f"Kafka send failed after 3 retries for topic {topic}")
        # Fall through to fallback
    # Fallback: process directly
    if _fallback_handler:
        try:
            await _fallback_handler(topic, message)
            return True
        except Exception as e:
            import traceback
            logger.error(f"Fallback handler failed: {e}\n{traceback.format_exc()}")
    return False


async def send_gps_ping(ping: dict) -> bool:
    """Convenience: send a GPS ping to the bus-gps-pings topic."""
    bus_id = ping.get("bus_id", ping.get("device_id", "unknown"))
    return await send("bus-gps-pings", ping, key=bus_id)


async def send_passenger_ping(ping: dict) -> bool:
    """Convenience: send a passenger ping to the passenger-pings topic."""
    return await send("passenger-pings", ping)


async def send_ghost_event(event: dict) -> bool:
    """Convenience: send a ghost bus event."""
    return await send("ghost-bus-events", event, key=event.get("bus_id"))


async def health_check() -> dict:
    """Check Kafka producer status."""
    if _producer:
        return {"status": "connected", "mode": "kafka"}
    if _fallback_handler:
        return {"status": "fallback", "mode": "direct_processing"}
    return {"status": "disconnected", "mode": "none"}
