"""
Async Kafka Consumer
=====================
aiokafka-based consumer that runs as a background asyncio task.
Processes GPS pings through the full pipeline:
  Hardware Scorer → Ghost Detector → Data Fusion → Redis + PostgreSQL

Gracefully handles Kafka unavailability.
"""

import json
import logging
import asyncio
from typing import Callable, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

_consumer = None
_running = False
_task: Optional[asyncio.Task] = None


async def start(
    bootstrap_servers: str,
    topics: list[str],
    group_id: str,
    message_handler: Callable,
):
    """Start the Kafka consumer as a background task.

    Args:
        bootstrap_servers: Kafka broker address
        topics: List of topics to subscribe to
        group_id: Consumer group ID
        message_handler: Async callable(topic, message_dict) to process each message
    """
    global _consumer, _running, _task

    try:
        from aiokafka import AIOKafkaConsumer

        _consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="latest",
            enable_auto_commit=False,
            max_poll_records=100,
        )
        await _consumer.start()
        _running = True
        _task = asyncio.create_task(_consume_loop(message_handler))
        logger.info(f"Kafka consumer started on topics: {topics}")

    except Exception as e:
        logger.warning(f"Kafka consumer failed to start ({e}). Messages will be processed via HTTP fallback.")
        _consumer = None


async def _consume_loop(handler: Callable):
    """Main consumption loop. Runs until stop() is called."""
    global _running
    while _running and _consumer:
        try:
            batch = await _consumer.getmany(timeout_ms=1000, max_records=50)
            for tp, messages in batch.items():
                for msg in messages:
                    try:
                        await handler(tp.topic, msg.value)
                    except Exception as e:
                        logger.error(f"Error processing message from {tp.topic}: {e}")
                # Manual commit after successful batch processing
                await _consumer.commit()

        except asyncio.CancelledError:
            logger.info("Kafka consumer loop cancelled.")
            break
        except Exception as e:
            logger.error(f"Kafka consumer error: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

    logger.info("Kafka consumer loop exited.")


async def stop():
    """Stop the consumer gracefully."""
    global _running, _consumer, _task
    _running = False
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
    if _consumer:
        await _consumer.stop()
        _consumer = None
    logger.info("Kafka consumer stopped.")


async def health_check() -> dict:
    """Check consumer status."""
    if _consumer and _running:
        return {"status": "consuming", "running": True}
    return {"status": "stopped", "running": False}
