"""
GPS Telemetry Ingestion Route (Supabase Edition)
====================================================
POST /api/ingest — receives raw GPS pings from AIS-140 devices or the simulator.
Runs hardware reliability scorer, upserts to Supabase.
"""

import time
import logging
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Ingestion"])

# Stateful scorer singleton
from hardware.reliability_scorer import HardwareReliabilityScorer
_scorer = HardwareReliabilityScorer(decay_rate=0.3)


class GPSPingRequest(BaseModel):
    """Incoming GPS telemetry from an AIS-140 device."""
    bus_id: Optional[str] = Field(None, description="Bus ID")
    device_id: Optional[str] = Field(None, description="Device ID (legacy)")
    lat: float = Field(..., ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    speed: float = Field(0, ge=0)
    heading: float = Field(0, ge=0, le=360)
    route: str = Field("")
    timestamp: Optional[float] = None

    def get_bus_id(self) -> str:
        return self.bus_id or self.device_id or "unknown"

    def get_lng(self) -> float:
        return self.lng if self.lng is not None else (self.lon or 0)


@router.post("/ingest")
async def ingest_gps_ping(ping: GPSPingRequest):
    """Ingest a GPS ping: score reliability, upsert to Supabase."""
    from infrastructure.supabase_client import get_supabase

    bid = ping.get_bus_id()
    lng_val = ping.get_lng()
    ts = ping.timestamp or (time.time() * 1000)

    # Run hardware reliability scorer
    score = _scorer.score_ping(
        bus_id=bid,
        lat=ping.lat,
        lng=lng_val,
        timestamp=ts,
        speed=ping.speed,
    )

    is_ghost = score < 0.4

    # Upsert to Supabase
    supabase = get_supabase()
    if supabase:
        try:
            supabase.table("buses").upsert({
                "id": bid,
                "route": ping.route,
                "lat": ping.lat,
                "lng": lng_val,
                "speed": ping.speed,
                "heading": ping.heading,
                "reliability_score": round(score, 4),
                "is_ghost": is_ghost,
                "last_seen": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }, on_conflict="id").execute()
        except Exception as e:
            logger.warning(f"Supabase upsert failed: {e}")

    return {
        "received": True,
        "bus_id": bid,
        "reliability_score": round(score, 4),
        "is_ghost": is_ghost,
    }
