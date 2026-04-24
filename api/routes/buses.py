"""
Bus Status Routes
==================
GET /api/buses — returns all active bus states from Redis.
GET /api/buses/{bus_id} — returns a single bus state.
GET /api/ghost-events — returns recent ghost bus events.
GET /api/traffic — returns current traffic state.
"""

import logging
from fastapi import APIRouter
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Buses"])


@router.get("/buses")
async def get_all_buses():
    """Get all active bus states from Redis Speed Layer."""
    from infrastructure import async_redis

    buses = await async_redis.get_all_bus_states()
    return {
        "count": len(buses),
        "buses": buses,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/buses/{bus_id}")
async def get_bus(bus_id: str):
    """Get a single bus state."""
    from infrastructure import async_redis

    state = await async_redis.get_bus_state(bus_id)
    if state is None:
        return {"error": f"Bus {bus_id} not found", "bus_id": bus_id}
    return {"bus_id": bus_id, **state}


@router.get("/ghost-events")
async def get_ghost_events():
    """Get recent ghost bus events from PostgreSQL."""
    try:
        from database import connection
        pool = connection.get_pool()
        if pool:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT bus_id, detected_at, health_score_at_detection,
                              trigger_reason, recovered_at, recovery_source,
                              passenger_ping_count
                       FROM ghost_bus_events
                       ORDER BY detected_at DESC LIMIT 20"""
                )
                events = []
                for row in rows:
                    events.append({
                        "bus_id": row["bus_id"],
                        "detected_at": row["detected_at"].isoformat() if row["detected_at"] else None,
                        "health_score": row["health_score_at_detection"],
                        "trigger_reason": row["trigger_reason"],
                        "recovered_at": row["recovered_at"].isoformat() if row["recovered_at"] else None,
                        "recovery_source": row["recovery_source"],
                        "passenger_ping_count": row["passenger_ping_count"],
                    })
                return {"count": len(events), "events": events}
    except Exception as e:
        logger.debug(f"Could not fetch ghost events: {e}")
    return {"count": 0, "events": []}


@router.get("/traffic")
async def get_traffic():
    """Get current traffic summary from TomTom client."""
    from traffic import tomtom_client
    summary = tomtom_client.get_traffic_summary()
    segments = tomtom_client.get_latest_snapshots()
    segment_list = []
    for label, snap in segments.items():
        from dataclasses import asdict
        segment_list.append(asdict(snap))
    summary["segments"] = segment_list
    return summary


@router.get("/metrics")
async def get_metrics():
    """System-wide metrics for the dashboard."""
    from infrastructure import async_redis
    from traffic import tomtom_client

    buses = await async_redis.get_all_bus_states()
    total = len(buses)
    ghosts = sum(1 for b in buses if b.get("is_ghost"))
    recovered = sum(1 for b in buses if b.get("status") == "ghost_recovered")
    avg_hw = sum(b.get("hw_score", 1) for b in buses) / max(total, 1)

    traffic = tomtom_client.get_traffic_summary()

    return {
        "total_buses": total,
        "active_buses": total - ghosts,
        "ghost_buses": ghosts,
        "recovered_buses": recovered,
        "system_health": round(avg_hw * 100, 1),
        "traffic": traffic,
        "timestamp": datetime.now().isoformat(),
    }
