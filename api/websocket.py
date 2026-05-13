"""
WebSocket Endpoint
===================
/ws/live — pushes real-time bus updates to connected frontend clients.
Subscribes to Redis pub/sub channel "bus_updates" and forwards every message.
Includes heartbeat ping/pong and automatic reconnection handling.
"""

import json
import logging
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSocket"])

# Track connected clients
_clients: set[WebSocket] = set()


@router.websocket("/ws/live")
async def websocket_endpoint(ws: WebSocket):
    """Real-time bus update stream via WebSocket."""
    await ws.accept()
    _clients.add(ws)
    logger.info(f"WebSocket client connected. Total: {len(_clients)}")

    try:
        # Send current state immediately on connect
        from infrastructure import async_redis
        buses = await async_redis.get_all_bus_states()
        await ws.send_json({
            "type": "initial_state",
            "buses": buses,
        })

        # Subscribe to Redis pub/sub
        pubsub = await async_redis.subscribe("bus_updates")

        if pubsub:
            # Redis pub/sub listener
            async def _listen_redis():
                try:
                    async for message in pubsub.listen():
                        if message["type"] == "message":
                            data = json.loads(message["data"])
                            await ws.send_json(data)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.debug(f"Redis listener error: {e}")
                finally:
                    await pubsub.unsubscribe("bus_updates")

            redis_task = asyncio.create_task(_listen_redis())

            # Keep alive with heartbeat + listen for client messages
            try:
                while True:
                    try:
                        data = await asyncio.wait_for(ws.receive_text(), timeout=30)
                        if data == "ping":
                            await ws.send_text("pong")
                    except asyncio.TimeoutError:
                        # Send heartbeat
                        await ws.send_json({"type": "heartbeat"})
            except WebSocketDisconnect:
                pass
            finally:
                redis_task.cancel()
                try:
                    await redis_task
                except asyncio.CancelledError:
                    pass
        else:
            # No Redis — fall back to polling loop
            while True:
                try:
                    buses = await async_redis.get_all_bus_states()
                    await ws.send_json({
                        "type": "bus_update_batch",
                        "buses": buses,
                    })
                    await asyncio.sleep(2)  # Poll every 2 seconds
                    # Check for client messages
                    try:
                        data = await asyncio.wait_for(ws.receive_text(), timeout=0.1)
                        if data == "ping":
                            await ws.send_text("pong")
                    except asyncio.TimeoutError:
                        pass
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.debug(f"WebSocket fallback error: {e}")
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        _clients.discard(ws)
        logger.info(f"WebSocket client disconnected. Total: {len(_clients)}")


async def broadcast(data: dict):
    """Broadcast a message to all connected WebSocket clients."""
    dead = set()
    for ws in _clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    _clients -= dead
