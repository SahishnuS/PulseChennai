"""
Seed Chennai MTC Bus Stops into Supabase
==========================================
Inserts hardcoded stop data for 3 routes (23C, 47A, 21B)
with real approximate coordinates and Tamil names.

Usage:
    python seed_stops.py
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("seed_stops")

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

ROUTES = {
    "23C": {
        "name": "Thiruvanmiyur → T Nagar",
        "stops": [
            {"id": "STOP_THIRUVANMIYUR", "name": "Thiruvanmiyur Terminus", "name_ta": "திருவான்மியூர் முனையம்", "lat": 12.9824, "lng": 80.2588, "sequence": 1},
            {"id": "STOP_LATTICE_BRIDGE", "name": "Lattice Bridge Road", "name_ta": "லாட்டிஸ் பிரிட்ஜ் சாலை", "lat": 12.9831, "lng": 80.2541, "sequence": 2},
            {"id": "STOP_ADYAR_SIGNAL", "name": "Adyar Signal", "name_ta": "அடையாறு சிக்னல்", "lat": 12.9799, "lng": 80.2576, "sequence": 3},
            {"id": "STOP_GANDHI_NAGAR", "name": "Gandhi Nagar", "name_ta": "காந்தி நகர்", "lat": 12.9836, "lng": 80.2463, "sequence": 4},
            {"id": "STOP_INDRA_NAGAR", "name": "Indra Nagar", "name_ta": "இந்திரா நகர்", "lat": 12.9901, "lng": 80.2378, "sequence": 5},
            {"id": "STOP_KOTTURPURAM", "name": "Kotturpuram", "name_ta": "கோட்டூர்புரம்", "lat": 12.9986, "lng": 80.2369, "sequence": 6},
            {"id": "STOP_SAIDAPET_23C", "name": "Saidapet", "name_ta": "சைதாப்பேட்டை", "lat": 13.0182, "lng": 80.2213, "sequence": 7},
            {"id": "STOP_MAMBALAM", "name": "Mambalam", "name_ta": "மாம்பலம்", "lat": 13.0365, "lng": 80.2129, "sequence": 8},
            {"id": "STOP_T_NAGAR", "name": "T Nagar Bus Terminus", "name_ta": "தியாகராய நகர் முனையம்", "lat": 13.0418, "lng": 80.2341, "sequence": 9},
        ]
    },
    "47A": {
        "name": "Anna Nagar → Koyambedu",
        "stops": [
            {"id": "STOP_ANNA_NAGAR_TOWER", "name": "Anna Nagar Tower", "name_ta": "அண்ணா நகர் கோபுரம்", "lat": 13.0891, "lng": 80.2101, "sequence": 1},
            {"id": "STOP_15TH_MAIN_ROAD", "name": "15th Main Road", "name_ta": "15வது பிரதான சாலை", "lat": 13.0842, "lng": 80.2089, "sequence": 2},
            {"id": "STOP_THIRUMANGALAM", "name": "Thirumangalam", "name_ta": "திருமங்கலம்", "lat": 13.0778, "lng": 80.2023, "sequence": 3},
            {"id": "STOP_KOYAMBEDU_CMBT", "name": "Koyambedu CMBT", "name_ta": "கோயம்பேடு CMBT", "lat": 13.0722, "lng": 80.1963, "sequence": 4},
            {"id": "STOP_KOYAMBEDU_MARKET", "name": "Koyambedu Market", "name_ta": "கோயம்பேடு சந்தை", "lat": 13.0698, "lng": 80.1944, "sequence": 5},
        ]
    },
    "21B": {
        "name": "Chennai Central → Tambaram",
        "stops": [
            {"id": "STOP_CHENNAI_CENTRAL", "name": "Chennai Central", "name_ta": "சென்னை சென்ட்ரல்", "lat": 13.0827, "lng": 80.2756, "sequence": 1},
            {"id": "STOP_PARK_TOWN", "name": "Park Town", "name_ta": "பார்க் டவுன்", "lat": 13.0792, "lng": 80.2731, "sequence": 2},
            {"id": "STOP_SAIDAPET_BRIDGE", "name": "Saidapet Bridge", "name_ta": "சைதாப்பேட்டை பாலம்", "lat": 13.0198, "lng": 80.2234, "sequence": 3},
            {"id": "STOP_CHROMPET", "name": "Chrompet", "name_ta": "குரோம்பேட்டை", "lat": 12.9516, "lng": 80.1430, "sequence": 4},
            {"id": "STOP_TAMBARAM", "name": "Tambaram", "name_ta": "தாம்பரம்", "lat": 12.9249, "lng": 80.1000, "sequence": 5},
        ]
    },
    "M70": {
        "name": "Adyar Signal → Chrompet",
        "stops": [
            {"id": "STOP_ADYAR", "name": "Adyar Signal", "name_ta": "அடையாறு சிக்னல்", "lat": 12.9799, "lng": 80.2576, "sequence": 1},
            {"id": "STOP_KOTTURPURAM", "name": "Kotturpuram", "name_ta": "கோட்டூர்புரம்", "lat": 12.9986, "lng": 80.2369, "sequence": 2},
            {"id": "STOP_SAIDAPET", "name": "Saidapet", "name_ta": "சைதாப்பேட்டை", "lat": 13.0182, "lng": 80.2213, "sequence": 3},
            {"id": "STOP_GUINDY", "name": "Guindy", "name_ta": "கிண்டி", "lat": 13.0066, "lng": 80.2206, "sequence": 4},
            {"id": "STOP_CHROMPET_M70", "name": "Chrompet", "name_ta": "குரோம்பேட்டை", "lat": 12.9516, "lng": 80.1430, "sequence": 5},
        ]
    },
}


def seed():
    from infrastructure.supabase_client import get_supabase

    supabase = get_supabase()
    if not supabase:
        logger.error("Supabase client not available. Check SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        sys.exit(1)

    total_inserted = 0

    for route_id, route_data in ROUTES.items():
        logger.info(f"Seeding route {route_id}: {route_data['name']}")

        for stop in route_data["stops"]:
            row = {
                "id": stop["id"],
                "route": route_id,
                "name": stop["name"],
                "name_ta": stop["name_ta"],
                "lat": stop["lat"],
                "lng": stop["lng"],
                "sequence": stop["sequence"],
            }

            try:
                supabase.table("stops").upsert(row, on_conflict="id").execute()
                total_inserted += 1
                logger.info(f"  ✓ {stop['name']} ({stop['name_ta']})")
            except Exception as e:
                logger.error(f"  ✗ Failed to insert {stop['id']}: {e}")

    logger.info(f"\n{'='*50}")
    logger.info(f"Seeded {total_inserted} stops across {len(ROUTES)} routes.")
    logger.info(f"{'='*50}")


if __name__ == "__main__":
    seed()
