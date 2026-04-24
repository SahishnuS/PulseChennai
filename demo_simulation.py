"""
Pulse-Chennai Functional Demonstration (1-Hour Prototype)
=========================================================
This script acts as the "Hardware Integration Layer" for the prototype.
It simulates multiple buses moving along routes and sends HTTP POST
requests to our FastAPI backend (`/dashboard/api/ingest`).

It intentionally injects corrupted data (Ghost Bus) to demonstrate
the Collaborative Telemetry recovery logic.
"""

import time
import requests
import random

API_URL = "http://localhost:8001/dashboard/api/ingest"

# A simplified linear route for simulation (Guindy to Chennai Central)
START_LAT, START_LNG = 13.0044, 80.2496
END_LAT, END_LNG = 13.0827, 80.2707
TOTAL_STEPS = 60  # 1 minute loop if 1 ping/sec

def interpolate(start, end, step, total_steps):
    return start + (end - start) * (step / total_steps)

buses = [
    {"id": "MTC-21G-001", "route": "21G", "near": "Mount Road", "step_offset": 0, "ghost_at": None},
    {"id": "MTC-5C-002",  "route": "5C",  "near": "T. Nagar",   "step_offset": 20, "ghost_at": None},
    # The Ghost Bus scenario: Fails at step 30
    {"id": "MTC-GHOST-007", "route": "21G", "near": "Ashok Nagar", "step_offset": 10, "ghost_at": 30},
]

print("="*60)
print("PULSE-CHENNAI HARDWARE TELEMETRY SIMULATOR")
print(f"Target API: {API_URL}")
print("="*60)

step = 0
while True:
    print(f"\n--- Simulation Step {step} ---")
    
    for bus in buses:
        # Calculate current position
        current_bus_step = (step + bus["step_offset"]) % TOTAL_STEPS
        current_lat = interpolate(START_LAT, END_LAT, current_bus_step, TOTAL_STEPS)
        current_lng = interpolate(START_LNG, END_LNG, current_bus_step, TOTAL_STEPS)
        
        # Add slight natural GPS jitter
        current_lat += random.uniform(-0.0002, 0.0002)
        current_lng += random.uniform(-0.0002, 0.0002)
        
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
            if resp.status_code == 200:
                data = resp.json()
                if is_failing:
                    print(f"🚨 [GHOST EVENT] {bus['id']} -> Sent corrupted data. API classified as Ghost: {data.get('is_ghost')}")
                else:
                    print(f"✅ [OK] {bus['id']} -> Sent healthy telemetry.")
            else:
                print(f"❌ [HTTP ERROR] {bus['id']} -> {resp.status_code}")
        except requests.exceptions.ConnectionError:
            print("❌ Backend is not running! Please start 'python -m pulse_chennai.api.dashboard_server'")
            time.sleep(2)
            break
            
    step += 1
    time.sleep(1) # Send pings every 1 second
