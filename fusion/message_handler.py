"""
Message Handler — The Core Processing Pipeline
=================================================
This module is the central nervous system of Pulse-Chennai.
It is called for every GPS ping (from Kafka consumer or HTTP fallback)
and orchestrates the full processing pipeline:

  1. Hardware Reliability Scoring
  2. Ghost Bus Detection → Event logging
  3. Passenger Telemetry Fusion (if ghost)
  4. TomTom-calibrated position projection (if ghost)
  5. Update Redis Speed Layer
  6. Persist to PostgreSQL
  7. Publish update to WebSocket via Redis pub/sub
"""

import time
import math
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Hardware scorer is stateful (keeps rolling history per bus), so we use a singleton
from hardware.reliability_scorer import HardwareReliabilityScorer
# Use a lower decay_rate (0.3) for instant demo response.
# Production would use 0.95 for better false-positive filtering.
_scorer = HardwareReliabilityScorer(decay_rate=0.3)


async def handle_message(topic: str, message: dict):
    """Route a Kafka/HTTP message to the correct handler."""
    if topic in ("bus-gps-pings", "bus_gps_pings"):
        await _handle_bus_ping(message)
    elif topic in ("passenger-pings", "passenger_pings"):
        await _handle_passenger_ping(message)
    else:
        logger.debug(f"Unknown topic: {topic}")


async def _handle_bus_ping(ping: dict):
    """Process a single bus GPS ping through the full pipeline."""
    from infrastructure import async_redis
    from infrastructure import kafka_producer

    bus_id = ping.get("bus_id", ping.get("device_id", "unknown"))
    lat = ping.get("lat", 0)
    lng = ping.get("lng", ping.get("lon", 0))
    speed = ping.get("speed", ping.get("speed_kmph", None))
    heading = ping.get("heading", 0)
    route_id = ping.get("route_id", ping.get("route", ""))
    ts = ping.get("timestamp", time.time() * 1000)

    # 1. Hardware Reliability Scoring
    hw_score = _scorer.score_ping(
        bus_id=bus_id, lat=lat, lng=lng,
        timestamp=ts, speed=speed,
    )

    is_ghost = hw_score < 0.3
    status = "active"
    source = "AIS140"
    confidence = min(1.0, hw_score + 0.2)
    final_lat, final_lng = lat, lng
    final_speed = speed if speed is not None else 0

    # 2. Ghost Bus Detection
    if is_ghost:
        status = "ghost_suppressed"
        source = "GHOST"
        final_speed = 0  # Suppress faulty speed reading

        # Log ghost event to PostgreSQL
        await _log_ghost_event(bus_id, hw_score, speed)

        # 3. Attempt recovery via passenger pings
        passenger_pings = await async_redis.georadius_passenger_pings(lat, lng, radius_m=200)

        if len(passenger_pings) >= 3:
            # Compute centroid of passenger cluster
            centroid_lat = sum(p["lat"] for p in passenger_pings) / len(passenger_pings)
            centroid_lon = sum(p["lon"] for p in passenger_pings) / len(passenger_pings)

            # Weighted fusion: 70% passenger cluster, 30% last known
            final_lat = 0.7 * centroid_lat + 0.3 * lat
            final_lng = 0.7 * centroid_lon + 0.3 * lng
            status = "ghost_recovered"
            source = "FUSED_PASSENGER"
            confidence = 0.7 + (min(len(passenger_pings), 20) / 100)
            logger.info(f"Ghost bus {bus_id} recovered via {len(passenger_pings)} passenger pings.")

            # Publish ghost event
            await kafka_producer.send_ghost_event({
                "bus_id": bus_id,
                "hw_score": hw_score,
                "recovery_source": "PASSENGER",
                "passenger_ping_count": len(passenger_pings),
                "recovered_lat": final_lat,
                "recovered_lng": final_lng,
                "timestamp": datetime.now().isoformat(),
            })

        else:
            # 4. Dead reckoning with TomTom speed
            from traffic import tomtom_client
            snapshots = tomtom_client.get_latest_snapshots()
            if snapshots:
                # Find nearest segment
                nearest = _find_nearest_segment(lat, lng, snapshots)
                if nearest:
                    # Project forward using TomTom speed
                    bus_state = await async_redis.get_bus_state(bus_id)
                    if bus_state:
                        last_seen = bus_state.get("last_seen", time.time())
                        elapsed_s = time.time() - last_seen
                        distance_m = nearest.current_speed_kmph * (elapsed_s / 3600) * 1000
                        final_lat, final_lng = _project_position(
                            bus_state.get("lat", lat),
                            bus_state.get("lng", lng),
                            bus_state.get("heading", heading),
                            distance_m,
                        )
                        final_speed = nearest.current_speed_kmph
                        status = "ghost_recovered"
                        source = "FUSED_TOMTOM"
                        confidence = 0.5

    # Compute H3 cell
    h3_cell = ""
    try:
        import h3
        # h3 v4+ uses latlng_to_cell, v3 uses geo_to_h3
        if hasattr(h3, 'latlng_to_cell'):
            h3_cell = h3.latlng_to_cell(final_lat, final_lng, 9)
        elif hasattr(h3, 'geo_to_h3'):
            h3_cell = h3.geo_to_h3(final_lat, final_lng, 9)
    except Exception:
        pass

    # 5. HMM Map-Matching
    try:
        from model.hmm_map_matching import HMMMapMatcher
        global _hmm_matcher
        if '_hmm_matcher' not in globals():
            _hmm_matcher = HMMMapMatcher()
        match_result = _hmm_matcher.match_point(final_lat, final_lng, heading, congestion_score=0.0)
        snapped_lat = match_result.snapped_lat
        snapped_lng = match_result.snapped_lng
        road_segment = match_result.segment_id
        road_class = match_result.road_class
    except Exception as e:
        logger.debug(f"HMM map-matching failed: {e}")
        snapped_lat, snapped_lng, road_segment, road_class = final_lat, final_lng, "unknown", "unknown"

    # 5.5 Update Redis Speed Layer
    bus_state = {
        "lat": round(final_lat, 6),
        "lng": round(final_lng, 6),
        "snapped_lat": round(snapped_lat, 6),
        "snapped_lng": round(snapped_lng, 6),
        "road_segment": road_segment,
        "road_class": road_class,
        "speed": round(final_speed, 1) if final_speed else 0,
        "heading": heading,
        "hw_score": round(hw_score, 4),
        "is_ghost": is_ghost,
        "status": status,
        "route_id": route_id,
        "h3_cell": h3_cell,
        "passenger_count": ping.get("passenger_count", 0),
        "source": source,
        "confidence": round(confidence, 3),
    }
    await async_redis.set_bus_state(bus_id, bus_state)

    # 6. Persist to PostgreSQL
    await _persist_ping(bus_id, ping, hw_score, h3_cell, source)
    await _update_bus_record(bus_id, bus_state)

    # 7. Publish to WebSocket channel
    await async_redis.publish_update("bus_updates", {
        "type": "bus_update",
        "trip_id": bus_id,
        **bus_state,
    })


async def _handle_passenger_ping(ping: dict):
    """Process a passenger GPS ping — store in geospatial index."""
    from infrastructure import async_redis

    lat = ping.get("lat", 0)
    lon = ping.get("lng", ping.get("lon", 0))
    session_token = ping.get("session_token", f"anon_{time.time()}")

    await async_redis.geoadd_passenger_ping(session_token, lat, lon)
    logger.debug(f"Passenger ping stored: {session_token} @ ({lat}, {lon})")


async def _log_ghost_event(bus_id: str, hw_score: float, speed: Optional[float]):
    """Log a ghost bus detection event to PostgreSQL."""
    try:
        from database import connection
        pool = connection.get_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO ghost_bus_events (bus_id, health_score_at_detection, trigger_reason)
                       VALUES ($1, $2, $3)""",
                    bus_id, hw_score,
                    f"HW score {hw_score:.3f} < 0.3. Speed: {speed}",
                )
    except Exception as e:
        logger.debug(f"Could not log ghost event to DB: {e}")


async def _persist_ping(bus_id: str, ping: dict, hw_score: float, h3_cell: str, source: str):
    """Persist a GPS ping to the gps_pings table."""
    try:
        from database import connection
        pool = connection.get_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO gps_pings
                       (bus_id, timestamp, raw_lat, raw_lon, reported_speed_kmph,
                        heading, h3_cell_id, source, hw_score_at_ping)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                    bus_id,
                    datetime.now(),
                    ping.get("lat", 0),
                    ping.get("lng", ping.get("lon", 0)),
                    ping.get("speed", 0),
                    ping.get("heading", 0),
                    h3_cell,
                    source,
                    hw_score,
                )
    except Exception as e:
        logger.debug(f"Could not persist ping to DB: {e}")


async def _update_bus_record(bus_id: str, state: dict):
    """Update the buses table with current state."""
    try:
        from database import connection
        pool = connection.get_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.execute(
                    """UPDATE buses SET
                       device_health_score = $2, is_ghost = $3, last_seen = $4,
                       current_speed_kmph = $5, heading = $6, h3_cell_id = $7,
                       status = $8, passenger_count = $9, updated_at = NOW()
                       WHERE bus_id = $1""",
                    bus_id,
                    state.get("hw_score", 1.0),
                    state.get("is_ghost", False),
                    datetime.now(),
                    state.get("speed", 0),
                    state.get("heading", 0),
                    state.get("h3_cell", ""),
                    state.get("status", "active"),
                    state.get("passenger_count", 0),
                )
    except Exception as e:
        logger.debug(f"Could not update bus record: {e}")


def _find_nearest_segment(lat, lng, snapshots):
    """Find the nearest TomTom traffic segment to a given point."""
    from traffic.tomtom_client import CHENNAI_SEGMENTS
    best_dist = float("inf")
    best_snap = None
    for label, (seg_lat, seg_lon) in CHENNAI_SEGMENTS.items():
        dist = _haversine(lat, lng, seg_lat, seg_lon)
        if dist < best_dist:
            best_dist = dist
            best_snap = snapshots.get(label)
    return best_snap


def _haversine(lat1, lon1, lat2, lon2):
    """Haversine distance in meters."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def _project_position(lat, lon, heading_deg, distance_m):
    """Project a position forward along a heading by a given distance."""
    R = 6_371_000
    heading_rad = math.radians(heading_deg)
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    new_lat = math.asin(
        math.sin(lat_rad) * math.cos(distance_m / R) +
        math.cos(lat_rad) * math.sin(distance_m / R) * math.cos(heading_rad)
    )
    new_lon = lon_rad + math.atan2(
        math.sin(heading_rad) * math.sin(distance_m / R) * math.cos(lat_rad),
        math.cos(distance_m / R) - math.sin(lat_rad) * math.sin(new_lat)
    )
    return math.degrees(new_lat), math.degrees(new_lon)
