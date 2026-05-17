"""
Stops Route
=============
GET /api/stops?route={route} — returns all stops for a route from Supabase
"""

import logging
from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Stops"])


@router.get("/stops")
async def get_stops(route: str = Query(..., description="Route ID (e.g. 23C, 47A, 21B)")):
    """Get all stops for a route, ordered by sequence."""
    from infrastructure.supabase_client import get_supabase

    supabase = get_supabase()
    if not supabase:
        return {"count": 0, "stops": [], "route": route}

    try:
        result = (
            supabase.table("stops")
            .select("*")
            .eq("route", route)
            .order("sequence")
            .execute()
        )
        stops = result.data if result.data else []
    except Exception as e:
        logger.warning(f"Failed to fetch stops for route {route}: {e}")
        stops = []

    return {
        "count": len(stops),
        "stops": stops,
        "route": route,
    }
