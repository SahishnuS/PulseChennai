"""
Health Check Route
===================
GET /health — reports system status of all subsystems.
"""

import time
import logging
import traceback
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])

_startup_time = time.time()


@router.get("/health")
async def health_check():
    """Comprehensive system health check."""
    from database import connection
    from infrastructure import async_redis
    from infrastructure import kafka_producer
    from infrastructure import kafka_consumer

    db_status = await connection.health_check()
    redis_status = await async_redis.health_check()
    kafka_prod_status = await kafka_producer.health_check()
    kafka_cons_status = await kafka_consumer.health_check()

    # Check PyTorch/CUDA
    cuda_available = False
    gpu_name = None
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            gpu_name = torch.cuda.get_device_name(0)
    except ImportError:
        pass

    # Determine overall status
    statuses = [
        db_status.get("status") == "connected",
        redis_status.get("status") in ("connected", "fallback_mode"),
        kafka_prod_status.get("status") in ("connected", "fallback"),
    ]
    if all(statuses):
        overall = "healthy"
    elif any(statuses):
        overall = "degraded"
    else:
        overall = "unhealthy"

    return {
        "status": overall,
        "uptime_seconds": round(time.time() - _startup_time, 1),
        "version": "2.0.0",
        "subsystems": {
            "database": db_status,
            "redis": redis_status,
            "kafka_producer": kafka_prod_status,
            "kafka_consumer": kafka_cons_status,
        },
        "ml": {
            "cuda_available": cuda_available,
            "gpu_name": gpu_name,
        },
    }


@router.get("/api/debug-ingest")
async def debug_ingest():
    """Debug: run the ingest pipeline directly and return error details."""
    import time
    from infrastructure import kafka_producer, async_redis

    msg = {
        "bus_id": "MTC-DEBUG-001",
        "lat": 13.0827,
        "lng": 80.2707,
        "speed": 25,
        "route_id": "21G",
        "heading": 0,
        "jitter": 1.0,
        "age_s": 0.5,
        "accuracy_m": 10,
        "timestamp": time.time() * 1000,
    }

    # Check fallback handler
    handler = kafka_producer._fallback_handler
    result = {"fallback_handler": str(handler)}

    # Try calling it directly
    if handler:
        try:
            await handler("bus-gps-pings", msg)
            result["handler_result"] = "success"
        except Exception as e:
            result["handler_error"] = str(e)
            result["traceback"] = traceback.format_exc()
    else:
        result["handler_error"] = "No fallback handler registered"

    # Try send_gps_ping
    try:
        ok = await kafka_producer.send_gps_ping(msg)
        result["send_result"] = ok
    except Exception as e:
        result["send_error"] = str(e)
        result["send_traceback"] = traceback.format_exc()

    # Check store
    buses = await async_redis.get_all_bus_states()
    result["buses_in_store"] = len(buses)

    return result
