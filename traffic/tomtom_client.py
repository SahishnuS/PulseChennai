"""
TomTom Traffic Client (Async)
==============================
httpx-based async client for TomTom's Traffic Flow Segment API.
Fetches real-time speed data for key Chennai road segments.
Caches responses in Redis. Falls back to time-of-day synthetic data.
Runs a background refresh loop every TOMTOM_REFRESH_INTERVAL seconds.
"""

import logging
import asyncio
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

CHENNAI_SEGMENTS = {
    "anna_salai_gemini":    (13.0569, 80.2497),
    "kathipara_junction":   (13.0107, 80.2145),
    "koyambedu":            (13.0694, 80.1948),
    "omr_sholinganallur":   (12.9010, 80.2279),
    "guindy_junction":      (13.0067, 80.2206),
    "tambaram":             (12.9249, 80.1000),
    "velachery":            (12.9786, 80.2209),
    "madhya_kailash":       (12.9883, 80.2480),
}

BASE_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"


@dataclass
class TrafficSnapshot:
    segment_label: str
    lat: float
    lon: float
    current_speed_kmph: float
    free_flow_speed_kmph: float
    gridlock_ratio: float
    confidence: float
    road_closure: bool
    captured_at: str


_http_client = None
_api_key: Optional[str] = None
_refresh_task: Optional[asyncio.Task] = None
_latest_snapshots: dict[str, TrafficSnapshot] = {}


async def init(api_key: Optional[str] = None):
    """Initialize the httpx async client."""
    global _http_client, _api_key
    _api_key = api_key
    try:
        import httpx
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(5.0))
        if api_key:
            logger.info("TomTom client initialized with API key.")
        else:
            logger.info("TomTom client initialized (synthetic mode — no API key).")
    except ImportError:
        logger.warning("httpx not installed. TomTom client in stub mode.")


async def close():
    """Shut down the httpx client and stop the refresh loop."""
    global _http_client, _refresh_task
    if _refresh_task:
        _refresh_task.cancel()
        try:
            await _refresh_task
        except asyncio.CancelledError:
            pass
        _refresh_task = None
    if _http_client:
        await _http_client.aclose()
        _http_client = None


async def get_flow_segment(segment_label: str, lat: float, lon: float) -> TrafficSnapshot:
    """Fetch real-time traffic for a single road segment from TomTom API.

    Falls back to cached Redis value on error, then to synthetic data.
    """
    from infrastructure import async_redis

    # Try real API
    if _http_client and _api_key:
        try:
            params = {
                "key": _api_key,
                "point": f"{lat},{lon}",
                "unit": "KMPH",
            }
            resp = await _http_client.get(BASE_URL, params=params)

            if resp.status_code == 429:
                logger.warning("TomTom rate limit hit. Using cache.")
                cached = await async_redis.get_tomtom_cache(segment_label)
                if cached:
                    return TrafficSnapshot(**cached)
                return _synthetic_snapshot(segment_label, lat, lon)

            resp.raise_for_status()
            data = resp.json()
            flow = data.get("flowSegmentData", {})

            current_speed = flow.get("currentSpeed", 0)
            free_flow = flow.get("freeFlowSpeed", 52)
            gridlock = current_speed / free_flow if free_flow > 0 else 0

            snap = TrafficSnapshot(
                segment_label=segment_label,
                lat=lat,
                lon=lon,
                current_speed_kmph=current_speed,
                free_flow_speed_kmph=free_flow,
                gridlock_ratio=round(gridlock, 3),
                confidence=flow.get("confidence", 0.8),
                road_closure=flow.get("roadClosure", False),
                captured_at=datetime.now().isoformat(),
            )

            # Cache in Redis
            from dataclasses import asdict
            await async_redis.set_tomtom_cache(segment_label, asdict(snap), ttl=120)
            return snap

        except Exception as e:
            logger.warning(f"TomTom API error for {segment_label}: {e}")
            cached = await async_redis.get_tomtom_cache(segment_label)
            if cached:
                return TrafficSnapshot(**cached)

    return _synthetic_snapshot(segment_label, lat, lon)


async def refresh_all_segments() -> dict[str, TrafficSnapshot]:
    """Fetch traffic for all Chennai segments concurrently."""
    global _latest_snapshots
    tasks = [
        get_flow_segment(label, lat, lon)
        for label, (lat, lon) in CHENNAI_SEGMENTS.items()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    snapshots = {}
    for label, result in zip(CHENNAI_SEGMENTS.keys(), results):
        if isinstance(result, TrafficSnapshot):
            snapshots[label] = result
        else:
            logger.warning(f"Failed to fetch {label}: {result}")
            snapshots[label] = _synthetic_snapshot(label, *CHENNAI_SEGMENTS[label])

    _latest_snapshots = snapshots

    # Persist to PostgreSQL
    try:
        from database import connection
        pool = connection.get_pool()
        if pool:
            async with pool.acquire() as conn:
                for snap in snapshots.values():
                    await conn.execute(
                        """INSERT INTO tomtom_snapshots
                           (segment_label, lat, lon, current_speed_kmph,
                            free_flow_speed_kmph, gridlock_ratio, confidence, road_closure)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                        snap.segment_label, snap.lat, snap.lon,
                        snap.current_speed_kmph, snap.free_flow_speed_kmph,
                        snap.gridlock_ratio, snap.confidence, snap.road_closure,
                    )
    except Exception as e:
        logger.debug(f"Could not persist TomTom snapshots to DB: {e}")

    logger.info(f"TomTom refresh complete: {len(snapshots)} segments.")
    return snapshots


async def start_refresh_loop(interval_seconds: int = 120):
    """Start a background loop that refreshes traffic data periodically."""
    global _refresh_task

    async def _loop():
        while True:
            try:
                await refresh_all_segments()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"TomTom refresh loop error: {e}")
            await asyncio.sleep(interval_seconds)

    _refresh_task = asyncio.create_task(_loop())
    logger.info(f"TomTom refresh loop started (every {interval_seconds}s).")


def get_latest_snapshots() -> dict[str, TrafficSnapshot]:
    """Get the most recently fetched traffic snapshots (non-async, from memory)."""
    return _latest_snapshots


def get_traffic_summary() -> dict:
    """Dashboard summary of current traffic state."""
    if not _latest_snapshots:
        return _synthetic_summary()

    ratios = [s.gridlock_ratio for s in _latest_snapshots.values()]
    avg_ratio = sum(ratios) / len(ratios) if ratios else 0.5
    congestion_pct = round((1 - avg_ratio) * 100)

    if avg_ratio < 0.4:
        label, color = "Heavy", "#ef4444"
    elif avg_ratio < 0.7:
        label, color = "Moderate", "#f59e0b"
    else:
        label, color = "Light", "#22c55e"

    bottlenecks = []
    for label_name, snap in sorted(_latest_snapshots.items(), key=lambda x: x[1].gridlock_ratio):
        bottlenecks.append({
            "name": label_name.replace("_", " ").title(),
            "congestion": round((1 - snap.gridlock_ratio) * 100),
            "speed": snap.current_speed_kmph,
        })

    return {
        "status": label,
        "color": color,
        "congestion_index": congestion_pct,
        "bottlenecks": bottlenecks[:5],
        "source": "TomTom Traffic Flow API" if _api_key else "Synthetic (Time-of-Day)",
        "updated_at": datetime.now().strftime("%H:%M:%S"),
    }


def _synthetic_snapshot(segment_label: str, lat: float, lon: float) -> TrafficSnapshot:
    """Generate a realistic synthetic traffic snapshot based on time of day."""
    hour = datetime.now().hour
    if 8 <= hour <= 10:
        speed = 12 + (hash(segment_label) % 10)
    elif 17 <= hour <= 20:
        speed = 8 + (hash(segment_label) % 12)
    elif 12 <= hour <= 14:
        speed = 25 + (hash(segment_label) % 10)
    else:
        speed = 38 + (hash(segment_label) % 14)

    free_flow = 52.0
    return TrafficSnapshot(
        segment_label=segment_label,
        lat=lat, lon=lon,
        current_speed_kmph=float(speed),
        free_flow_speed_kmph=free_flow,
        gridlock_ratio=round(speed / free_flow, 3),
        confidence=0.7,
        road_closure=False,
        captured_at=datetime.now().isoformat(),
    )


def _synthetic_summary() -> dict:
    """Synthetic summary when no real data is available."""
    hour = datetime.now().hour
    if 8 <= hour <= 10 or 17 <= hour <= 20:
        return {"status": "Heavy", "color": "#ef4444", "congestion_index": 78,
                "bottlenecks": [], "source": "Synthetic", "updated_at": datetime.now().strftime("%H:%M:%S")}
    elif 12 <= hour <= 14:
        return {"status": "Moderate", "color": "#f59e0b", "congestion_index": 45,
                "bottlenecks": [], "source": "Synthetic", "updated_at": datetime.now().strftime("%H:%M:%S")}
    return {"status": "Light", "color": "#22c55e", "congestion_index": 18,
            "bottlenecks": [], "source": "Synthetic", "updated_at": datetime.now().strftime("%H:%M:%S")}
