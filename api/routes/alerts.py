"""
Alerts + Journey Watch Routes
=================================
GET  /api/alerts            — last 20 alerts from Supabase
POST /api/journey/watch     — start watching a bus for a stop
"""

import logging
from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Alerts"])


@router.get("/alerts")
async def get_alerts():
    """Get the last 20 alerts from Supabase, ordered by created_at desc."""
    from infrastructure.supabase_client import get_supabase

    supabase = get_supabase()
    if not supabase:
        return {"count": 0, "alerts": []}

    try:
        result = (
            supabase.table("alerts")
            .select("*")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        alerts = result.data if result.data else []
    except Exception as e:
        logger.warning(f"Failed to fetch alerts: {e}")
        alerts = []

    return {
        "count": len(alerts),
        "alerts": alerts,
    }


class JourneyWatchRequest(BaseModel):
    session_id: str = Field(..., description="Client session UUID")
    bus_id: str = Field(..., description="Bus ID to watch")
    target_stop_id: str = Field(..., description="Target stop ID")


@router.post("/journey/watch")
async def start_journey_watch(req: JourneyWatchRequest):
    """Start watching a bus for a specific stop arrival."""
    from infrastructure.supabase_client import get_supabase

    supabase = get_supabase()
    if not supabase:
        return {"error": "Supabase not configured"}

    try:
        result = supabase.table("journey_watches").insert({
            "session_id": req.session_id,
            "bus_id": req.bus_id,
            "target_stop_id": req.target_stop_id,
        }).execute()

        watch_id = result.data[0]["id"] if result.data else None
        return {"watch_id": watch_id, "status": "watching"}
    except Exception as e:
        logger.error(f"Failed to create journey watch: {e}")
        return {"error": str(e)}
