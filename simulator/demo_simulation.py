"""
Pulse-Chennai Demo Simulator (Supabase Edition)
==================================================
Simulates 3 MTC buses on real Chennai routes (19, 102X, 515).
Writes directly to Supabase — NO Kafka dependency.
"""

import os
import sys
import math
import random
import asyncio
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("simulator")

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

# Ensure parent directory is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from traffic.routing_service import get_route_path

STOPS_19 = [
    (12.7275, 80.1989), (12.7915, 80.2185), (12.8361, 80.2199), (12.8988, 80.2281),
    (12.9824, 80.2588), (13.0182, 80.2213), (13.0418, 80.2341)
]

STOPS_102X = [
    (12.7915, 80.2185), (12.8361, 80.2199), (12.8988, 80.2281), (12.9379, 80.2366),
    (12.9649, 80.2450), (13.0012, 80.2565), (13.0326, 80.2783), (13.0886, 80.2872)
]

STOPS_515 = [
    (12.9249, 80.1000), (12.9048, 80.0894), (12.8872, 80.0832), (12.8344, 80.1500),
    (12.7915, 80.2185), (12.7275, 80.1989), (12.6208, 80.1945)
]

BUSES = [
  {
    "id": "BUS_19_001",
    "route": "19",
    "stops": STOPS_19,
    "crowding_pattern": ["low", "low", "medium", "high", "high", "medium", "low"],
    "ghost_at_index": 2,
    "speed_kmh": 22,
    "start_offset": 0
  },
  {
    "id": "BUS_102X_001",
    "route": "102X",
    "stops": STOPS_102X,
    "crowding_pattern": ["low", "low", "medium", "high", "high", "high", "medium", "low"],
    "skip_stop_index": 2,
    "ghost_at_index": None,
    "speed_kmh": 26,
    "start_offset": 1
  },
  {
    "id": "BUS_515_001",
    "route": "515",
    "stops": STOPS_515,
    "crowding_pattern": ["low", "medium", "medium", "low", "low", "low", "low"],
    "ghost_at_index": None,
    "speed_kmh": 20,
    "start_offset": 0
  }
]


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    return 2 * 6371 * math.asin(math.sqrt(a))


def polyline_length_km(polyline: list[tuple]) -> float:
    """Calculate the total length of the waypoint path in km using Haversine sum."""
    total = 0.0
    for i in range(len(polyline) - 1):
        lat1, lng1 = polyline[i]
        lat2, lng2 = polyline[i+1]
        total += haversine_km(lat1, lng1, lat2, lng2)
    return max(total, 0.001)


def snap_to_polyline(point: tuple, polyline: list[tuple]) -> tuple:
    """Find the closest point on the polyline to `point` using minimum Haversine distance."""
    if not polyline:
        return point
    best_dist = float('inf')
    best_pt = point
    lat, lng = point
    for p_lat, p_lng in polyline:
        d = haversine_km(lat, lng, p_lat, p_lng)
        if d < best_dist:
            best_dist = d
            best_pt = (p_lat, p_lng)
    return best_pt


def interpolate_position(waypoints, progress, total_length_km):
    """Interpolate GPS position accurately along a polyline by distance."""
    if not waypoints:
        return 13.0, 80.2, 0
    if len(waypoints) == 1:
        return waypoints[0][0], waypoints[0][1], 0

    progress = max(0.0, min(1.0, progress))
    target_dist = progress * total_length_km
    
    current_dist = 0.0
    for i in range(len(waypoints) - 1):
        lat1, lng1 = waypoints[i]
        lat2, lng2 = waypoints[i+1]
        d = haversine_km(lat1, lng1, lat2, lng2)
        
        if current_dist + d >= target_dist:
            t = (target_dist - current_dist) / d if d > 0 else 0
            lat = lat1 + t * (lat2 - lat1)
            lng = lng1 + t * (lng2 - lng1)
            
            # Add minor GPS jitter
            lat += random.gauss(0, 0.00003)
            lng += random.gauss(0, 0.00003)
            return lat, lng, i
            
        current_dist += d

    return waypoints[-1][0], waypoints[-1][1], len(waypoints) - 1


def get_supabase():
    from infrastructure.supabase_client import get_supabase as _get
    client = _get()
    if not client:
        logger.error("Supabase client not available. Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        sys.exit(1)
    return client


async def run_simulation():
    supabase = get_supabase()

    logger.info("=" * 60)
    logger.info("PULSE-CHENNAI DEMO SIMULATOR (3 Buses - Road-Aware Edition)")
    logger.info("=" * 60)

    # Initialize Upstash Redis for initialization calls
    from infrastructure import upstash_redis
    await upstash_redis.init()

    # Pre-fetch road-aware geometry paths for each bus route
    from app.services import deviation_detector as dev_det
    bus_paths = {}
    for bus in BUSES:
        bus_id = bus["id"]
        route_id = bus["route"]
        is_reversed = False
        
        logger.info(f"Loading road geometry for {bus_id} ({route_id})")
        waypoints, stop_indices = await get_route_path(route_id, reversed_direction=is_reversed)
        
        bus_paths[bus_id] = {
            "waypoints": waypoints,
            "stop_indices": stop_indices,
            "length_km": polyline_length_km(waypoints)
        }
        logger.info(f"  Loaded {len(waypoints)} waypoints, path length: {bus_paths[bus_id]['length_km']:.2f} km")

    # Initialize bus states
    bus_state = {}
    for bus in BUSES:
        bus_id = bus["id"]
        waypoints = bus_paths[bus_id]["waypoints"]
        stop_indices = bus_paths[bus_id]["stop_indices"]
        
        # Calculate initial progress fraction based on start_offset
        original_n = len(bus["stops"]) - 1
        start_stop = bus.get("start_offset", 0)
        # Find first index in stop_indices matching start_stop
        start_wp_idx = next((i for i, s_idx in enumerate(stop_indices) if s_idx >= start_stop), 0)
        initial_progress = start_wp_idx / max(1, len(waypoints) - 1)
        
        bus_state[bus_id] = {
            "progress": initial_progress,
            "direction": 1,
            "is_ghost": False,
            "crowding": bus["crowding_pattern"][0] if bus["crowding_pattern"] else "low",
            "skip_done": False,
            "ghost_timer": 0
        }

    step = 0
    PING_INTERVAL = 3

    while True:
        for bus in BUSES:
            bus_id = bus["id"]
            state = bus_state[bus_id]
            
            path_info = bus_paths[bus_id]
            waypoints = path_info["waypoints"]
            stop_indices = path_info["stop_indices"]
            route_length_km = path_info["length_km"]
            n = len(waypoints) - 1

            # Advance progress along road geometry
            step_dist_km = bus["speed_kmh"] * (PING_INTERVAL / 3600.0)
            speed_progress = step_dist_km / route_length_km
            state["progress"] += speed_progress * state["direction"]

            # Bounce
            if state["progress"] >= 1.0:
                state["progress"] = 1.0
                state["direction"] = -1
                state["skip_done"] = False
            elif state["progress"] <= 0.0:
                state["progress"] = 0.0
                state["direction"] = 1
                state["skip_done"] = False

            lat, lng, segment_idx = interpolate_position(waypoints, state["progress"], route_length_km)
            stop_index = stop_indices[segment_idx]

            # Crowding pattern based on stop
            if bus.get("crowding_pattern"):
                safe_index = min(stop_index, len(bus["crowding_pattern"]) - 1)
                state["crowding"] = bus["crowding_pattern"][safe_index]

            reliability_score = round(random.uniform(0.85, 0.98), 2)

            # Ghost logic
            if bus.get("ghost_at_index") is not None:
                if stop_index == bus["ghost_at_index"] and state["direction"] == 1:
                    state["is_ghost"] = True
                    reliability_score = round(random.uniform(0.05, 0.25), 2)
                elif stop_index != bus["ghost_at_index"]:
                    state["is_ghost"] = False

            # Skip stop logic
            if bus.get("skip_stop_index") is not None:
                if stop_index == bus["skip_stop_index"] and not state["skip_done"] and state["direction"] == 1:
                    # Find the first waypoint index belonging to the next stop or later
                    target_stop = bus["skip_stop_index"] + 1
                    target_wp_idx = next((i for i, s_idx in enumerate(stop_indices) if s_idx >= target_stop), n)
                    state["progress"] = target_wp_idx / n
                    lat, lng, segment_idx = interpolate_position(waypoints, state["progress"], route_length_km)
                    stop_index = stop_indices[segment_idx]
                    state["skip_done"] = True
                    
                    try:
                        supabase.table("alerts").insert({
                            "bus_id": bus_id,
                            "type": "stop_skip",
                            "message": f"Bus {bus['route']} skipped stop {bus['skip_stop_index']}",
                            "message_ta": f"{bus['route']} பேருந்து நிறுத்தத்தை தவிர்த்தது",
                        }).execute()
                    except Exception as e:
                        pass

            # Compute heading based on segment direction
            heading = random.uniform(0, 360)
            if segment_idx < n:
                next_wp = waypoints[segment_idx + 1]
                heading = math.degrees(math.atan2(
                    next_wp[1] - waypoints[segment_idx][1],
                    next_wp[0] - waypoints[segment_idx][0]
                )) % 360

            speed = bus["speed_kmh"] + random.uniform(-2, 2)
            if state["is_ghost"]:
                speed = 0

            # Snap to polyline to ensure it stays strictly on road
            lat, lng = snap_to_polyline((lat, lng), waypoints)

            row = {
                "id": bus_id,
                "route": bus["route"],
                "lat": round(lat, 6),
                "lng": round(lng, 6),
                "speed": round(speed, 1),
                "heading": round(heading, 1),
                "reliability_score": reliability_score,
                "is_ghost": state["is_ghost"],
                "crowding": state["crowding"],
                "last_seen": datetime.now().isoformat(),
                "stop_index": stop_index,
            }

            try:
                supabase.table("buses").upsert(row, on_conflict="id").execute()
            except Exception as e:
                logger.error(f"Upsert failed for {bus_id}: {e}")

            # Generate random passenger pings
            import httpx
            num_pings = random.randint(2, 5)
            async def send_ping(p_lat, p_lng):
                try:
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            "http://localhost:8000/api/passenger-ping",
                            json={"lat": p_lat, "lng": p_lng, "resolution": 8},
                            timeout=2.0
                        )
                except Exception:
                    pass
                    
            for _ in range(num_pings):
                # ~1km offset
                ping_lat = lat + random.uniform(-0.009, 0.009)
                ping_lng = lng + random.uniform(-0.009, 0.009)
                asyncio.create_task(send_ping(ping_lat, ping_lng))

            # ── Deviation detection ──────────────────────────────────────
            try:
                dev_result = dev_det.check_deviation(
                    bus_id      = bus_id,
                    current_pos = (lat, lng),
                    route_polyline = waypoints,
                )
                consec = dev_det.record_tick(bus_id, dev_result["deviated"])

                if consec >= dev_det.CONSECUTIVE_TICKS_ALERT:
                    # Build stops-ahead list from current stop_index
                    stop_names = [
                        f"Stop-{i}" for i in range(
                            min(stop_index + 1, len(bus["stops"]) - 1),
                            len(bus["stops"])
                        )
                    ]
                    # All buses on same route (for next-available-stop)
                    same_route_buses = [
                        {
                            "id": b["id"],
                            "is_deviated": dev_det._consecutive_deviation.get(b["id"], 0) >= dev_det.CONSECUTIVE_TICKS_ALERT,
                            "next_stop_name": f"Stop-{bus_state[b['id']].get('progress', 0):.0f}"
                        }
                        for b in BUSES if b["route"] == bus["route"]
                    ]
                    asyncio.create_task(dev_det.maybe_alert(
                        bus_id           = bus_id,
                        route            = bus["route"],
                        deviation_result = dev_result,
                        stop_names       = stop_names,
                        all_buses_on_route = same_route_buses,
                    ))
            except Exception as _e:
                pass  # Never let deviation detection crash the sim loop

        step += 1
        await asyncio.sleep(PING_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(run_simulation())
    except KeyboardInterrupt:
        logger.info("Simulator stopped.")
