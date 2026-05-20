"""
Polylines Router
==================
GET /api/polylines — returns road-snapped coordinates for routes 19, 102X, 515.

The handler delegates to the road_polyline service which:
  1. Checks Upstash Redis for a 24-hour cached result.
  2. Fetches from the public OSRM API on a cache miss.
  3. Falls back to straight-line stop coordinates if OSRM is unreachable.

Response shape
--------------
{
  "routes": {
    "19":   [[lat, lng], ...],
    "102X": [[lat, lng], ...],
    "515":  [[lat, lng], ...]
  },
  "cached": true | false,     # best-effort flag (True if all from cache)
  "point_counts": {
    "19":   <int>,
    "102X": <int>,
    "515":  <int>
  }
}
"""

import logging
import sys
import os

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Polylines"])

# Make sure the project root is on sys.path so absolute imports work regardless
# of how uvicorn was launched.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


@router.get("/polylines")
async def get_polylines():
    """
    Return road-snapped polyline coordinates for the three active MTC routes
    (19, 102X, 515), cached in Upstash Redis for 24 hours.
    """
    try:
        from app.services.road_polyline import get_all_route_polylines

        polylines = await get_all_route_polylines()

        # Convert tuples to plain lists for JSON serialisation
        routes_out = {
            route_id: [[lat, lng] for lat, lng in coords]
            for route_id, coords in polylines.items()
        }

        return {
            "routes": routes_out,
            "point_counts": {rid: len(pts) for rid, pts in routes_out.items()},
        }

    except Exception as exc:
        logger.error("Failed to fetch polylines: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Polyline fetch failed: {exc}")
