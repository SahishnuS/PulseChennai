"""
GPS Telemetry Ingestion Route
==============================
POST /api/ingest — receives raw GPS pings from AIS-140 devices or the simulator.
Publishes to Kafka (or processes directly if Kafka is unavailable).
Returns 202 Accepted immediately — processing is async.
"""

import time
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Ingestion"])


class GPSPingRequest(BaseModel):
    """Incoming GPS telemetry from an AIS-140 device."""
    device_id: str = Field(..., description="Bus device ID (e.g. MTC-21G-001)")
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(None, ge=-180, le=180)
    lon: float = Field(None, ge=-180, le=180)  # Accept both lng/lon
    speed: float = Field(0, ge=0, description="Speed in km/h")
    heading: float = Field(0, ge=0, le=360)
    jitter: float = Field(0, ge=0)
    age_s: float = Field(0, ge=0)
    route: str = Field("", description="Route ID")
    near: str = Field("", description="Nearest landmark")
    accuracy_m: float = Field(10.0)
    timestamp: Optional[float] = Field(None, description="Unix timestamp ms")

    def get_lng(self) -> float:
        return self.lng if self.lng is not None else (self.lon or 0)


class PassengerPingRequest(BaseModel):
    """Incoming passenger smartphone ping (anonymized)."""
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    accuracy_m: float = Field(10.0)
    session_token: str = Field(..., description="Random UUID, not tied to identity")


@router.post("/ingest", status_code=202)
async def ingest_gps_ping(ping: GPSPingRequest):
    """Ingest a single GPS ping. Publishes to Kafka for async processing."""
    from infrastructure import kafka_producer

    message = {
        "bus_id": ping.device_id,
        "lat": ping.lat,
        "lng": ping.get_lng(),
        "speed": ping.speed,
        "heading": ping.heading,
        "jitter": ping.jitter,
        "age_s": ping.age_s,
        "route_id": ping.route,
        "near": ping.near,
        "accuracy_m": ping.accuracy_m,
        "timestamp": ping.timestamp or (time.time() * 1000),
    }

    success = await kafka_producer.send_gps_ping(message)

    if success:
        return {"status": "accepted", "bus_id": ping.device_id, "pipeline": "kafka"}
    else:
        raise HTTPException(status_code=503, detail="Failed to queue GPS ping.")


@router.post("/passenger-ping", status_code=202)
async def ingest_passenger_ping(ping: PassengerPingRequest):
    """Ingest an anonymized passenger smartphone ping."""
    from infrastructure import kafka_producer

    message = {
        "lat": ping.lat,
        "lon": ping.lon,
        "accuracy_m": ping.accuracy_m,
        "session_token": ping.session_token,
        "timestamp": time.time() * 1000,
    }

    success = await kafka_producer.send_passenger_ping(message)

    if success:
        return {"status": "accepted", "session": ping.session_token}
    else:
        raise HTTPException(status_code=503, detail="Failed to queue passenger ping.")
