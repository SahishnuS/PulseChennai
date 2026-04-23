"""
Pulse-Chennai Functional Demonstration
======================================
This script demonstrates the core logical flow of the system
without requiring the 2.5GB+ PyTorch/CUDA installation.
"""

import time
import json
from dataclasses import dataclass
from typing import Optional

# -- Mocking the schemas and logic we built --

@dataclass
class H3Prediction:
    h3_index: str
    lat: float
    lng: float
    confidence: float

def simulate_hardware_scorer(speed: float, jitter: float, age_s: float) -> float:
    """Simulates the HardwareReliabilityScorer logic we wrote."""
    score = 1.0
    if speed > 100: score -= 0.5  # Impossible speed in Chennai traffic
    if jitter > 50: score -= 0.3  # Jumping around
    if age_s > 60: score -= 0.8   # Stale ping
    return max(0.0, score)

def simulate_pipeline(trip_id: str, lat: float, lng: float, speed: float, jitter: float, age_s: float):
    print(f"\n[1] Ingesting GPS Ping from {trip_id} @ ({lat:.4f}, {lng:.4f})")
    
    # 1. Hardware Scoring
    hw_score = simulate_hardware_scorer(speed, jitter, age_s)
    print(f"    ├─ AI Hardware Audit: Speed={speed}km/h, Jitter={jitter}m, Staleness={age_s}s")
    print(f"    └─ Reliability Score: {hw_score:.2f}/1.00")
    
    # 2. Decision Logic
    if hw_score < 0.3:
        print(f"\n[2] 🚨 GHOST BUS DETECTED! (Score {hw_score:.2f} < Threshold 0.3)")
        print("    ├─ Action: Suppressing faulty AIS 140 device...")
        print("    └─ Action: Triggering Collaborative Telemetry (Passenger Pings)...")
        time.sleep(1)
        
        print("\n[3] Executing Ghost Bus Recovery Module")
        print("    ├─ Scanning nearby H3 cells for passenger smartphone pings...")
        print("    ├─ Found 14 passenger pings tracing route 21G.")
        print("    └─ Executing GNN Latent State inference...")
        time.sleep(1)
        
        # 3. Model Output Simulation
        res = {
            "trip_id": trip_id,
            "status": "recovered",
            "estimated_h3": "896181b6b23ffff",
            "lat": lat + 0.001,
            "lng": lng + 0.002,
            "snapped_road": "Anna Salai (T. Nagar)",
            "confidence": 0.87,
            "data_source": "collaborative_telemetry_gnn",
            "eta_seconds": 340
        }
    else:
        print(f"\n[2] ✅ Hardware Healthy (Score {hw_score:.2f} > 0.3)")
        print("    ├─ Action: Executing Standard GNN Forward Pass...")
        time.sleep(1)
        
        print("\n[3] HMM Map-Matching & ETA Prediction")
        print("    ├─ Converting lat/lng to H3 Hex (Resolution 9)...")
        print("    ├─ GAT Attention Layer weighting high congestion cells...")
        print("    └─ Viterbi algorithm snapping point to road segment...")
        time.sleep(1)
        
        res = {
            "trip_id": trip_id,
            "h3_index": "896181b6b23ffff",
            "snapped_lat": lat + 0.0001,
            "snapped_lng": lng + 0.0001,
            "snapped_road": "Mount Road",
            "confidence": 0.98,
            "data_source": "gnn_inference",
            "hw_reliability_score": hw_score,
            "eta_seconds": 120
        }
        
    print("\n[4] API Response to Frontend:")
    print(json.dumps(res, indent=4))
    print("="*60)

if __name__ == "__main__":
    print("\n" + "="*60)
    print("PULSE-CHENNAI ENGINE DEMONSTRATION")
    print("="*60)
    
    # Scenario 1: Healthy Bus
    print("\n>>> SCENARIO 1: Healthy Bus Tracking")
    simulate_pipeline("bus_MTC_101", 13.0827, 80.2707, speed=25, jitter=5, age_s=2)
    
    time.sleep(2)
    
    # Scenario 2: Ghost Bus
    print("\n>>> SCENARIO 2: Ghost Bus Hardware Failure")
    simulate_pipeline("bus_MTC_404", 13.0827, 80.2707, speed=120, jitter=200, age_s=400)
