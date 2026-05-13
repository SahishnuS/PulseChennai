import os
import sys
import time
import random
import logging
from datetime import datetime, timedelta
import pandas as pd

# Ensure pulse_chennai is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph.h3_utils import latlng_to_h3
from infrastructure.local_data_lake import local_data_lake

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BUSES = [
    {"id": "MTC-19-001",   "lat": 12.7260, "lng": 80.1893},
    {"id": "MTC-102X-002", "lat": 12.7260, "lng": 80.1893},
]

def generate_trajectories(days=5):
    logger.info(f"Generating {days} days of sample trajectories...")
    now = datetime.now()
    start_time = now - timedelta(days=days)
    
    records = []
    
    for bus in BUSES:
        lat = bus["lat"]
        lng = bus["lng"]
        
        # 1000 pings per day per bus
        pings_per_day = 1000
        time_step = timedelta(seconds=(24 * 3600) / pings_per_day)
        
        current_time = start_time
        for day in range(days):
            for i in range(pings_per_day):
                # Simulate movement
                lat += random.uniform(-0.0005, 0.0005)
                lng += random.uniform(-0.0005, 0.0005)
                
                # Keep within Chennai bounds
                lat = max(12.7, min(13.3, lat))
                lng = max(79.9, min(80.5, lng))
                
                # Vary speed by time of day (slower in rush hours)
                hour = current_time.hour
                if 8 <= hour <= 11 or 17 <= hour <= 20:
                    speed = random.uniform(5, 20)
                else:
                    speed = random.uniform(20, 50)
                
                ts_ms = int(current_time.timestamp() * 1000)
                h3_l9 = latlng_to_h3(lat, lng, 9)
                h3_l8 = latlng_to_h3(lat, lng, 8)
                
                records.append({
                    "trip_id": bus["id"],
                    "timestamp_ms": ts_ms,
                    "lat": lat,
                    "lng": lng,
                    "speed_kmh": speed,
                    "heading_deg": random.uniform(0, 360),
                    "passenger_count": random.randint(10, 60),
                    "h3_l9": h3_l9,
                    "h3_l8": h3_l8,
                    "date": current_time.strftime("%Y-%m-%d")
                })
                current_time += time_step
                
    df = pd.DataFrame(records)
    logger.info(f"Generated {len(df)} total trajectory points.")
    
    # Save to local data lake
    success = local_data_lake.write_trajectories(df)
    if success:
        logger.info("Sample data generation complete.")
    else:
        logger.error("Failed to write sample data.")

if __name__ == "__main__":
    generate_trajectories(days=5)
