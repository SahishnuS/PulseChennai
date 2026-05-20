"""
ETA API Route — Pulse-Chennai
==============================
Endpoints:
  GET  /api/eta?src=<text|lat,lon>&dst=<text|lat,lon>
       → Calculate ETA between any two points (text or coordinates)

  GET  /api/eta/buses
       → Calculate live ETA for ALL active buses to their route terminus

  GET  /api/eta/bus/{bus_id}?dst=<text|lat,lon>
       → Calculate ETA for a specific bus to a custom destination
"""

import os
import random
import logging
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["ETA"])


# ── Confidence scoring ────────────────────────────────────────────────────────

def compute_confidence(
    method_used: str,
    is_ghost: bool,
    tomtom_applied: bool,
    eta_minutes: float,
) -> dict:
    """
    Calculate an integer confidence score [25, 97] for an ETA prediction.

    Rules (applied in order):
    1. Base = 85
    2. -20 if single-model fallback (one of XGB/LGB failed)
    3. -30 if GradientBoosting on-the-fly fallback
    4. -15 if bus is a ghost (reliability < 0.3)
    5. +10 if TomTom live correction was applied
    6. ETA range penalty: 0/<5min, -5/5-15min, -10/15-30min, -20/>30min
    7. Gaussian noise ±3
    8. Clamp to [25, 97]
    """
    score = 85

    method_lower = (method_used or "").lower()

    # Rule 2: single-model fallback
    if "single" in method_lower or "one model" in method_lower:
        score -= 20
    # Rule 3: on-the-fly GradientBoosting fallback
    if "gradientboosting" in method_lower or "fallback" in method_lower:
        score -= 30

    # Rule 4: ghost bus
    if is_ghost:
        score -= 15

    # Rule 5: TomTom correction bonus
    if tomtom_applied:
        score += 10

    # Rule 6: ETA range penalty
    if eta_minutes >= 30:
        score -= 20
    elif eta_minutes >= 15:
        score -= 10
    elif eta_minutes >= 5:
        score -= 5
    # < 5 min: no penalty

    # Rule 7: Gaussian noise
    score += random.gauss(0, 3)

    # Rule 8: clamp
    score = int(round(max(25, min(97, score))))

    label = "HIGH" if score >= 75 else ("MODERATE" if score >= 50 else "LOW")

    return {"confidence_pct": score, "confidence_label": label}


def _model_used_label(method_str: str, tomtom_applied: bool) -> str:
    """Map method_used string to a clean model_used enum value."""
    m = (method_str or "").lower()
    if "ensemble" in m or "xgb" in m or "lgb" in m:
        return "ensemble"
    if "single" in m or "one model" in m:
        return "single"
    if "fallback" in m or "gradientboosting" in m or "analytical" in m or "historical" in m:
        return "fallback"
    if "tomtom" in m and not tomtom_applied:
        return "analytical"
    return "analytical"


# Chennai route termini for per-bus ETA calculation
_ROUTE_TERMINI = {
    "19":   {"lat": 13.0338, "lon": 80.2326, "label": "T. Nagar Bus Terminus"},
    "102X": {"lat": 13.0827, "lon": 80.2707, "label": "Broadway Bus Stand"},
}

# Intermediate stops for each route (for distance context)
_ROUTE_STOPS = {
    "19": [
        {"lat": 12.7427, "lon": 80.2297, "label": "Thiruporur"},
        {"lat": 12.8230, "lon": 80.2280, "label": "Siruseri"},
        {"lat": 12.8710, "lon": 80.2240, "label": "Perungudi"},
        {"lat": 12.9010, "lon": 80.2279, "label": "Sholinganallur"},
        {"lat": 12.9500, "lon": 80.2350, "label": "Medavakkam"},
        {"lat": 12.9786, "lon": 80.2209, "label": "Velachery"},
        {"lat": 13.0338, "lon": 80.2326, "label": "T. Nagar"},
    ],
    "102X": [
        {"lat": 12.7427, "lon": 80.2297, "label": "Thiruporur"},
        {"lat": 12.8520, "lon": 80.2210, "label": "Tambaram"},
        {"lat": 12.9249, "lon": 80.1000, "label": "Chromepet"},
        {"lat": 13.0107, "lon": 80.2145, "label": "Kathipara"},
        {"lat": 13.0694, "lon": 80.1948, "label": "Koyambedu"},
        {"lat": 13.0569, "lon": 80.2497, "label": "Anna Salai"},
        {"lat": 13.0827, "lon": 80.2707, "label": "Broadway"},
    ],
}


def _get_api_key() -> str:
    return os.getenv("TOMTOM_API_KEY") or os.getenv("VITE_TOMTOM_API_KEY", "")


def _find_next_stop(bus_lat: float, bus_lon: float, route_id: str) -> Optional[dict]:
    """Find the next upcoming stop for a bus on its route."""
    from traffic.eta_engine import _haversine_meters
    stops = _ROUTE_STOPS.get(route_id, [])
    if not stops:
        return None

    min_dist = float("inf")
    nearest_idx = 0
    for i, stop in enumerate(stops):
        d = _haversine_meters(bus_lat, bus_lon, stop["lat"], stop["lon"])
        if d < min_dist:
            min_dist = d
            nearest_idx = i

    # Return next stop (not the one we're at)
    next_idx = min(nearest_idx + 1, len(stops) - 1)
    return stops[next_idx]


@router.get("/eta")
async def calculate_eta_endpoint(
    src: str = Query(..., description="Source: text address or 'lat,lon'"),
    dst: str = Query(..., description="Destination: text address or 'lat,lon'"),
    method: str = Query("auto", description="Method: auto | tomtom | haversine | historical"),
):
    """
    Calculate ETA between source and destination.

    Supports text addresses (geocoded via TomTom Search API) or raw lat,lon pairs.

    Examples:
      /api/eta?src=Koyambedu Bus Stand&dst=T. Nagar
      /api/eta?src=13.0694,80.1948&dst=13.0338,80.2326
    """
    from traffic.eta_engine import calculate_eta

    if not src.strip() or not dst.strip():
        raise HTTPException(status_code=400, detail="Both src and dst are required")

    try:
        result = await calculate_eta(
            src=src.strip(),
            dst=dst.strip(),
            api_key=_get_api_key(),
        )
        eta_dict   = result.to_dict()
        eta_min    = eta_dict.get("best_eta_minutes") or 0
        tomtom_ok  = bool(result.eta_live_seconds)
        conf       = compute_confidence(
            method_used    = result.method_used,
            is_ghost       = False,
            tomtom_applied = tomtom_ok,
            eta_minutes    = eta_min,
        )
        return {
            "status":          "ok",
            "eta":             eta_dict,
            "eta_minutes":     eta_min,
            "eta_corrected_minutes": eta_min,
            "confidence_pct":  conf["confidence_pct"],
            "confidence_label": conf["confidence_label"],
            "model_used":      _model_used_label(result.method_used, tomtom_ok),
            "tomtom_applied":  tomtom_ok,
            "requested_at":    datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"ETA calculation error: {e}")
        raise HTTPException(status_code=500, detail=f"ETA calculation failed: {str(e)}")


@router.get("/eta/buses")
async def get_all_bus_etas():
    """
    Calculate live ETA for all active buses to their respective route termini.
    Uses each bus's current GPS position as the source.
    """
    from traffic.eta_engine import calculate_eta_for_bus
    from infrastructure import async_redis

    api_key = _get_api_key()

    try:
        buses = await async_redis.get_all_bus_states()
    except Exception:
        buses = []

    if not buses:
        return {"status": "no_buses", "etas": [], "count": 0}

    results = []
    for bus in buses:
        route_id = bus.get("route_id", bus.get("route", ""))
        terminus = _ROUTE_TERMINI.get(route_id)
        if not terminus:
            continue

        bus_lat = bus.get("lat")
        bus_lon = bus.get("lng", bus.get("lon"))
        bus_id  = bus.get("trip_id", bus.get("bus_id", "unknown"))

        if not bus_lat or not bus_lon:
            continue

        # Find next stop for granular ETA
        next_stop = _find_next_stop(bus_lat, bus_lon, route_id)

        try:
            # ETA to next stop
            next_stop_eta = None
            if next_stop:
                ns_result = await calculate_eta_for_bus(
                    bus_id=bus_id,
                    bus_lat=bus_lat,
                    bus_lon=bus_lon,
                    dst_lat=next_stop["lat"],
                    dst_lon=next_stop["lon"],
                    dst_label=next_stop["label"],
                    api_key=api_key,
                )
                next_stop_eta = ns_result.to_dict()

            # ETA to terminus
            terminus_result = await calculate_eta_for_bus(
                bus_id=bus_id,
                bus_lat=bus_lat,
                bus_lon=bus_lon,
                dst_lat=terminus["lat"],
                dst_lon=terminus["lon"],
                dst_label=terminus["label"],
                api_key=api_key,
            )

            t_dict     = terminus_result.to_dict()
            t_min      = t_dict.get("best_eta_minutes") or 0
            t_tomtom   = bool(terminus_result.eta_live_seconds)
            t_conf     = compute_confidence(
                method_used    = terminus_result.method_used,
                is_ghost       = bool(bus.get("is_ghost", False)),
                tomtom_applied = t_tomtom,
                eta_minutes    = t_min,
            )

            results.append({
                "bus_id":        bus_id,
                "route_id":      route_id,
                "current_lat":   bus_lat,
                "current_lon":   bus_lon,
                "speed_kmph":    bus.get("speed", 0),
                "passenger_count": bus.get("passenger_count", 0),
                "is_ghost":      bus.get("is_ghost", False),
                "next_stop":     next_stop_eta,
                "terminus":      t_dict,
                "eta_minutes":          t_min,
                "eta_corrected_minutes": t_min,
                "confidence_pct":        t_conf["confidence_pct"],
                "confidence_label":      t_conf["confidence_label"],
                "model_used":            _model_used_label(terminus_result.method_used, t_tomtom),
                "tomtom_applied":        t_tomtom,
            })

        except Exception as e:
            logger.warning(f"ETA failed for bus {bus_id}: {e}")
            results.append({
                "bus_id": bus_id,
                "route_id": route_id,
                "error": str(e),
            })

    return {
        "status":       "ok",
        "count":        len(results),
        "etas":         results,
        "computed_at":  datetime.now().isoformat(),
        "traffic_source": "TomTom Live Traffic",
    }


@router.get("/eta/bus/{bus_id}")
async def get_bus_eta(
    bus_id: str,
    dst: Optional[str] = Query(None, description="Custom destination (text or lat,lon)"),
):
    """
    Calculate live ETA for a specific bus.
    If no dst is given, uses the route terminus as destination.
    """
    from traffic.eta_engine import calculate_eta_for_bus, calculate_eta
    from infrastructure import async_redis

    bus = await async_redis.get_bus_state(bus_id)
    if not bus:
        raise HTTPException(status_code=404, detail=f"Bus {bus_id} not found")

    bus_lat = bus.get("lat")
    bus_lon = bus.get("lng", bus.get("lon"))
    route_id = bus.get("route_id", bus.get("route", ""))

    if not bus_lat or not bus_lon:
        raise HTTPException(status_code=422, detail="Bus has no GPS position")

    api_key = _get_api_key()

    # Resolve destination
    if dst:
        result = await calculate_eta(
            src=(bus_lat, bus_lon),
            dst=dst.strip(),
            api_key=api_key,
        )
    else:
        terminus = _ROUTE_TERMINI.get(route_id, {
            "lat": 13.0827, "lon": 80.2707, "label": "Broadway Bus Stand"
        })
        result = await calculate_eta_for_bus(
            bus_id=bus_id,
            bus_lat=bus_lat,
            bus_lon=bus_lon,
            dst_lat=terminus["lat"],
            dst_lon=terminus["lon"],
            dst_label=terminus["label"],
            api_key=api_key,
        )

    tomtom_ok = bool(result.eta_live_seconds)
    conf = compute_confidence(
        method_used    = result.method_used,
        is_ghost       = bool(bus.get("is_ghost", False)),
        tomtom_applied = tomtom_ok,
        eta_minutes    = result.best_eta_minutes() or 0,
    )

    return {
        "status":     "ok",
        "bus_id":     bus_id,
        "bus_info":   bus,
        "eta":        result.to_dict(),
        "eta_minutes":          result.best_eta_minutes(),
        "eta_corrected_minutes": result.best_eta_minutes(),
        "confidence_pct":  conf["confidence_pct"],
        "confidence_label": conf["confidence_label"],
        "model_used":      _model_used_label(result.method_used, tomtom_ok),
        "tomtom_applied":  tomtom_ok,
        "computed_at":     datetime.now().isoformat(),
    }
