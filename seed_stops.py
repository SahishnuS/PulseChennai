"""
Seed Chennai MTC Bus Stops into Supabase
==========================================
Scrapes official MTC routes dynamically, geocodes them using TomTom,
and writes to Supabase.
"""

import os
import sys
import logging
import uuid

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("seed_stops")

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from traffic.ingest_mtc import scrape_route_stops, geocode_stop

ROUTES_TO_INGEST = ["19", "102X", "515"]


def clear_database(supabase):
    """Clear old tracking and routing data so new buses have a clean slate."""
    logger.info("Clearing old data from Supabase...")
    tables_to_clear = [
        "journey_watches", "alerts", "cached_route_segments", "route_polylines", "buses", "stops"
    ]
    for table in tables_to_clear:
        try:
            # Delete all rows where id/routing key is not empty
            if table == "buses":
                supabase.table(table).delete().neq("id", "").execute()
            elif table == "stops":
                supabase.table(table).delete().neq("id", "").execute()
            elif table == "route_polylines":
                supabase.table(table).delete().neq("route_id", "").execute()
            elif table == "cached_route_segments":
                supabase.table(table).delete().neq("start_stop_id", "").execute()
            elif table == "alerts":
                supabase.table(table).delete().neq("id", 0).execute()
            elif table == "journey_watches":
                supabase.table(table).delete().neq("id", 0).execute()
                
            logger.info(f"  ✓ Cleared {table}")
        except Exception as e:
            logger.warning(f"  ✗ Failed to clear {table}: {e}")


def seed():
    from infrastructure.supabase_client import get_supabase

    supabase = get_supabase()
    if not supabase:
        logger.error("Supabase client not available. Check SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        sys.exit(1)

    clear_database(supabase)

    total_inserted = 0

    for route_id in ROUTES_TO_INGEST:
        logger.info(f"Scraping route {route_id} from official MTC source...")
        stops = scrape_route_stops(route_id)
        
        if not stops:
            logger.error(f"  ✗ No stops found for {route_id}. Skipping.")
            continue
            
        logger.info(f"  Found {len(stops)} stops. Geocoding...")
        
        for idx, stop_name in enumerate(stops):
            coords = geocode_stop(stop_name)
            stop_id = f"STOP_{route_id}_{idx+1}"
            
            row = {
                "id": stop_id,
                "route": route_id,
                "name": stop_name,
                "name_ta": stop_name, # MTC site often gives mixed or English, just passing raw for now
                "lat": coords["lat"],
                "lng": coords["lng"],
                "sequence": idx + 1,
            }

            try:
                supabase.table("stops").upsert(row, on_conflict="id").execute()
                total_inserted += 1
                logger.info(f"  ✓ [{idx+1}/{len(stops)}] {stop_name} ({coords['lat']:.5f}, {coords['lng']:.5f})")
            except Exception as e:
                logger.error(f"  ✗ Failed to insert {stop_id}: {e}")

    logger.info(f"\n{'='*50}")
    logger.info(f"Seeded {total_inserted} official stops across {len(ROUTES_TO_INGEST)} routes.")
    logger.info(f"{'='*50}")


if __name__ == "__main__":
    seed()
