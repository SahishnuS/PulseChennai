"""
Pulse-Chennai: Road-Aware Routing Service
==========================================
Uses the TomTom Routing API to compute street-following paths between sequential bus stops,
with local memory/Redis caching and automatic route regeneration on stop changes.
"""

import os
import httpx
import hashlib
import json
import logging
import math
from datetime import datetime
from typing import List, Tuple, Dict, Any, Optional

from infrastructure import upstash_redis
from infrastructure.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# Fallback stops dictionary to keep the system operational if DB is empty/offline
FALLBACK_ROUTES = {
    "19": [
        {"id": "STOP_THIRUPORUR_19", "name": "Thiruporur", "lat": 12.7275, "lng": 80.1989, "sequence": 1},
        {"id": "STOP_KELAMBAKKAM_19", "name": "Kelambakkam", "lat": 12.7915, "lng": 80.2185, "sequence": 2},
        {"id": "STOP_SIRUSERI_19", "name": "Siruseri", "lat": 12.8361, "lng": 80.2199, "sequence": 3},
        {"id": "STOP_SHOLINGANALLUR_19", "name": "Sholinganallur", "lat": 12.8988, "lng": 80.2281, "sequence": 4},
        {"id": "STOP_THIRUVANMIYUR_19", "name": "Thiruvanmiyur Terminus", "lat": 12.9824, "lng": 80.2588, "sequence": 5},
        {"id": "STOP_SAIDAPET_19", "name": "Saidapet", "lat": 13.0182, "lng": 80.2213, "sequence": 6},
        {"id": "STOP_T_NAGAR_19", "name": "T Nagar Bus Terminus", "lat": 13.0418, "lng": 80.2341, "sequence": 7},
    ],
    "102X": [
        {"id": "STOP_KELAMBAKKAM_102X", "name": "Kelambakkam", "lat": 12.7915, "lng": 80.2185, "sequence": 1},
        {"id": "STOP_SIRUSERI_102X", "name": "Siruseri", "lat": 12.8361, "lng": 80.2199, "sequence": 2},
        {"id": "STOP_SHOLINGANALLUR_102X", "name": "Sholinganallur", "lat": 12.8988, "lng": 80.2281, "sequence": 3},
        {"id": "STOP_THORAIPAKKAM_102X", "name": "Thoraipakkam", "lat": 12.9379, "lng": 80.2366, "sequence": 4},
        {"id": "STOP_PERUNGUDI_102X", "name": "Perungudi", "lat": 12.9649, "lng": 80.2450, "sequence": 5},
        {"id": "STOP_ADYAR_102X", "name": "Adyar Depot", "lat": 13.0012, "lng": 80.2565, "sequence": 6},
        {"id": "STOP_SANTHOME_102X", "name": "Santhome", "lat": 13.0326, "lng": 80.2783, "sequence": 7},
        {"id": "STOP_BROADWAY_102X", "name": "Broadway", "lat": 13.0886, "lng": 80.2872, "sequence": 8},
    ],
    "515": [
        {"id": "STOP_TAMBARAM_515", "name": "Tambaram West", "lat": 12.9249, "lng": 80.1000, "sequence": 1},
        {"id": "STOP_PERUNGULATTUR_515", "name": "Perungulattur", "lat": 12.9048, "lng": 80.0894, "sequence": 2},
        {"id": "STOP_VANDALUR_ZOO_515", "name": "Vandalur Zoo", "lat": 12.8872, "lng": 80.0832, "sequence": 3},
        {"id": "STOP_MAMBAKKAM_515", "name": "Mambakkam", "lat": 12.8344, "lng": 80.1500, "sequence": 4},
        {"id": "STOP_KELAMBAKKAM_515", "name": "Kelambakkam", "lat": 12.7915, "lng": 80.2185, "sequence": 5},
        {"id": "STOP_THIRUPORUR_515", "name": "Thiruporur", "lat": 12.7275, "lng": 80.1989, "sequence": 6},
        {"id": "STOP_MAMALLAPURAM_515", "name": "Mamallapuram", "lat": 12.6208, "lng": 80.1945, "sequence": 7},
    ],
    "21C": [
        {"id": "STOP_KOYAMBEDU_21C", "name": "Koyambedu CMBT", "lat": 13.0694, "lng": 80.1948, "sequence": 1},
        {"id": "STOP_VADAPALANI_21C", "name": "Vadapalani", "lat": 13.0526, "lng": 80.2104, "sequence": 2},
        {"id": "STOP_ASHOK_PILLAR_21C", "name": "Ashok Pillar", "lat": 13.0354, "lng": 80.2124, "sequence": 3},
        {"id": "STOP_GUINDY_21C", "name": "Guindy", "lat": 13.0084, "lng": 80.2131, "sequence": 4},
        {"id": "STOP_MADHYA_KAILASH_21C", "name": "Madhya Kailash", "lat": 13.0063, "lng": 80.2443, "sequence": 5},
        {"id": "STOP_ADYAR_DEPOT_21C", "name": "Adyar Depot", "lat": 13.0012, "lng": 80.2565, "sequence": 6},
        {"id": "STOP_ADYAR_21C", "name": "Adyar", "lat": 12.9953, "lng": 80.2538, "sequence": 7},
    ],
    "70": [
        {"id": "STOP_CENTRAL_70", "name": "Chennai Central", "lat": 13.0827, "lng": 80.2756, "sequence": 1},
        {"id": "STOP_PERAMBUR_70", "name": "Perambur", "lat": 13.1082, "lng": 80.2467, "sequence": 2},
        {"id": "STOP_VILLIVAKKAM_70", "name": "Villivakkam", "lat": 13.1030, "lng": 80.2039, "sequence": 3},
        {"id": "STOP_DUNLOP_70", "name": "Dunlop", "lat": 13.1091, "lng": 80.1700, "sequence": 4},
        {"id": "STOP_AMBATTUR_70", "name": "Ambattur", "lat": 13.1017, "lng": 80.1611, "sequence": 5},
    ],
    "47A": [
        {"id": "STOP_TNAGAR_47A", "name": "T Nagar Bus Terminus", "lat": 13.0418, "lng": 80.2341, "sequence": 1},
        {"id": "STOP_SAIDAPET_47A", "name": "Saidapet", "lat": 13.0182, "lng": 80.2213, "sequence": 2},
        {"id": "STOP_GUINDY_47A", "name": "Guindy", "lat": 13.0084, "lng": 80.2131, "sequence": 3},
        {"id": "STOP_MEENAMBAKKAM_47A", "name": "Meenambakkam", "lat": 12.9868, "lng": 80.1762, "sequence": 4},
        {"id": "STOP_PALLAVARAM_47A", "name": "Pallavaram", "lat": 12.9675, "lng": 80.1491, "sequence": 5},
        {"id": "STOP_CHROMEPET_47A", "name": "Chromepet", "lat": 12.9560, "lng": 80.1435, "sequence": 6},
    ]
}


def encode_polyline(points: List[Tuple[float, float]]) -> str:
    """
    Encodes a list of coordinate tuples (latitude, longitude) into a Google Polyline string (precision 5).
    """
    def encode_value(val: int) -> str:
        # Convert to two's complement if negative
        val = ~(val << 1) if val < 0 else (val << 1)
        chunks = []
        while val >= 0x20:
            chunks.append(chr((0x20 | (val & 0x1f)) + 63))
            val >>= 5
        chunks.append(chr(val + 63))
        return "".join(chunks)

    encoded = []
    last_lat = 0
    last_lng = 0
    for lat, lng in points:
        lat_int = int(round(lat * 1e5))
        lng_int = int(round(lng * 1e5))
        encoded.append(encode_value(lat_int - last_lat))
        encoded.append(encode_value(lng_int - last_lng))
        last_lat = lat_int
        last_lng = lng_int

    return "".join(encoded)


def decode_polyline(encoded: str) -> List[Tuple[float, float]]:
    """
    Decodes a Google Polyline string (precision 5) into a list of (latitude, longitude) tuples.
    """
    coords = []
    index = 0
    lat = 0
    lng = 0

    while index < len(encoded):
        shift = 0
        result = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1f) << shift
            shift += 5
            if byte < 0x20:
                break
        lat_change = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += lat_change

        shift = 0
        result = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1f) << shift
            shift += 5
            if byte < 0x20:
                break
        lng_change = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += lng_change

        coords.append((lat / 1e5, lng / 1e5))

    return coords


async def get_route_stops(route_id: str) -> List[Dict[str, Any]]:
    """
    Fetch stops for a route ordered by sequence from Supabase, or fall back to local seed data.
    """
    # Clean route key for lookup
    clean_route = route_id.upper().strip()
    
    supabase = get_supabase()
    if supabase:
        try:
            result = (
                supabase.table("stops")
                .select("*")
                .eq("route", clean_route)
                .order("sequence")
                .execute()
            )
            if result.data and len(result.data) > 0:
                return result.data
        except Exception as e:
            logger.warning(f"Failed to fetch stops for {clean_route} from Supabase: {e}")

    # Fallback to local hardcoded stops
    if clean_route in FALLBACK_ROUTES:
        logger.info(f"Using fallback stops for route {clean_route}")
        return FALLBACK_ROUTES[clean_route]

    return []


def get_fallback_segment(lat_A: float, lng_A: float, lat_B: float, lng_B: float) -> Dict[str, Any]:
    """Build a straight-line fallback segment."""
    points = [(lat_A, lng_A), (lat_B, lng_B)]
    # Haversine distance in meters
    dy = (lat_B - lat_A) * 111132.0
    dx = (lng_B - lng_A) * 111132.0 * math.cos(math.radians(lat_A))
    distance = math.sqrt(dx*dx + dy*dy)
    # Estimate time at 25 km/h (6.94 m/s)
    duration = distance / 6.94
    return {
        "polyline": encode_polyline(points),
        "distance_meters": int(distance),
        "duration_seconds": int(duration),
        "fallback": True
    }


async def get_route_geometry(route_id: str) -> Dict[str, Any]:
    """
    Retrieve or calculate road-aware geometry for a bus route.
    Calculates route leg-by-leg between consecutive stops, caching segments in Upstash Redis and Supabase.
    """
    clean_route = route_id.upper().strip()
    stops = await get_route_stops(clean_route)
    if not stops:
        return {"route_id": clean_route, "geometry": [], "encoded_polyline": "", "error": "No stops found"}

    # Generate MD5 hash of stop locations and order to detect route change
    stops_str = "".join([f"{s.get('id', '')}:{float(s['lat']):.5f},{float(s['lng']):.5f}" for s in stops])
    stops_hash = hashlib.md5(stops_str.encode("utf-8")).hexdigest()

    cache_key = f"route:geometry:{clean_route}"
    
    # Try Upstash Redis cache first for the entire route geometry
    try:
        cached_data = await upstash_redis.get_json(cache_key)
        if cached_data and cached_data.get("stops_hash") == stops_hash:
            logger.info(f"Cache hit for full route geometry: {clean_route}")
            return cached_data
    except Exception as e:
        logger.warning(f"Redis lookup failed for route {clean_route}: {e}")

    # Check Supabase route_polylines table as secondary cache
    supabase = get_supabase()
    if supabase:
        try:
            result = supabase.table("route_polylines").select("*").eq("route_id", clean_route).execute()
            if result.data and result.data[0].get("stops_hash") == stops_hash:
                logger.info(f"Supabase hit for full route geometry: {clean_route}")
                coords = decode_polyline(result.data[0]["polyline"])
                geometry_coords = [[lng, lat] for lat, lng in coords]
                
                route_data = {
                    "route_id": clean_route,
                    "geometry": geometry_coords,
                    "encoded_polyline": result.data[0]["polyline"],
                    "stops_hash": stops_hash,
                    "length_meters": result.data[0].get("length_meters", 0),
                    "duration_seconds": result.data[0].get("duration_seconds", 0)
                }
                try:
                    await upstash_redis.set_json(cache_key, route_data, ex=86400 * 7)
                except:
                    pass
                return route_data
        except Exception as e:
            logger.debug(f"Supabase route_polylines query failed (table may not exist): {e}")

    # Not found in cache. Calculate leg-by-leg
    logger.info(f"Calculating route geometry leg-by-leg for: {clean_route}")
    
    all_coords = []
    legs_points = []
    total_length = 0
    total_duration = 0
    api_key = os.getenv("VITE_TOMTOM_API_KEY")

    for i in range(len(stops) - 1):
        stop_A = stops[i]
        stop_B = stops[i+1]
        id_A = stop_A.get("id", f"STOP_{i}")
        id_B = stop_B.get("id", f"STOP_{i+1}")
        lat_A, lng_A = float(stop_A["lat"]), float(stop_A["lng"])
        lat_B, lng_B = float(stop_B["lat"]), float(stop_B["lng"])

        # Try to get from Redis segment cache
        seg_cache_key = f"route:segment:{id_A}:{id_B}"
        segment = None
        try:
            segment = await upstash_redis.get_json(seg_cache_key)
        except Exception as e:
            logger.warning(f"Redis segment fetch failed: {e}")

        # Try to get from Supabase cached_route_segments table
        if not segment and supabase:
            try:
                result = supabase.table("cached_route_segments").select("*").eq("start_stop_id", id_A).eq("end_stop_id", id_B).execute()
                if result.data:
                    segment = result.data[0]
            except Exception as e:
                logger.debug(f"Supabase segment query failed (table may not exist): {e}")

        if not segment:
            # Query TomTom API for this specific leg
            logger.info(f"Querying TomTom for leg: {id_A} -> {id_B}")
            if not api_key:
                logger.error("VITE_TOMTOM_API_KEY environment variable is missing")
                segment = get_fallback_segment(lat_A, lng_A, lat_B, lng_B)
            else:
                try:
                    url = f"https://api.tomtom.com/routing/1/calculateRoute/{lat_A},{lng_A}:{lat_B},{lng_B}/json"
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            url,
                            params={"key": api_key, "travelMode": "car", "routeType": "fastest"},
                            timeout=6.0
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            route = data["routes"][0]
                            summary = route["summary"]
                            points = [(pt["latitude"], pt["longitude"]) for pt in route["legs"][0]["points"]]
                            encoded = encode_polyline(points)
                            segment = {
                                "polyline": encoded,
                                "distance_meters": summary["lengthInMeters"],
                                "duration_seconds": summary["travelTimeInSeconds"]
                            }
                            logger.info(f"  TomTom leg success: {summary['lengthInMeters']}m, {summary['travelTimeInSeconds']}s")
                        else:
                            logger.warning(f"  TomTom leg failed with status {resp.status_code}. Using fallback.")
                            segment = get_fallback_segment(lat_A, lng_A, lat_B, lng_B)
                except Exception as e:
                    logger.warning(f"  TomTom leg request failed: {e}. Using fallback.")
                    segment = get_fallback_segment(lat_A, lng_A, lat_B, lng_B)

            # Save to segment cache (Redis & Supabase)
            try:
                await upstash_redis.set_json(seg_cache_key, segment, ex=86400 * 30) # Cache segments for 30 days
            except:
                pass

            if supabase:
                try:
                    supabase.table("cached_route_segments").insert({
                        "start_stop_id": id_A,
                        "end_stop_id": id_B,
                        "polyline": segment["polyline"],
                        "distance_meters": int(segment["distance_meters"]),
                        "duration_seconds": int(segment["duration_seconds"])
                    }).execute()
                except Exception as e:
                    logger.debug(f"Supabase segment insert skipped (table may not exist): {e}")

        # Decode segment polyline and accumulate
        leg_pts = decode_polyline(segment["polyline"])
        legs_points.append(leg_pts)
        total_length += segment["distance_meters"]
        total_duration += segment["duration_seconds"]

    # Combine all legs
    for idx, leg_pts in enumerate(legs_points):
        if idx == 0:
            all_coords.extend(leg_pts)
        else:
            all_coords.extend(leg_pts[1:]) # Avoid duplicating boundary points

    encoded_full = encode_polyline(all_coords)
    geometry_coords = [[lng, lat] for lat, lng in all_coords]

    route_data = {
        "route_id": clean_route,
        "geometry": geometry_coords,
        "encoded_polyline": encoded_full,
        "stops_hash": stops_hash,
        "length_meters": total_length,
        "duration_seconds": total_duration,
        "legs": [[ [pt[1], pt[0]] for pt in leg ] for leg in legs_points]
    }

    # Cache full route geometry in Redis & Supabase
    try:
        await upstash_redis.set_json(cache_key, route_data, ex=86400 * 7)
    except:
        pass

    if supabase:
        try:
            supabase.table("route_polylines").upsert({
                "route_id": clean_route,
                "polyline": encoded_full,
                "stops_hash": stops_hash,
                "length_meters": int(total_length),
                "duration_seconds": int(total_duration),
                "updated_at": datetime.now().isoformat()
            }, on_conflict="route_id").execute()
        except Exception as e:
            logger.debug(f"Supabase route_polylines upsert skipped (table may not exist): {e}")

    logger.info(f"Successfully calculated and cached road geometry for route {clean_route} ({total_length} meters)")
    return route_data


async def get_route_path(route_id: str, reversed_direction: bool = False) -> Tuple[List[Tuple[float, float]], List[int]]:
    """
    Get the flat coordinate sequence (waypoints) for the route, along with the stop index mapping for each point.
    Returns (waypoints, stop_indices) where:
      - waypoints: List of (lat, lng) tuples.
      - stop_indices: List of integers of same size as waypoints, mapping each waypoint to the stop sequence index.
    This is designed specifically to be consumed by the bus simulator.
    """
    clean_route = route_id.upper().strip()
    route_data = await get_route_geometry(clean_route)
    
    # Extract points from legs if available, otherwise build from coordinates directly
    waypoints: List[Tuple[float, float]] = []
    stop_indices: List[int] = []
    
    if "legs" in route_data and len(route_data["legs"]) > 0:
        legs = route_data["legs"]
        for leg_idx, leg in enumerate(legs):
            # For each coordinate in this leg, it represents the path between stop `leg_idx` and `leg_idx + 1`
            for pt in leg:
                # leg pt is in [lng, lat] format
                waypoints.append((pt[1], pt[0]))
                stop_indices.append(leg_idx)
        # Append the final destination stop coordinate to complete the path
        if legs:
            last_pt = legs[-1][-1]
            waypoints.append((last_pt[1], last_pt[0]))
            stop_indices.append(len(legs))
    else:
        # Fallback to stop-to-stop straight lines
        stops = await get_route_stops(clean_route)
        for i, s in enumerate(stops):
            waypoints.append((float(s["lat"]), float(s["lng"])))
            stop_indices.append(i)

    # Handle reversed direction simulation (e.g. BUS_21B_002 running Tambaram -> Central)
    if reversed_direction:
        waypoints = list(reversed(waypoints))
        # When reversed, stop index needs to count down: len(stops) - 1 - idx
        max_idx = max(stop_indices) if stop_indices else 0
        stop_indices = [max_idx - idx for idx in reversed(stop_indices)]

    return waypoints, stop_indices
