"""
Route Deviation Detector — Pulse-Chennai
=========================================
Detects when a bus has drifted off its assigned route polyline,
tracks consecutive deviations, and broadcasts ROUTE_DEVIATION events
via the WebSocket broadcast channel.

Public API:
  check_deviation(bus_id, current_pos, route_polyline) -> dict
  record_tick(bus_id, deviated)                        -> int (consecutive count)
  get_next_available_stop(deviated_bus_id, all_buses)  -> str | None
  maybe_alert(bus_id, route, deviation_result, stop_names, all_buses) -> None
"""

import math
import asyncio
import logging
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────
DEVIATION_THRESHOLD_M   = 250   # metres off-route before flagging
CONSECUTIVE_TICKS_ALERT = 3     # ticks before broadcasting
TICK_INTERVAL_S         = 15    # simulator tick (seconds)
DEVIATION_TTL_S         = 300   # Redis key TTL (5 min)

# ─── In-memory consecutive-tick counters ─────────────────────────────────────
_consecutive_deviation: dict[str, int] = defaultdict(int)
_alerted_buses: set[str] = set()   # buses that already triggered an alert this window


# ─── Maths ───────────────────────────────────────────────────────────────────

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance between two GPS points in metres."""
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a  = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─── Core deviation check ─────────────────────────────────────────────────────

def check_deviation(
    bus_id: str,
    current_pos: tuple,           # (lat, lng)
    route_polyline: list[tuple],  # [(lat, lng), ...]
) -> dict:
    """
    Compute minimum Haversine distance from current_pos to any point on
    route_polyline.

    Returns:
      {
        "deviated":           bool,
        "distance_m":         float,
        "nearest_route_point": (lat, lng),
      }
    """
    if not route_polyline:
        return {"deviated": False, "distance_m": 0.0, "nearest_route_point": current_pos}

    lat, lng = current_pos
    best_dist = float("inf")
    best_pt   = route_polyline[0]

    for pt in route_polyline:
        d = _haversine_m(lat, lng, pt[0], pt[1])
        if d < best_dist:
            best_dist = d
            best_pt   = pt

    deviated = best_dist > DEVIATION_THRESHOLD_M

    return {
        "deviated":            deviated,
        "distance_m":          round(best_dist, 1),
        "nearest_route_point": best_pt,
    }


# ─── Consecutive-tick tracker ─────────────────────────────────────────────────

def record_tick(bus_id: str, deviated: bool) -> int:
    """
    Update the consecutive deviation counter for a bus.
    Returns the current consecutive count.
    """
    if deviated:
        _consecutive_deviation[bus_id] += 1
    else:
        _consecutive_deviation[bus_id] = 0
        _alerted_buses.discard(bus_id)  # Reset alert window when back on route
    return _consecutive_deviation[bus_id]


# ─── Next-available-stop finder ───────────────────────────────────────────────

def get_next_available_stop(
    deviated_bus_id: str,
    all_buses_on_route: list[dict],
) -> Optional[str]:
    """
    Returns the stop name of the next non-deviated bus on the same route,
    or None if there is no alternative.

    all_buses_on_route: list of bus dicts with keys "id", "next_stop_name".
    """
    for bus in all_buses_on_route:
        if bus.get("id") == deviated_bus_id:
            continue
        if not bus.get("is_deviated", False):
            stop = bus.get("next_stop_name")
            if stop:
                return stop
    return None


# ─── Alert broadcaster ────────────────────────────────────────────────────────

async def maybe_alert(
    bus_id: str,
    route: str,
    deviation_result: dict,
    stop_names: list[str],          # stops ahead that may be skipped
    all_buses_on_route: list[dict], # for get_next_available_stop
) -> None:
    """
    If the bus has deviated for >= CONSECUTIVE_TICKS_ALERT ticks and hasn't
    already fired an alert this window:
      1. Set Redis flag "deviation:{bus_id}" with TTL 300s
      2. Broadcast ROUTE_DEVIATION event via WebSocket
    """
    count = _consecutive_deviation.get(bus_id, 0)
    if count < CONSECUTIVE_TICKS_ALERT:
        return
    if bus_id in _alerted_buses:
        return

    _alerted_buses.add(bus_id)

    # ── 1. Set Redis flag ──────────────────────────────────────────────────
    try:
        from infrastructure import upstash_redis
        await upstash_redis.set(f"deviation:{bus_id}", "1", ex=DEVIATION_TTL_S)
        logger.info(f"Deviation flag set in Redis for {bus_id}")
    except Exception as e:
        logger.warning(f"Could not set Redis deviation flag: {e}")

    # ── 2. Build the event payload ─────────────────────────────────────────
    next_stop = get_next_available_stop(bus_id, all_buses_on_route)
    affected  = stop_names or []
    stops_str = ", ".join(affected) if affected else "upcoming stops"

    message = (
        f"{bus_id} has deviated from Route {route}. "
        f"Passengers at stops [{stops_str}] may need to board at the next available stop."
    )

    event = {
        "type":              "ROUTE_DEVIATION",
        "bus_id":            bus_id,
        "route":             route,
        "affected_stops":    affected,
        "next_available_stop": next_stop,
        "distance_m":        deviation_result["distance_m"],
        "message":           message,
    }

    # ── 3. Broadcast via WebSocket ─────────────────────────────────────────
    try:
        from api.websocket import broadcast
        await broadcast(event)
        logger.info(f"ROUTE_DEVIATION broadcast for {bus_id} ({deviation_result['distance_m']}m off-route)")
    except Exception as e:
        logger.warning(f"WebSocket broadcast failed for deviation event: {e}")
