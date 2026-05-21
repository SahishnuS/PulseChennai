import os
import sys
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from infrastructure.supabase_client import get_supabase

def inspect():
    supabase = get_supabase()
    if not supabase:
        print("Supabase client not available.")
        return

    # Fetch buses
    buses_resp = supabase.table("buses").select("*").execute()
    buses = buses_resp.data if hasattr(buses_resp, "data") else buses_resp
    print(f"Total buses: {len(buses)}")
    for bus in buses:
        print(f"Bus ID: {bus.get('id')}, Route: {bus.get('route')}, Status: {bus.get('status')}")

    # Fetch stops
    stops_resp = supabase.table("stops").select("*").execute()
    stops = stops_resp.data if hasattr(stops_resp, "data") else stops_resp
    print(f"Total stops: {len(stops)}")
    
    # Analyze stops by route
    route_stops = {}
    for stop in stops:
        route = stop.get("route")
        route_stops.setdefault(route, []).append(stop)
    
    print("\nStops by Route:")
    for route, s_list in route_stops.items():
        print(f"  Route '{route}': {len(s_list)} stops")

    # Check which bus routes have no stops
    bus_routes = set(bus.get("route") for bus in buses if bus.get("route"))
    stop_routes = set(route_stops.keys())
    
    missing = bus_routes - stop_routes
    print(f"\nBus routes with NO stops in DB: {missing}")

if __name__ == "__main__":
    inspect()
