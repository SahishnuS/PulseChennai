"""
Pulse-Chennai Functional Demonstration (1-Hour Prototype)
=========================================================
This script acts as the "Hardware Integration Layer" for the prototype.
It simulates 2 MTC buses (Route 19 and Route 102X) moving along real
Chennai routes and sends HTTP POST requests to our FastAPI backend.

It intentionally injects corrupted data (Ghost Bus) to demonstrate
the Collaborative Telemetry recovery logic.
"""

import time
import requests
import random

API_URL = "http://localhost:8001/api/ingest"

# ── Real Chennai MTC Route waypoints (GPS coordinates) ──
# Route 19:   Thiruporur → T. Nagar (via OMR)
ROUTE_19_WAYPOINTS = [
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
]

# Route 102X: Thiruporur → Broadway (via OMR + Adyar + Marina)
ROUTE_102X_WAYPOINTS = [
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
]

TOTAL_STEPS = 60  # 1 minute loop if 1 ping/sec

def interpolate_waypoints(waypoints, step, total_steps):
    """Interpolate position along a multi-waypoint route."""
    n = len(waypoints) - 1
    progress = (step % total_steps) / total_steps
    segment = min(int(progress * n), n - 1)
    t = (progress * n) - segment
    lat = waypoints[segment][0] + t * (waypoints[segment + 1][0] - waypoints[segment][0])
    lng = waypoints[segment][1] + t * (waypoints[segment + 1][1] - waypoints[segment][1])
    # Add slight natural GPS jitter
    lat += random.uniform(-0.0002, 0.0002)
    lng += random.uniform(-0.0002, 0.0002)
    return lat, lng

buses = [
    {"id": "MTC-19-001",   "route": "19",   "near": "OMR Corridor",  "waypoints": ROUTE_19_WAYPOINTS,   "step_offset": 0,  "ghost_at": 30},
    {"id": "MTC-102X-002", "route": "102X", "near": "OMR / Marina",  "waypoints": ROUTE_102X_WAYPOINTS, "step_offset": 15, "ghost_at": None},
]

print("=" * 60)
print("PULSE-CHENNAI HARDWARE TELEMETRY SIMULATOR")
print(f"  Buses: Route 19 (Thiruporur→T.Nagar), Route 102X (Thiruporur→Broadway)")
print(f"  Target API: {API_URL}")
print("=" * 60)

step = 0
while True:
    print(f"\n--- Simulation Step {step} ---")

    for bus in buses:
        # Calculate current position along the real route
        current_bus_step = (step + bus["step_offset"]) % TOTAL_STEPS
        current_lat, current_lng = interpolate_waypoints(bus["waypoints"], current_bus_step, TOTAL_STEPS)

        speed = random.uniform(30.0, 45.0)
        jitter = random.uniform(1.0, 5.0)
        age_s = random.uniform(0.1, 2.0)

        # Inject Ghost Bus Failure
        is_failing = False
        if bus["ghost_at"] is not None and current_bus_step >= bus["ghost_at"] and current_bus_step <= bus["ghost_at"] + 15:
            # Simulate broken hardware (e.g. impossible speed, huge jitter)
            speed = random.uniform(110.0, 150.0)
            jitter = random.uniform(100.0, 300.0)
            is_failing = True

        payload = {
            "device_id": bus["id"],
            "lat": current_lat,
            "lng": current_lng,
            "speed": speed,
            "jitter": jitter,
            "age_s": age_s,
            "route": bus["route"],
            "near": bus["near"]
        }

        try:
            resp = requests.post(API_URL, json=payload, timeout=2)
            if resp.status_code in (200, 202):
                data = resp.json()
                if is_failing:
                    print(f"[!!] [GHOST EVENT] {bus['id']} -> Sent corrupted data. API classified as Ghost: {data.get('is_ghost')}")
                else:
                    print(f"[OK] {bus['id']} -> Sent healthy telemetry.")
            else:
                print(f"[ERR] [HTTP ERROR] {bus['id']} -> {resp.status_code}")
        except requests.exceptions.ConnectionError:
            print("[ERR] Backend is not running! Please start 'uvicorn api.dashboard_server:app --port 8001'")
            time.sleep(2)
            break

    step += 1
    time.sleep(1)  # Send pings every 1 second
