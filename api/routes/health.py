"""
Health Check Route
===================
GET /health — reports system status of all subsystems.
"""

import time
import logging
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
