import logging
import requests
from config import get_settings
from traffic.ml_eta_predictor import get_predictor

logger = logging.getLogger(__name__)

settings = get_settings()

def get_optimal_route(start_lat: float, start_lon: float, end_lat: float, end_lon: float, hour: int) -> dict:
    """
    Synchronous ML and Routing Engine logic for the Celery Worker.
    Fetches exact routes from OSRM and runs an ETA Prediction model.
    """
    url = (
        f"{settings.OSRM_BASE_URL}/route/v1/driving/"
        f"{start_lon},{start_lat};{end_lon},{end_lat}"
        f"?overview=full&geometries=geojson&steps=false"
    )
    
    try:
        resp = requests.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("code") != "Ok" or not data.get("routes"):
            return {"status": "error", "message": "OSRM routing failed to find a valid route."}
            
        route = data["routes"][0]
        
        # OSRM returns duration in seconds, distance in meters
        distance_km = round(route["distance"] / 1000.0, 2)
        osrm_eta_min = route["duration"] / 60.0
        
        # ─────────────────────────────────────────────────────────────────
        # ML ETA Engine — ensemble prediction with traffic correction
        # ─────────────────────────────────────────────────────────────────
        try:
            predictor = get_predictor()
            ml_result = predictor.predict(
                src_lat=start_lat,
                src_lon=start_lon,
                dst_lat=end_lat,
                dst_lon=end_lon,
                current_speed_kmph=None,
            )
            ml_eta_prediction = round(ml_result["eta_minutes"], 2)
            logger.info(
                "ML ETA: %.2f min (method=%s, confidence=%.3f, OSRM=%.2f min)",
                ml_eta_prediction,
                ml_result.get("method", "unknown"),
                ml_result.get("confidence", 0),
                osrm_eta_min,
            )
        except Exception as ml_err:
            logger.warning("ML ETA prediction failed, falling back to OSRM×1.15: %s", ml_err)
            ml_eta_prediction = round(osrm_eta_min * 1.15, 2)
        
        # Route geometry (list of [lon, lat])
        # GeoJSON LineString coordinates are [lon, lat]
        coordinates = route["geometry"]["coordinates"]
        
        # PostGIS requires WKT: LINESTRING(lon lat, lon lat, ...)
        # The worker.py expects a list of tuples, but since GeoJSON gives [lon, lat],
        # let's return it exactly how worker expects to build its WKT.
        # Worker expects route_coords elements returning (lat, lon) or (lon, lat).
        # We will standardize on a list of `(lon, lat)` to easily convert to WKT string.
        
        route_coords = coordinates # list of [lon, lat]

        return {
            "status": "success",
            "distance_km": distance_km,
            "eta_minutes": ml_eta_prediction,
            "route_coords": route_coords
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
