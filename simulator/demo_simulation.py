"""
Pulse-Chennai AIS-140 Hardware Simulator
==========================================
Simulates 5 MTC buses on real Chennai routes.
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

# ── Real Chennai Routes (10-15 waypoints each) ──
ROUTES = {
    "MTC-21G-001": {
        "route": "21G", "name": "Tambaram → Central",
        "waypoints": [
            (12.9249, 80.1000),  # Tambaram
            (12.9400, 80.1200),  # Chromepet
            (12.9600, 80.1500),  # Pallavaram
            (12.9786, 80.2000),  # Meenambakkam
            (13.0067, 80.2206),  # Guindy
            (13.0200, 80.2350),  # Saidapet
            (13.0400, 80.2450),  # Mambalam
            (13.0569, 80.2497),  # T. Nagar / Anna Salai
            (13.0620, 80.2560),  # Teynampet
            (13.0700, 80.2630),  # Thousand Lights
            (13.0780, 80.2680),  # Park Station
            (13.0827, 80.2707),  # Chennai Central
        ],
    },
    "MTC-5C-002": {
        "route": "5C", "name": "Koyambedu → T. Nagar",
        "waypoints": [
            (13.0694, 80.1948),  # Koyambedu
            (13.0620, 80.2050),  # Arumbakkam
            (13.0580, 80.2121),  # Vadapalani
            (13.0520, 80.2200),  # Ashok Nagar
            (13.0480, 80.2280),  # K.K. Nagar
            (13.0550, 80.2337),  # Ashok Pillar
            (13.0620, 80.2376),  # Pondy Bazaar
            (13.0674, 80.2376),  # T. Nagar
        ],
    },
    "MTC-12-003": {
        "route": "12", "name": "Guindy → Parry's Corner",
        "waypoints": [
            (13.0067, 80.2206),  # Guindy
            (13.0200, 80.2350),  # Saidapet
            (13.0350, 80.2430),  # Nandanam
            (13.0450, 80.2480),  # Alwarpet
            (13.0500, 80.2550),  # R.A. Puram
            (13.0550, 80.2600),  # Mylapore
            (13.0600, 80.2650),  # Triplicane
            (13.0700, 80.2700),  # Flower Bazaar
            (13.0830, 80.2850),  # Parry's Corner
        ],
    },
    "MTC-47-004": {
        "route": "47", "name": "Velachery → Central",
        "waypoints": [
            (12.9786, 80.2209),  # Velachery
            (12.9883, 80.2350),  # Taramani
            (12.9950, 80.2400),  # Raj Bhavan
            (13.0050, 80.2450),  # Adyar
            (13.0150, 80.2500),  # Kotturpuram
            (13.0300, 80.2550),  # Nandanam
            (13.0500, 80.2600),  # Teynampet
            (13.0650, 80.2650),  # Egmore
            (13.0827, 80.2707),  # Central
        ],
    },
    "MTC-GHOST-007": {
        "route": "29C", "name": "Ambattur → Central (GHOST TARGET)",
        "waypoints": [
            (13.1143, 80.1548),  # Ambattur
            (13.1050, 80.1700),  # Padi
            (13.0900, 80.1800),  # Anna Nagar
            (13.0800, 80.1950),  # Aminjikarai
            (13.0750, 80.2100),  # Chetpet
            (13.0700, 80.2250),  # Nungambakkam
            (13.0750, 80.2400),  # Egmore
            (13.0827, 80.2707),  # Central
        ],
    },
}

# Ghost bus events: (bus_id, trigger_step_in_cycle, duration_steps)
# These repeat every cycle (total_steps=120)
GHOST_EVENTS = [
    ("MTC-GHOST-007", 2, 30),   # Fails at step 2 in each cycle, lasts 30 steps
    ("MTC-12-003",    50, 15),  # Goes silent at step 50 for 15 steps
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
