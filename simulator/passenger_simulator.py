import asyncio
import random
import time
import uuid
import httpx
import logging
from typing import Dict, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

API_URL = "http://localhost:8001/api/passenger-ping"

# Target buses — Route 19 and Route 102X
TARGET_BUSES = [
    {"id": "MTC-19-001",   "base_lat": 12.7260, "base_lng": 80.1893},
    {"id": "MTC-102X-002", "base_lat": 12.7260, "base_lng": 80.1893},
]

class Passenger:
    def __init__(self, bus_id: str, base_lat: float, base_lng: float):
        self.session_token = f"pax_{uuid.uuid4().hex[:8]}"
        self.bus_id = bus_id
        self.lat = base_lat
        self.lng = base_lng
        # Random initial offset (up to ~10 meters)
        self.lat_offset = random.uniform(-0.0001, 0.0001)
        self.lng_offset = random.uniform(-0.0001, 0.0001)

    def update_position(self, bus_lat: float, bus_lng: float):
        # Follow the bus, with some GPS noise
        noise_lat = random.uniform(-0.00005, 0.00005)
        noise_lng = random.uniform(-0.00005, 0.00005)
        self.lat = bus_lat + self.lat_offset + noise_lat
        self.lng = bus_lng + self.lng_offset + noise_lng

    def get_ping(self) -> dict:
        return {
            "session_token": self.session_token,
            "lat": self.lat,
            "lng": self.lng,
            "timestamp": time.time() * 1000,
            "device_os": random.choice(["android", "ios"]),
        }

async def fetch_bus_positions() -> Dict[str, tuple]:
    """Fetch current bus positions from the dashboard API to follow them."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8001/api/buses", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                # Return dict of {bus_id: (lat, lng)}
                return {b["trip_id"]: (b["lat"], b["lng"]) for b in data.get("buses", [])}
    except Exception as e:
        logger.debug(f"Could not fetch bus positions: {e}")
    return {}

async def simulate_passengers():
    logger.info("Starting Collaborative Telemetry Passenger Simulator...")

    # Create 3-8 passengers per bus
    passengers: List[Passenger] = []
    for bus in TARGET_BUSES:
        num_pax = random.randint(3, 8)
        for _ in range(num_pax):
            passengers.append(Passenger(bus["id"], bus["base_lat"], bus["base_lng"]))

    logger.info(f"Created {len(passengers)} simulated passengers across {len(TARGET_BUSES)} buses.")

    async with httpx.AsyncClient() as client:
        while True:
            # 1. Get real bus positions to follow
            bus_positions = await fetch_bus_positions()

            # 2. Update and send ping for each passenger
            for pax in passengers:
                # If we know where the bus is, follow it
                if pax.bus_id in bus_positions:
                    bus_lat, bus_lng = bus_positions[pax.bus_id]
                    pax.update_position(bus_lat, bus_lng)

                # Send ping
                try:
                    resp = await client.post(API_URL, json=pax.get_ping(), timeout=2.0)
                    if resp.status_code not in (200, 202):
                        logger.warning(f"Failed to send passenger ping: {resp.status_code}")
                except Exception as e:
                    logger.debug(f"Ping error: {e}")

            logger.info(f"Sent pings for {len(passengers)} passengers.")
            await asyncio.sleep(3.0)  # Send every 3 seconds

if __name__ == "__main__":
    try:
        asyncio.run(simulate_passengers())
    except KeyboardInterrupt:
        logger.info("Passenger simulator stopped.")
