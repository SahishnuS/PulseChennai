"""
Road-Snapped Polyline Service
==============================
Fetches road-following geometry for MTC bus routes using the public
OSRM routing API and caches results in Upstash Redis.

Functions
---------
get_road_snapped_polyline(stop_coords)  — single-route OSRM fetch
get_all_route_polylines()              — all 3 routes with cache
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── OSRM public endpoint ────────────────────────────────────────────────────
OSRM_BASE = "http://router.project-osrm.org/route/v1/driving"
OSRM_TIMEOUT_S = 5.0

# ── Upstash cache TTL (24 hours) ────────────────────────────────────────────
POLYLINE_TTL = 86_400  # seconds

# ── Hardcoded stop coordinates (lat, lng) for routes 19, 102X, 515 ─────────
# These mirror the seed_stops.py route data; OSRM will snap them to roads.
ROUTE_STOP_COORDS: dict[str, list[tuple[float, float]]] = {
    "19": [
        (13.0827, 80.2756),   # Chennai Central
        (13.0792, 80.2731),   # Park Town
        (13.0614, 80.2564),   # Nungambakkam
        (13.0418, 80.2341),   # T Nagar
        (13.0182, 80.2213),   # Saidapet
        (12.9986, 80.2369),   # Kotturpuram
        (12.9901, 80.2378),   # Indra Nagar
        (12.9836, 80.2463),   # Gandhi Nagar
        (12.9831, 80.2541),   # Lattice Bridge
        (12.9824, 80.2588),   # Thiruvanmiyur
    ],
    "102X": [
        (13.0827, 80.2756),   # Chennai Central
        (13.0778, 80.2023),   # Thirumangalam
        (13.0722, 80.1963),   # Koyambedu CMBT
        (13.0698, 80.1944),   # Koyambedu Market
        (13.0365, 80.2129),   # Mambalam
        (13.0182, 80.2213),   # Saidapet
        (12.9516, 80.1430),   # Chrompet
        (12.9249, 80.1000),   # Tambaram
    ],
    "515": [
        (13.0891, 80.2101),   # Anna Nagar Tower
        (13.0842, 80.2089),   # 15th Main Road
        (13.0778, 80.2023),   # Thirumangalam
        (13.0722, 80.1963),   # Koyambedu CMBT
        (13.0418, 80.2341),   # T Nagar
        (12.9986, 80.2369),   # Kotturpuram
        (12.9824, 80.2588),   # Thiruvanmiyur
    ],
    "21C": [
        (13.0694, 80.1948),   # Koyambedu CMBT
        (13.0526, 80.2104),   # Vadapalani
        (13.0354, 80.2124),   # Ashok Pillar
        (13.0084, 80.2131),   # Guindy
        (13.0063, 80.2443),   # Madhya Kailash
        (13.0012, 80.2565),   # Adyar Depot
        (12.9953, 80.2538),   # Adyar
    ],
    "70": [
        (13.0827, 80.2756),   # Chennai Central
        (13.1082, 80.2467),   # Perambur
        (13.1030, 80.2039),   # Villivakkam
        (13.1091, 80.1700),   # Dunlop
        (13.1017, 80.1611),   # Ambattur
    ],
    "47A": [
        (13.0418, 80.2341),   # T Nagar Bus Terminus
        (13.0182, 80.2213),   # Saidapet
        (13.0084, 80.2131),   # Guindy
        (12.9868, 80.1762),   # Meenambakkam
        (12.9675, 80.1491),   # Pallavaram
        (12.9560, 80.1435),   # Chromepet
    ],
}


# ── Straight-line fallback ──────────────────────────────────────────────────

def _straight_line_coords(
    stop_coords: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Return the stop coordinates unchanged (straight-line fallback)."""
    return list(stop_coords)


# ── Core OSRM fetch ─────────────────────────────────────────────────────────

async def get_road_snapped_polyline(
    stop_coords: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """
    Fetch a road-snapped polyline from the public OSRM API.

    Parameters
    ----------
    stop_coords:
        Ordered list of ``(lat, lng)`` tuples representing the bus stops.

    Returns
    -------
    list[tuple[float, float]]
        Road-snapped ``(lat, lng)`` pairs. Falls back to straight-line
        if OSRM is unreachable or returns an error.
    """
    if len(stop_coords) < 2:
        return _straight_line_coords(stop_coords)

    # OSRM coordinate string uses lng,lat order separated by semicolons
    coord_str = ";".join(f"{lng},{lat}" for lat, lng in stop_coords)
    url = f"{OSRM_BASE}/{coord_str}"
    params = {"overview": "full", "geometries": "geojson"}

    try:
        async with httpx.AsyncClient(timeout=OSRM_TIMEOUT_S) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()

        # Parse GeoJSON geometry: [[lng, lat], ...]
        raw_coords: list[list[float]] = (
            payload["routes"][0]["geometry"]["coordinates"]
        )
        # Convert to (lat, lng) tuples
        return [(pt[1], pt[0]) for pt in raw_coords]

    except httpx.TimeoutException:
        logger.warning(
            "OSRM request timed out after %.1fs — using straight-line fallback",
            OSRM_TIMEOUT_S,
        )
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "OSRM HTTP error %s — using straight-line fallback",
            exc.response.status_code,
        )
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning(
            "OSRM response parse error (%s) — using straight-line fallback",
            exc,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "OSRM unexpected error (%s) — using straight-line fallback",
            exc,
        )

    return _straight_line_coords(stop_coords)


# ── Aggregate fetch with Upstash cache ──────────────────────────────────────

async def get_all_route_polylines() -> dict[str, list[tuple[float, float]]]:
    """
    Return road-snapped polylines for routes 19, 102X, and 515.

    Each route's result is cached in Upstash Redis under the key
    ``polyline:{route_id}`` with a 24-hour TTL.  A cache miss triggers
    a live OSRM fetch which is then stored before returning.

    Returns
    -------
    dict
        ``{ "19": [(lat, lng), ...], "102X": [...], "515": [...] }``
    """
    from infrastructure import upstash_redis  # lazy import keeps module testable

    result: dict[str, list[tuple[float, float]]] = {}

    for route_id, stops in ROUTE_STOP_COORDS.items():
        cache_key = f"polyline:{route_id}"

        # ── 1. Try cache ──────────────────────────────────────────────────
        cached = await upstash_redis.get_json(cache_key)
        if cached is not None:
            logger.debug("Cache HIT for %s", cache_key)
            # Stored as list-of-lists; convert to list-of-tuples
            result[route_id] = [tuple(pt) for pt in cached]
            continue

        # ── 2. Cache miss — call OSRM ─────────────────────────────────────
        logger.info("Cache MISS for %s — fetching from OSRM", cache_key)
        polyline = await get_road_snapped_polyline(stops)

        # ── 3. Store in Upstash (serialize tuples → lists for JSON) ───────
        serialisable = [list(pt) for pt in polyline]
        stored = await upstash_redis.set_json(cache_key, serialisable, ex=POLYLINE_TTL)
        if stored:
            logger.info(
                "Cached %d points for route %s (TTL=%ds)",
                len(polyline),
                route_id,
                POLYLINE_TTL,
            )
        else:
            logger.warning("Failed to cache polyline for route %s", route_id)

        result[route_id] = polyline

    return result
