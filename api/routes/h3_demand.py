"""
H3 Demand Endpoints
====================
POST /api/passenger-ping   — Accept a crowdsourced passenger ping
GET  /api/h3-demand        — Return aggregated hex demand data
"""

from fastapi import APIRouter
from pydantic import BaseModel
from app.services.h3_demand import record_ping, get_demand_hexes

router = APIRouter()


class PassengerPing(BaseModel):
    lat: float
    lng: float
    resolution: int = 8


@router.post("/api/passenger-ping")
async def passenger_ping(ping: PassengerPing):
    """Accept a crowdsourced passenger ping and bin it into an H3 hex cell."""
    hex_id = record_ping(ping.lat, ping.lng, ping.resolution)
    return {"status": "ok", "hex_id": hex_id}


@router.get("/api/h3-demand")
async def h3_demand():
    """Return H3 hex demand data for the last 10 minutes."""
    hexes = get_demand_hexes()
    return {
        "hexes": hexes,
        "total_hexes": len(hexes),
        "total_pings": sum(h["count"] for h in hexes),
    }
