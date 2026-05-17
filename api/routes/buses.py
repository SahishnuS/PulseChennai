"""
Bus Status + ETA Routes (Supabase Edition)
=============================================
GET /api/buses — all active bus states from Supabase
GET /api/buses/{bus_id}/eta — ETA calculation with ghost uncertainty
GET /api/metrics — system-wide metrics
"""

import math
import logging
from datetime import datetime
from fastapi import APIRouter, Query
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Buses"])

# Stop coordinates keyed by stop ID (for ETA calculations)
# Imported from seed_stops.py route data
_STOP_COORDS = {
    "STOP_THIRUVANMIYUR": (12.9824, 80.2588),
    "STOP_LATTICE_BRIDGE": (12.9831, 80.2541),
    "STOP_ADYAR_SIGNAL": (12.9799, 80.2576),
    "STOP_GANDHI_NAGAR": (12.9836, 80.2463),
    "STOP_INDRA_NAGAR": (12.9901, 80.2378),
    "STOP_KOTTURPURAM": (12.9986, 80.2369),
    "STOP_SAIDAPET_23C": (13.0182, 80.2213),
    "STOP_MAMBALAM": (13.0365, 80.2129),
    "STOP_T_NAGAR": (13.0418, 80.2341),
    "STOP_ANNA_NAGAR_TOWER": (13.0891, 80.2101),
    "STOP_15TH_MAIN_ROAD": (13.0842, 80.2089),
    "STOP_THIRUMANGALAM": (13.0778, 80.2023),
    "STOP_KOYAMBEDU_CMBT": (13.0722, 80.1963),
    "STOP_KOYAMBEDU_MARKET": (13.0698, 80.1944),
    "STOP_CHENNAI_CENTRAL": (13.0827, 80.2756),
    "STOP_PARK_TOWN": (13.0792, 80.2731),
    "STOP_SAIDAPET_BRIDGE": (13.0198, 80.2234),
    "STOP_CHROMPET": (12.9516, 80.1430),
    "STOP_TAMBARAM": (12.9249, 80.1000),
}

CHENNAI_AVG_SPEED_KMH = 18.0


def _haversine_km(lat1, lon1, lat2, lon2):
    """Haversine distance in kilometers."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


@router.get("/buses")
async def get_all_buses():
    """Get all active bus states from Supabase."""
    from infrastructure.supabase_client import get_supabase

    supabase = get_supabase()
    if not supabase:
        return {"count": 0, "buses": [], "timestamp": datetime.now().isoformat()}

    try:
        result = supabase.table("buses").select("*").execute()
        buses = result.data if result.data else []
    except Exception as e:
        logger.warning(f"Failed to fetch buses: {e}")
        buses = []

    return {
        "count": len(buses),
        "buses": buses,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/buses/{bus_id}")
async def get_bus(bus_id: str):
    """Get a single bus state."""
    from infrastructure.supabase_client import get_supabase

    supabase = get_supabase()
    if not supabase:
        return {"error": "Supabase not configured"}

    try:
        result = supabase.table("buses").select("*").eq("id", bus_id).execute()
        if result.data and len(result.data) > 0:
            return {"bus_id": bus_id, **result.data[0]}
    except Exception as e:
        logger.warning(f"Failed to fetch bus {bus_id}: {e}")

    return {"error": f"Bus {bus_id} not found", "bus_id": bus_id}


@router.get("/buses/{bus_id}/eta")
async def get_bus_eta(
    bus_id: str,
    stop_id: str = Query(..., description="Target stop ID"),
):
    """
    Calculate ETA for a bus to a target stop.

    If bus is NOT ghost: distance / 18 km/h average speed
    If bus IS ghost: add 40% uncertainty band
    Returns: {eta_min, eta_max, confidence, is_ghost}
    """
    from infrastructure.supabase_client import get_supabase

    supabase = get_supabase()
    if not supabase:
        return {"error": "Supabase not configured"}

    # Get bus state
    try:
        result = supabase.table("buses").select("*").eq("id", bus_id).execute()
        if not result.data:
            return {"error": f"Bus {bus_id} not found"}
        bus = result.data[0]
    except Exception as e:
        return {"error": f"Failed to fetch bus: {e}"}

    # Get target stop coordinates
    stop_coords = _STOP_COORDS.get(stop_id)
    if not stop_coords:
        # Try fetching from Supabase
        try:
            stop_result = supabase.table("stops").select("lat,lng").eq("id", stop_id).execute()
            if stop_result.data:
                stop_coords = (stop_result.data[0]["lat"], stop_result.data[0]["lng"])
        except Exception:
            pass

    if not stop_coords:
        return {"error": f"Stop {stop_id} not found"}

    bus_lat = bus.get("lat", 0)
    bus_lng = bus.get("lng", 0)
    is_ghost = bus.get("is_ghost", False)

    # Calculate distance
    distance_km = _haversine_km(bus_lat, bus_lng, stop_coords[0], stop_coords[1])

    # Base ETA in minutes
    base_eta_min = (distance_km / CHENNAI_AVG_SPEED_KMH) * 60

    if is_ghost:
        # Ghost bus: wider uncertainty, lower confidence
        eta_min = max(1, int(base_eta_min * 0.8))
        eta_max = max(2, int(base_eta_min * 1.4))
        confidence = "low"
    elif base_eta_min < 5:
        # Very close: tight estimate, high confidence
        eta_min = max(1, int(base_eta_min * 0.9))
        eta_max = max(2, int(base_eta_min * 1.1))
        confidence = "high"
    else:
        # Normal: moderate uncertainty
        eta_min = max(1, int(base_eta_min * 0.85))
        eta_max = max(2, int(base_eta_min * 1.2))
        confidence = "medium"

    return {
        "bus_id": bus_id,
        "stop_id": stop_id,
        "eta_min": eta_min,
        "eta_max": eta_max,
        "confidence": confidence,
        "is_ghost": is_ghost,
        "distance_km": round(distance_km, 2),
        "reliability_score": bus.get("reliability_score", 1.0),
    }


@router.get("/metrics")
async def get_metrics():
    """System-wide metrics."""
    from infrastructure.supabase_client import get_supabase

    supabase = get_supabase()
    if not supabase:
        return {"total_buses": 0, "active_buses": 0, "ghost_buses": 0}

    try:
        result = supabase.table("buses").select("*").execute()
        buses = result.data if result.data else []
    except Exception:
        buses = []

    total = len(buses)
    ghosts = sum(1 for b in buses if b.get("is_ghost"))
    avg_score = sum(b.get("reliability_score", 1) for b in buses) / max(total, 1)

    return {
        "total_buses": total,
        "active_buses": total - ghosts,
        "ghost_buses": ghosts,
        "system_health": round(avg_score * 100, 1),
        "timestamp": datetime.now().isoformat(),
    }
