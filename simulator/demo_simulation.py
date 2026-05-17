"""
Pulse-Chennai Demo Simulator (Supabase Edition)
==================================================
Simulates 6 MTC buses on real Chennai routes.
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

STOPS_23C = [
    (12.9824, 80.2588), (12.9831, 80.2541), (12.9799, 80.2576), (12.9836, 80.2463),
    (12.9901, 80.2378), (12.9986, 80.2369), (13.0182, 80.2213), (13.0365, 80.2129),
    (13.0418, 80.2341)
]

STOPS_47A = [
    (13.0891, 80.2101), (13.0842, 80.2089), (13.0778, 80.2023), 
    (13.0722, 80.1963), (13.0698, 80.1944)
]

STOPS_21B = [
    (13.0827, 80.2756), (13.0792, 80.2731), (13.0198, 80.2234), 
    (12.9516, 80.1430), (12.9249, 80.1000)
]

STOPS_M70 = [
    (12.9799, 80.2576), (12.9986, 80.2369), (13.0182, 80.2213), 
    (13.0066, 80.2206), (12.9516, 80.1430)
]

BUSES = [
  {
    "id": "BUS_23C_001",
    "route": "23C",
    "stops": STOPS_23C,
    "crowding_pattern": ["low", "medium", "medium", "high", "high", "medium", "low", "low", "low"],
    "ghost_at_index": 2,
    "speed_kmh": 16,
    "start_offset": 0
  },
  {
    "id": "BUS_23C_002",
    "route": "23C", 
    "stops": STOPS_23C,
    "start_offset": 4,
    "crowding_pattern": ["medium", "high", "high", "medium", "low", "low", "low", "low", "low"],
    "ghost_at_index": None,
    "speed_kmh": 18
  },
  {
    "id": "BUS_47A_001",
    "route": "47A",
    "stops": STOPS_47A,
    "crowding_pattern": ["low", "low", "medium", "high", "high"],
    "skip_stop_index": 2,
    "ghost_at_index": None,
    "speed_kmh": 14,
    "start_offset": 0
  },
  {
    "id": "BUS_21B_001",
    "route": "21B",
    "stops": STOPS_21B,
    "crowding_pattern": ["high", "high", "medium", "medium", "low"],
    "ghost_at_index": None,
    "speed_kmh": 20,
    "start_offset": 0
  },
  {
    "id": "BUS_21B_002",
    "route": "21B",
    "stops": list(reversed(STOPS_21B)),
    "crowding_pattern": ["low", "medium", "medium", "high", "high"],
    "ghost_at_index": None,
    "speed_kmh": 17,
    "start_offset": 1
  },
  {
    "id": "BUS_M70_001",
    "route": "M70",
    "stops": STOPS_M70,
    "crowding_pattern": ["low", "low", "medium", "medium", "high"],
    "ghost_at_index": None,
    "speed_kmh": 22,
    "start_offset": 0
  }
]


def interpolate_position(waypoints, progress):
    """Interpolate GPS position along a waypoint sequence."""
    if not waypoints:
        return 13.0, 80.2, 0

    n = len(waypoints) - 1
    progress = max(0.0, min(1.0, progress))
    segment_float = progress * n
    segment = min(int(segment_float), n - 1)
    t = segment_float - segment

    lat = waypoints[segment][0] + t * (waypoints[segment + 1][0] - waypoints[segment][0])
    lng = waypoints[segment][1] + t * (waypoints[segment + 1][1] - waypoints[segment][1])

    lat += random.gauss(0, 0.00003)
    lng += random.gauss(0, 0.00003)

    return lat, lng, segment


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
    logger.info("PULSE-CHENNAI DEMO SIMULATOR (6 Buses)")
    logger.info("=" * 60)

    # Initialize bus states
    bus_state = {}
    for bus in BUSES:
        n = len(bus["stops"]) - 1
        initial_progress = min(1.0, bus.get("start_offset", 0) / max(1, n))
        
        bus_state[bus["id"]] = {
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
            waypoints = bus["stops"]
            n = len(waypoints) - 1

            # Advance position
            route_length_estimate = n * 0.005
            speed_progress = (bus["speed_kmh"] / 3600 * PING_INTERVAL * 0.00001) / max(route_length_estimate, 0.001)
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

            lat, lng, stop_index = interpolate_position(waypoints, state["progress"])

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

            # Skip stop logic (47A skipping Thirumangalam)
            if bus.get("skip_stop_index") is not None:
                if stop_index == bus["skip_stop_index"] and not state["skip_done"] and state["direction"] == 1:
                    state["progress"] = min((bus["skip_stop_index"] + 1) / max(1, n) + 0.01, 1.0)
                    lat, lng, stop_index = interpolate_position(waypoints, state["progress"])
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

            # Compute heading
            heading = random.uniform(0, 360)
            if stop_index < n:
                next_wp = waypoints[stop_index + 1]
                heading = math.degrees(math.atan2(
                    next_wp[1] - waypoints[stop_index][1],
                    next_wp[0] - waypoints[stop_index][0]
                )) % 360

            speed = bus["speed_kmh"] + random.uniform(-2, 2)
            if state["is_ghost"]:
                speed = 0

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

        step += 1
        await asyncio.sleep(PING_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(run_simulation())
    except KeyboardInterrupt:
        logger.info("Simulator stopped.")
