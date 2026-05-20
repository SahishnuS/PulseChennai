"""
ETA Engine — Pulse-Chennai
==========================
Calculates Estimated Time of Arrival between two points using
multiple methods in priority order:

  0. **ML Ensemble** (XGB+LGB on uber_data features + TomTom traffic)
  1. TomTom Routing API (live traffic, most accurate)
  2. TomTom Geocode + Routing (when text addresses are given)
  3. Haversine + Traffic Flow Multiplier (fast, offline fallback)
  4. Historical time-of-day pattern (pure offline fallback)

Usage:
    result = await calculate_eta(
        src="Koyambedu Bus Stand",
        dst="T. Nagar Bus Terminus",
        api_key="YOUR_TOMTOM_KEY"
    )
    # or with coordinates:
    result = await calculate_eta(
        src=(13.0694, 80.1948),
        dst=(13.0338, 80.2326),
        api_key="YOUR_TOMTOM_KEY"
    )
"""

import math
import logging
import asyncio
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ── TomTom API endpoints ──────────────────────────────────────────────────────
_ROUTING_BASE   = "https://api.tomtom.com/routing/1/calculateRoute"
_GEOCODE_BASE   = "https://api.tomtom.com/search/2/geocode"
_SEARCH_BASE    = "https://api.tomtom.com/search/2/search"

# Chennai bounding box for geocoding bias
_CHENNAI_LAT, _CHENNAI_LON = 13.0827, 80.2707


# ── Result dataclass ──────────────────────────────────────────────────────────
@dataclass
class ETAResult:
    source_label:        str          # Human-readable source name
    dest_label:          str          # Human-readable destination name
    src_lat:             float
    src_lon:             float
    dst_lat:             float
    dst_lon:             float
    eta_live_seconds:    Optional[int]   # Live traffic ETA (TomTom best)
    eta_historic_seconds:Optional[int]   # Historic traffic ETA
    eta_no_traffic_seconds: Optional[int]  # Free-flow ETA
    eta_fallback_seconds: Optional[int]  # Haversine+flow fallback
    distance_meters:     Optional[int]   # Route distance
    method_used:         str             # Which method succeeded
    traffic_delay_seconds: Optional[int] # live - no_traffic
    confidence:          float           # 0.0–1.0
    timestamp:           str
    source_data:         str             # API label for UI
    # ── ML prediction fields (added for Method 0) ─────────────────────────────
    ml_prediction_seconds: Optional[float] = None    # ML ensemble raw ETA
    ml_confidence:         Optional[float] = None    # ML model confidence 0-1
    ml_method:             Optional[str]   = None    # Which ML path was used
    ml_traffic_factor:     Optional[float] = None    # Real-time traffic multiplier

    def eta_live_minutes(self) -> Optional[float]:
        return round(self.eta_live_seconds / 60, 1) if self.eta_live_seconds else None

    def eta_historic_minutes(self) -> Optional[float]:
        return round(self.eta_historic_seconds / 60, 1) if self.eta_historic_seconds else None

    def eta_no_traffic_minutes(self) -> Optional[float]:
        return round(self.eta_no_traffic_seconds / 60, 1) if self.eta_no_traffic_seconds else None

    def ml_prediction_minutes(self) -> Optional[float]:
        """ML ensemble prediction in minutes."""
        return round(self.ml_prediction_seconds / 60, 1) if self.ml_prediction_seconds else None

    def best_eta_minutes(self) -> Optional[float]:
        """Returns the most accurate ETA in minutes (ML > live > historic > fallback)."""
        s = (self.ml_prediction_seconds or self.eta_live_seconds
             or self.eta_historic_seconds or self.eta_fallback_seconds)
        if s is not None:
            return round(float(s) / 60, 1)
        return None

    def arrival_time(self) -> Optional[str]:
        secs = (self.ml_prediction_seconds or self.eta_live_seconds
                or self.eta_fallback_seconds)
        if secs:
            arrival = datetime.now() + timedelta(seconds=float(secs))
            return arrival.strftime("%H:%M")
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["eta_live_minutes"]       = self.eta_live_minutes()
        d["eta_historic_minutes"]   = self.eta_historic_minutes()
        d["eta_no_traffic_minutes"] = self.eta_no_traffic_minutes()
        d["ml_prediction_minutes"]  = self.ml_prediction_minutes()
        d["best_eta_minutes"]       = self.best_eta_minutes()
        d["arrival_time"]           = self.arrival_time()
        d["distance_km"]            = round(self.distance_meters / 1000, 2) if self.distance_meters else None
        d["traffic_delay_minutes"]  = (
            round(self.traffic_delay_seconds / 60, 1) if self.traffic_delay_seconds else None
        )
        return d


# ── Public API ────────────────────────────────────────────────────────────────
async def calculate_eta(
    src: Union[str, Tuple[float, float]],
    dst: Union[str, Tuple[float, float]],
    api_key: Optional[str] = None,
) -> ETAResult:
    """
    Top-level ETA calculation function.

    Parameters
    ----------
    src : str or (lat, lon)
        Source location — text address or coordinate tuple.
    dst : str or (lat, lon)
        Destination — text address or coordinate tuple.
    api_key : str, optional
        TomTom API key. Falls back to env var VITE_TOMTOM_API_KEY.
    """
    import os
    key = api_key or os.getenv("VITE_TOMTOM_API_KEY", "")

    # ── Resolve coordinates (geocode if text) ─────────────────────────────────
    src_lat, src_lon, src_label = await _resolve(src, key)
    dst_lat, dst_lon, dst_label = await _resolve(dst, key)

    # ── ML prediction (populated on all results when available) ───────────────
    ml_pred_seconds: Optional[float] = None
    ml_confidence:   Optional[float] = None
    ml_method:       Optional[str]   = None
    ml_traffic_factor: Optional[float] = None

    # ── Method 0: ML Ensemble (highest priority) ─────────────────────────────
    if src_lat and dst_lat:
        try:
            ml_result = await _ml_ensemble_eta(
                src_lat, src_lon, dst_lat, dst_lon,
                src_label, dst_label, key,
            )
            if ml_result:
                # Populate ML fields for enriching all downstream results too
                ml_pred_seconds = ml_result.ml_prediction_seconds
                ml_confidence   = ml_result.ml_confidence
                ml_method       = ml_result.ml_method
                ml_traffic_factor = ml_result.ml_traffic_factor
                return ml_result
        except Exception as e:
            logger.warning(f"ML Ensemble ETA failed: {e}. Falling to TomTom.")

    # ── Method 1: TomTom Routing API (live traffic) ───────────────────────────
    if key and src_lat and dst_lat:
        try:
            result = await _tomtom_route_eta(
                src_lat, src_lon, dst_lat, dst_lon,
                src_label, dst_label, key
            )
            if result:
                # Attach any ML prediction we computed before failure
                result.ml_prediction_seconds = ml_pred_seconds
                result.ml_confidence = ml_confidence
                result.ml_method = ml_method
                result.ml_traffic_factor = ml_traffic_factor
                return result
        except Exception as e:
            logger.warning(f"TomTom Routing API failed: {e}. Falling back.")

    # ── Method 2: Haversine + TomTom Flow Multiplier ──────────────────────────
    if src_lat and dst_lat:
        try:
            result = await _haversine_flow_eta(src_lat, src_lon, dst_lat, dst_lon, src_label, dst_label)
            result.ml_prediction_seconds = ml_pred_seconds
            result.ml_confidence = ml_confidence
            result.ml_method = ml_method
            result.ml_traffic_factor = ml_traffic_factor
            return result
        except Exception as e:
            logger.warning(f"Haversine fallback failed: {e}")

    # ── Method 3: Pure historical pattern (last resort) ───────────────────────
    result = _historical_eta(src_lat or 0, src_lon or 0, dst_lat or 0, dst_lon or 0, src_label, dst_label)
    result.ml_prediction_seconds = ml_pred_seconds
    result.ml_confidence = ml_confidence
    result.ml_method = ml_method
    result.ml_traffic_factor = ml_traffic_factor
    return result


async def calculate_eta_for_bus(
    bus_id: str,
    bus_lat: float,
    bus_lon: float,
    dst_lat: float,
    dst_lon: float,
    dst_label: str = "Next Stop",
    api_key: Optional[str] = None,
) -> ETAResult:
    """
    Convenience function for per-bus ETA calculation.
    Uses bus's current GPS position as source.
    """
    return await calculate_eta(
        src=(bus_lat, bus_lon),
        dst=(dst_lat, dst_lon),
        api_key=api_key,
    )


# ── ML Ensemble helper ────────────────────────────────────────────────────────

async def _ml_ensemble_eta(
    src_lat: float, src_lon: float,
    dst_lat: float, dst_lon: float,
    src_label: str, dst_label: str,
    api_key: str,
) -> Optional[ETAResult]:
    """
    Method 0: ML Ensemble prediction using pre-trained XGB+LGB models.

    Runs the prediction in a thread pool to avoid blocking the event loop
    (model inference + historical data lookups are CPU-bound).
    """
    import asyncio
    from traffic.ml_eta_predictor import get_predictor

    predictor = get_predictor()

    # Run CPU-bound ML prediction in a thread pool
    loop = asyncio.get_event_loop()
    ml_result = await loop.run_in_executor(
        None,
        lambda: predictor.predict(
            src_lat=src_lat,
            src_lon=src_lon,
            dst_lat=dst_lat,
            dst_lon=dst_lon,
        ),
    )

    if not ml_result or ml_result.get("confidence", 0) < 0.4:
        logger.info("ML prediction confidence too low (%.2f), skipping.",
                    ml_result.get("confidence", 0) if ml_result else 0)
        return None

    eta_s = ml_result["eta_seconds"]
    distance_km = ml_result.get("distance_km", 0)
    distance_m = int(distance_km * 1000 * 1.35) if distance_km else None  # road correction

    return ETAResult(
        source_label          = src_label,
        dest_label            = dst_label,
        src_lat               = src_lat,
        src_lon               = src_lon,
        dst_lat               = dst_lat,
        dst_lon               = dst_lon,
        eta_live_seconds      = None,
        eta_historic_seconds  = (
            int(ml_result["historical_eta_seconds"])
            if ml_result.get("historical_eta_seconds") else None
        ),
        eta_no_traffic_seconds= None,
        eta_fallback_seconds  = int(eta_s),
        distance_meters       = distance_m,
        method_used           = ml_result["method"],
        traffic_delay_seconds = None,
        confidence            = ml_result["confidence"],
        timestamp             = datetime.now().isoformat(),
        source_data           = "ML Ensemble (XGB+LGB+uber_data+TomTom)",
        # ML-specific fields
        ml_prediction_seconds = round(eta_s, 1),
        ml_confidence         = round(ml_result["confidence"], 3),
        ml_method             = ml_result["method"],
        ml_traffic_factor     = ml_result.get("traffic_factor"),
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _resolve(
    location: Union[str, Tuple[float, float]],
    api_key: str,
) -> Tuple[Optional[float], Optional[float], str]:
    """
    Resolve a location to (lat, lon, label).
    If it's already coordinates, return as-is.
    If it's a string, geocode it via TomTom Search API.
    """
    if isinstance(location, (list, tuple)) and len(location) == 2:
        lat, lon = float(location[0]), float(location[1])
        return lat, lon, f"{lat:.4f},{lon:.4f}"

    if isinstance(location, str):
        # Try TomTom fuzzy search (free text)
        if api_key:
            coords = await _geocode_text(location, api_key)
            if coords:
                lat, lon = coords
                return lat, lon, location
        # Fallback: try parsing "lat,lon" string format
        try:
            parts = location.split(",")
            if len(parts) == 2:
                return float(parts[0].strip()), float(parts[1].strip()), location
        except ValueError:
            pass

    return None, None, str(location)


async def _geocode_text(query: str, api_key: str) -> Optional[Tuple[float, float]]:
    """Use TomTom Fuzzy Search API to geocode a text location near Chennai."""
    try:
        import httpx
        url = f"{_SEARCH_BASE}/{query}.json"
        params = {
            "key": api_key,
            "limit": 1,
            "countrySet": "IN",
            "lat": _CHENNAI_LAT,
            "lon": _CHENNAI_LON,
            "radius": 50000,   # 50km radius bias around Chennai
            "language": "en-GB",
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            if results:
                pos = results[0]["position"]
                return pos["lat"], pos["lon"]
    except Exception as e:
        logger.warning(f"Geocoding failed for '{query}': {e}")
    return None


async def _tomtom_route_eta(
    src_lat: float, src_lon: float,
    dst_lat: float, dst_lon: float,
    src_label: str, dst_label: str,
    api_key: str,
) -> Optional[ETAResult]:
    """
    Call TomTom Routing API to get a live traffic-aware ETA.

    Returns all three ETA flavours:
      - travelTimeInSeconds             (live traffic)
      - historicTrafficTravelTimeInSeconds
      - noTrafficTravelTimeInSeconds    (free flow)
    """
    import httpx

    route_path = f"{src_lat},{src_lon}:{dst_lat},{dst_lon}"
    url = f"{_ROUTING_BASE}/{route_path}/json"

    params = {
        "key":                  api_key,
        "traffic":              "true",
        "travelMode":           "car",
        "computeTravelTimeFor": "all",   # returns all 3 ETA flavours
        "routeType":            "fastest",
        "avoid":                "unpavedRoads",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)

        if resp.status_code == 403:
            logger.warning("TomTom Routing API: 403 Forbidden (check API key or plan)")
            return None
        if resp.status_code == 429:
            logger.warning("TomTom Routing API: rate limit hit")
            return None

        resp.raise_for_status()
        data = resp.json()

    routes = data.get("routes", [])
    if not routes:
        logger.warning("TomTom Routing API: no routes returned")
        return None

    summary = routes[0].get("summary", {})

    live_s      = summary.get("travelTimeInSeconds")
    historic_s  = summary.get("historicTrafficTravelTimeInSeconds")
    no_traffic_s= summary.get("noTrafficTravelTimeInSeconds")
    dist_m      = summary.get("lengthInMeters")

    delay_s = (live_s - no_traffic_s) if live_s and no_traffic_s else None

    return ETAResult(
        source_label          = src_label,
        dest_label            = dst_label,
        src_lat               = src_lat,
        src_lon               = src_lon,
        dst_lat               = dst_lat,
        dst_lon               = dst_lon,
        eta_live_seconds      = live_s,
        eta_historic_seconds  = historic_s,
        eta_no_traffic_seconds= no_traffic_s,
        eta_fallback_seconds  = None,
        distance_meters       = dist_m,
        method_used           = "TomTom Routing API (Live Traffic)",
        traffic_delay_seconds = delay_s,
        confidence            = 0.95,
        timestamp             = datetime.now().isoformat(),
        source_data           = "TomTom Routing API v1",
    )


async def _haversine_flow_eta(
    src_lat: float, src_lon: float,
    dst_lat: float, dst_lon: float,
    src_label: str, dst_label: str,
) -> ETAResult:
    """
    Fallback ETA using:
    1. Haversine straight-line distance (×1.35 road correction factor for Chennai)
    2. Average speed from TomTom Flow Segment snapshots (nearest segment)
    3. Free-flow speed (52 km/h) as baseline
    """
    from traffic import tomtom_client

    # Haversine distance
    dist_m = _haversine_meters(src_lat, src_lon, dst_lat, dst_lon)
    road_dist_m = dist_m * 1.35   # Chennai urban road correction

    # Get current speed from nearest flow segment
    snapshots = tomtom_client.get_latest_snapshots()
    current_speed_kmph, free_flow_kmph = _nearest_segment_speeds(
        src_lat, src_lon, dst_lat, dst_lon, snapshots
    )

    # Calculate ETAs
    free_flow_s = int((road_dist_m / 1000) / free_flow_kmph * 3600)
    if current_speed_kmph > 0:
        live_s = int((road_dist_m / 1000) / current_speed_kmph * 3600)
        delay_s = max(0, live_s - free_flow_s)
    else:
        live_s = None
        delay_s = None

    return ETAResult(
        source_label          = src_label,
        dest_label            = dst_label,
        src_lat               = src_lat,
        src_lon               = src_lon,
        dst_lat               = dst_lat,
        dst_lon               = dst_lon,
        eta_live_seconds      = None,
        eta_historic_seconds  = None,
        eta_no_traffic_seconds= free_flow_s,
        eta_fallback_seconds  = live_s,
        distance_meters       = int(road_dist_m),
        method_used           = "Haversine + TomTom Flow Segment",
        traffic_delay_seconds = delay_s,
        confidence            = 0.72,
        timestamp             = datetime.now().isoformat(),
        source_data           = "TomTom Traffic Flow API (segment speed)",
    )


def _historical_eta(
    src_lat: float, src_lon: float,
    dst_lat: float, dst_lon: float,
    src_label: str, dst_label: str,
) -> ETAResult:
    """
    Last-resort fallback based purely on time-of-day speed profiles.
    No external API calls needed.
    """
    dist_m = _haversine_meters(src_lat, src_lon, dst_lat, dst_lon)
    road_dist_m = dist_m * 1.35

    hour = datetime.now().hour
    if 8 <= hour <= 10 or 17 <= hour <= 20:
        avg_speed_kmph = 15   # Heavy traffic
    elif 12 <= hour <= 14:
        avg_speed_kmph = 28   # Midday moderate
    elif 22 <= hour or hour <= 5:
        avg_speed_kmph = 50   # Late night
    else:
        avg_speed_kmph = 38   # Normal flow

    eta_s = int((road_dist_m / 1000) / avg_speed_kmph * 3600)

    return ETAResult(
        source_label          = src_label,
        dest_label            = dst_label,
        src_lat               = src_lat,
        src_lon               = src_lon,
        dst_lat               = dst_lat,
        dst_lon               = dst_lon,
        eta_live_seconds      = None,
        eta_historic_seconds  = eta_s,
        eta_no_traffic_seconds= None,
        eta_fallback_seconds  = eta_s,
        distance_meters       = int(road_dist_m),
        method_used           = "Historical Time-of-Day Pattern",
        traffic_delay_seconds = None,
        confidence            = 0.55,
        timestamp             = datetime.now().isoformat(),
        source_data           = "Synthetic (no API key)",
    )


# ── Math helpers ──────────────────────────────────────────────────────────────

def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance between two GPS coordinates in metres."""
    R = 6_371_000  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _nearest_segment_speeds(
    src_lat: float, src_lon: float,
    dst_lat: float, dst_lon: float,
    snapshots: dict,
) -> Tuple[float, float]:
    """
    Find the nearest TomTom flow segment to the midpoint of the route.
    Returns (current_speed_kmph, free_flow_speed_kmph).
    """
    if not snapshots:
        return 35.0, 52.0  # default fallback

    mid_lat = (src_lat + dst_lat) / 2
    mid_lon = (src_lon + dst_lon) / 2

    best_dist = float("inf")
    best_snap = None
    for snap in snapshots.values():
        d = _haversine_meters(mid_lat, mid_lon, snap.lat, snap.lon)
        if d < best_dist:
            best_dist = d
            best_snap = snap

    if best_snap:
        return best_snap.current_speed_kmph, best_snap.free_flow_speed_kmph
    return 35.0, 52.0
