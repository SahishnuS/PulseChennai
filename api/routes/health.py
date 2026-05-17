"""
Health Check Route
====================
GET /health — system health check
"""

import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """System health check."""
    from infrastructure.supabase_client import get_supabase
    from infrastructure import upstash_redis

    checks = {}

    # Supabase
    supabase = get_supabase()
    if supabase:
        try:
            result = supabase.table("buses").select("id").limit(1).execute()
            checks["supabase"] = "connected"
        except Exception as e:
            checks["supabase"] = f"error: {e}"
    else:
        checks["supabase"] = "not_configured"

    # Upstash Redis
    redis_health = await upstash_redis.health_check()
    checks["upstash_redis"] = redis_health.get("status", "unknown")

    overall = "healthy" if all(v in ("connected", "not_configured") for v in checks.values()) else "degraded"

    return {
        "status": overall,
        "checks": checks,
    }
