"""
Routes Endpoints
==================
GET /api/routes/{route_id}/geometry — returns the street-following geometry for a route
GET /api/routes/{route_id}/stops — returns the ordered list of stops for a route
"""

import logging
from fastapi import APIRouter, Path, HTTPException
from traffic import routing_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/routes", tags=["Routes"])


@router.get("/{route_id}/geometry")
async def get_route_geometry(
    route_id: str = Path(..., description="Route ID (e.g. 23C, 47A, 21B, M70)")
):
    """Get the road-following geometry coordinates for a route (GeoJSON-friendly [lng, lat] format)."""
    try:
        geometry = await routing_service.get_route_geometry(route_id)
        if not geometry or "geometry" not in geometry or len(geometry["geometry"]) == 0:
            raise HTTPException(status_code=404, detail=f"Geometry for route {route_id} not found")
        return geometry
    except Exception as e:
        logger.error(f"Failed to fetch geometry for route {route_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{route_id}/stops")
async def get_route_stops(
    route_id: str = Path(..., description="Route ID (e.g. 23C, 47A, 21B, M70)")
):
    """Get the sequential stops for a route."""
    try:
        stops = await routing_service.get_route_stops(route_id)
        if not stops:
            raise HTTPException(status_code=404, detail=f"Stops for route {route_id} not found")
        return {
            "route_id": route_id.upper().strip(),
            "count": len(stops),
            "stops": stops
        }
    except Exception as e:
        logger.error(f"Failed to fetch stops for route {route_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
