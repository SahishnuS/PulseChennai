"""
Pulse-Chennai AIS-140 Hardware Simulator
==========================================
Simulates 2 MTC buses on real Chennai routes:
  - Route 19:   Thiruporur → T. Nagar (via OMR)
  - Route 102X: Thiruporur → Broadway (via OMR + Adyar + Marina)

Sends HTTP POST to /api/ingest every 2 seconds.
Injects ghost bus events at deterministic steps.
Also simulates passenger pings near ghost bus locations.

Usage:
    python -m simulator.demo_simulation
"""

import time
import random
import asyncio
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("simulator")

API_BASE = "http://localhost:8001/api"

# ── Real Chennai MTC Routes (GPS waypoints sourced from public data) ──
# Coordinates represent major bus stops / landmarks along each route.
ROUTES = {
    "MTC-19-001": {
        "route": "19", "name": "Thiruporur → T. Nagar",
        "waypoints": [
            (12.7260, 80.1893),  # Thiruporur Bus Stand
            (12.7535, 80.1980),  # Kalavakkam / SSN College
            (12.7864, 80.2135),  # Kelambakkam
            (12.8077, 80.2258),  # Padur
            (12.8361, 80.2036),  # Siruseri IT Park
            (12.8625, 80.2285),  # Semmancheri
            (12.8961, 80.2249),  # Sholinganallur Junction
            (12.9142, 80.2294),  # Karapakkam
            (12.9386, 80.2377),  # Thoraipakkam
            (12.9654, 80.2461),  # Perungudi
            (12.9856, 80.2614),  # Thiruvanmiyur
            (13.0224, 80.2204),  # Saidapet
            (13.0418, 80.2341),  # T. Nagar Bus Depot
        ],
    },
    "MTC-102X-002": {
        "route": "102X", "name": "Thiruporur → Broadway",
        "waypoints": [
            (12.7260, 80.1893),  # Thiruporur Bus Stand
            (12.7535, 80.1980),  # Kalavakkam
            (12.7864, 80.2135),  # Kelambakkam
            (12.8077, 80.2258),  # Padur
            (12.8361, 80.2036),  # Siruseri IT Park
            (12.8625, 80.2285),  # Semmancheri
            (12.8961, 80.2249),  # Sholinganallur Junction
            (12.9142, 80.2294),  # Karapakkam
            (12.9386, 80.2377),  # Thoraipakkam
            (12.9654, 80.2461),  # Perungudi
            (12.9896, 80.2486),  # Tidel Park / SRP Tools
            (13.0050, 80.2550),  # Adyar Depot
            (13.0335, 80.2733),  # Santhome
            (13.0542, 80.2837),  # Marina Beach / Queen Mary's
            (13.0905, 80.2844),  # Broadway (Terminus)
        ],
    },
}

# Ghost bus events: (bus_id, trigger_step_in_cycle, duration_steps)
# Route 19 bus experiences a ghost event (AIS-140 hardware failure)
GHOST_EVENTS = [
    ("MTC-19-001", 15, 25),   # Fails at step 15 in each cycle, lasts 25 steps
]

# Passenger pings to simulate near ghost buses
PASSENGER_COUNT = 8


def interpolate_position(waypoints, step, total_steps):
    """Interpolate GPS position along a waypoint sequence."""
    if not waypoints:
        return 13.0, 80.2
    n = len(waypoints) - 1
    progress = (step % total_steps) / total_steps
    segment = min(int(progress * n), n - 1)
    t = (progress * n) - segment

    lat = waypoints[segment][0] + t * (waypoints[segment+1][0] - waypoints[segment][0])
    lon = waypoints[segment][1] + t * (waypoints[segment+1][1] - waypoints[segment][1])

    # Add realistic GPS noise (sigma ~3m ≈ 0.00003 degrees)
    lat += random.gauss(0, 0.00003)
    lon += random.gauss(0, 0.00003)
    return lat, lon


def get_realistic_speed(hour):
    """Chennai speed by time of day."""
    if 8 <= hour <= 10:
        return random.uniform(8, 18)
    elif 17 <= hour <= 20:
        return random.uniform(5, 15)
    elif 12 <= hour <= 14:
        return random.uniform(20, 35)
    else:
        return random.uniform(30, 52)


async def run_simulation():
    """Main simulation loop."""
    try:
        import httpx
    except ImportError:
        logger.error("httpx not installed! Run: pip install httpx")
        return

    total_steps = 120  # Full cycle per bus

    logger.info("=" * 60)
    logger.info("PULSE-CHENNAI AIS-140 SIMULATOR")
    logger.info(f"Buses: {len(ROUTES)} | Ghost events: {len(GHOST_EVENTS)}")
    logger.info(f"API: {API_BASE}")
    logger.info("=" * 60)

    async with httpx.AsyncClient(timeout=5.0) as client:
        step = 0
        while True:
            hour = datetime.now().hour
            speed_base = get_realistic_speed(hour)
            cycle_step = step % total_steps

            tasks = []
            status_lines = []

            for bus_id, route_info in ROUTES.items():
                lat, lon = interpolate_position(route_info["waypoints"], step, total_steps)

                # Check ghost events (using cycle_step so they repeat)
                is_ghost_step = False
                for g_bus, g_trigger, g_duration in GHOST_EVENTS:
                    if bus_id == g_bus and g_trigger <= cycle_step < g_trigger + g_duration:
                        is_ghost_step = True
                        break

                if is_ghost_step:
                    # Inject faulty hardware data
                    payload = {
                        "device_id": bus_id,
                        "lat": lat,
                        "lng": lon,
                        "speed": random.uniform(120, 180),   # Impossible speed
                        "heading": random.uniform(0, 360),
                        "jitter": random.uniform(100, 500),   # Massive jitter
                        "age_s": random.uniform(0.5, 3),
                        "route": route_info["route"],
                        "near": route_info["name"],
                    }
                    status_lines.append(f"🚨 {bus_id:20s} | GHOST | speed=150+ | step {step}")

                    # Also send passenger pings near this ghost bus
                    for i in range(PASSENGER_COUNT):
                        p_lat = lat + random.gauss(0, 0.0005)
                        p_lon = lon + random.gauss(0, 0.0005)
                        p_payload = {
                            "lat": p_lat,
                            "lon": p_lon,
                            "accuracy_m": random.uniform(5, 20),
                            "session_token": f"passenger_{step}_{i}",
                        }
                        tasks.append(client.post(f"{API_BASE}/passenger-ping", json=p_payload))
                else:
                    payload = {
                        "device_id": bus_id,
                        "lat": lat,
                        "lng": lon,
                        "speed": speed_base + random.uniform(-5, 5),
                        "heading": random.uniform(0, 360),
                        "jitter": random.uniform(0.5, 5),
                        "age_s": random.uniform(0.1, 1.5),
                        "route": route_info["route"],
                        "near": route_info["name"],
                    }
                    status_lines.append(f"✅ {bus_id:20s} | OK    | speed={payload['speed']:.0f}km/h")

                tasks.append(client.post(f"{API_BASE}/ingest", json=payload))

            # Send all pings concurrently
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                errors = [r for r in results if isinstance(r, Exception)]
                if errors:
                    logger.warning(f"  {len(errors)} request(s) failed")
            except Exception as e:
                logger.error(f"Batch send failed: {e}")

            # Print status
            if step % 5 == 0:
                logger.info(f"\n{'─'*55}")
                logger.info(f"Step {step} | {datetime.now().strftime('%H:%M:%S')}")
                for line in status_lines:
                    logger.info(f"  {line}")

            step += 1
            await asyncio.sleep(2)  # 2-second ping interval


if __name__ == "__main__":
    try:
        asyncio.run(run_simulation())
    except KeyboardInterrupt:
        logger.info("Simulator stopped.")
