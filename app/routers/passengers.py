from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import random
import string
from datetime import datetime, timezone
import logging

from infrastructure.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/passengers", tags=["Passengers"])

# In-memory store for fallback when database tables or connection fails
_IN_MEMORY_REGISTRATIONS = {}  # ticket_id -> dict

class RegisterRequest(BaseModel):
    passenger_id: str
    bus_id: str
    boarding_stop: str

class AlightRequest(BaseModel):
    ticket_id: str
    alighting_stop: str

def generate_ticket_id():
    chars = string.ascii_uppercase + string.digits
    return "TKT-" + "".join(random.choices(chars, k=6))

@router.post("/register")
async def register_passenger(req: RegisterRequest):
    sb = get_supabase()
    
    # Defaults in case DB connection is missing or fails
    route_id = "21C"
    boarding_seq = 1
    total_stops = 10
    
    if sb:
        try:
            # Validate bus exists and get route
            bus_res = sb.table("buses").select("route").eq("id", req.bus_id).execute()
            if bus_res.data:
                route_id = bus_res.data[0]["route"]
                
                # Fetch stops for this route to calculate sequence order
                stops_res = sb.table("route_stops").select("stop_name, sequence_order").eq("route_id", route_id).order("sequence_order").execute()
                stops = stops_res.data or []
                total_stops = len(stops)
                for s in stops:
                    if req.boarding_stop.lower() in s["stop_name"].lower():
                        boarding_seq = s["sequence_order"]
                        break
        except Exception as e:
            logger.warning(f"Failed to fetch bus/stops from Supabase, using mock route info: {e}")
            if "_" in req.bus_id:
                parts = req.bus_id.split("_")
                if len(parts) > 1:
                    route_id = parts[1]
                    
    # Calculate fare estimate
    remaining_stops = max(1, total_stops - boarding_seq)
    fare_estimate = remaining_stops * 2
    ticket_id = generate_ticket_id()
    
    row = {
        "ticket_id": ticket_id,
        "passenger_id": req.passenger_id,
        "bus_id": req.bus_id,
        "route_id": route_id,
        "boarding_stop": req.boarding_stop,
        "fare_estimate": fare_estimate,
        "status": "active",
        "boarded_at": datetime.now(timezone.utc).isoformat(),
        "alighting_stop": None,
        "alighted_at": None,
        "final_fare": None
    }
    
    # Try inserting into Supabase
    if sb:
        try:
            res = sb.table("passenger_registrations").insert({
                "ticket_id": ticket_id,
                "passenger_id": req.passenger_id,
                "bus_id": req.bus_id,
                "route_id": route_id,
                "boarding_stop": req.boarding_stop,
                "fare_estimate": fare_estimate,
                "status": "active"
            }).execute()
            if res.data:
                logger.info(f"Successfully registered passenger in Supabase: {ticket_id}")
        except Exception as e:
            logger.warning(f"Failed to insert registration into Supabase, falling back to in-memory: {e}")
            
    # Always keep in-memory sync for robust fallback
    _IN_MEMORY_REGISTRATIONS[ticket_id] = row
    
    return {
        "ticket_id": ticket_id,
        "route": route_id,
        "bus_id": req.bus_id,
        "boarding_stop": req.boarding_stop,
        "fare_estimate": fare_estimate
    }


@router.post("/alight")
async def alight_passenger(req: AlightRequest):
    sb = get_supabase()
    
    ticket = None
    if sb:
        try:
            # Fetch current ticket
            tkt_res = sb.table("passenger_registrations").select("*").eq("ticket_id", req.ticket_id).execute()
            if tkt_res.data:
                ticket = tkt_res.data[0]
        except Exception as e:
            logger.warning(f"Failed to fetch ticket from Supabase: {e}")

    # Fall back to in-memory
    if not ticket:
        ticket = _IN_MEMORY_REGISTRATIONS.get(req.ticket_id)
        
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    if ticket["status"] != "active":
        raise HTTPException(status_code=400, detail="Ticket is not active")
        
    route_id = ticket.get("route_id") or "21C"
    boarding_stop = ticket["boarding_stop"]
    
    # Calculate stops travelled
    stops_travelled = 3
    if sb:
        try:
            stops_res = sb.table("route_stops").select("stop_name, sequence_order").eq("route_id", route_id).order("sequence_order").execute()
            stops = stops_res.data or []
            
            board_seq = 0
            alight_seq = 0
            for s in stops:
                if boarding_stop.lower() in s["stop_name"].lower():
                    board_seq = s["sequence_order"]
                if req.alighting_stop.lower() in s["stop_name"].lower():
                    alight_seq = s["sequence_order"]
                    
            if board_seq and alight_seq:
                stops_travelled = abs(alight_seq - board_seq)
        except Exception as e:
            logger.warning(f"Failed to compute stops travelled via Supabase: {e}")
            
    if stops_travelled == 0:
        stops_travelled = 1
        
    final_fare = (stops_travelled * 2) + 8
    
    # Calculate duration
    boarded_at_str = ticket.get("boarded_at")
    if boarded_at_str:
        try:
            if boarded_at_str.endswith("Z"):
                boarded_at_str = boarded_at_str[:-1] + "+00:00"
            boarded_at = datetime.fromisoformat(boarded_at_str)
        except Exception:
            boarded_at = datetime.now(timezone.utc)
    else:
        boarded_at = datetime.now(timezone.utc)
        
    now = datetime.now(timezone.utc)
    duration_minutes = max(1, int((now - boarded_at).total_seconds() / 60))
    
    update_data = {
        "alighting_stop": req.alighting_stop,
        "alighted_at": now.isoformat(),
        "final_fare": final_fare,
        "status": "completed"
    }
    
    # Update Supabase if available
    if sb:
        try:
            sb.table("passenger_registrations").update(update_data).eq("ticket_id", req.ticket_id).execute()
        except Exception as e:
            logger.warning(f"Failed to update registration in Supabase: {e}")
            
    # Update in-memory
    if req.ticket_id in _IN_MEMORY_REGISTRATIONS:
        _IN_MEMORY_REGISTRATIONS[req.ticket_id].update(update_data)
    else:
        # If it was in Supabase but not in memory, save it now
        ticket.update(update_data)
        _IN_MEMORY_REGISTRATIONS[req.ticket_id] = ticket
        
    return {
        "final_fare": final_fare,
        "journey_duration_minutes": duration_minutes
    }


@router.get("/{passenger_id}/tickets")
async def get_passenger_tickets(passenger_id: str):
    sb = get_supabase()
    tickets = []
    
    # Try fetching from Supabase
    if sb:
        try:
            res = sb.table("passenger_registrations").select("*").eq("passenger_id", passenger_id).order("boarded_at", desc=True).limit(20).execute()
            if res.data:
                tickets = res.data
        except Exception as e:
            logger.warning(f"Failed to fetch tickets from Supabase: {e}")
            
    # Merge in-memory tickets for this passenger
    in_mem_tickets = [t for t in _IN_MEMORY_REGISTRATIONS.values() if t.get("passenger_id") == passenger_id]
    
    seen_ticket_ids = {t["ticket_id"] for t in tickets}
    for t in in_mem_tickets:
        if t["ticket_id"] not in seen_ticket_ids:
            tickets.append(t)
            
    # Sort tickets by boarded_at descending
    def get_boarded_at(t):
        return t.get("boarded_at") or ""
        
    tickets.sort(key=get_boarded_at, reverse=True)
    
    # Format keys for frontend
    formatted = []
    for t in tickets[:20]:
        formatted.append({
            "id": t["ticket_id"],
            "route": t.get("route_id") or "21C",
            "from": t["boarding_stop"],
            "to": t.get("alighting_stop") or "Ongoing",
            "boarded_at": t.get("boarded_at"),
            "alighted_at": t.get("alighted_at"),
            "fare": t.get("final_fare") or t.get("fare_estimate") or 15,
            "bus_id": t["bus_id"],
            "status": t["status"],
            "crowding": "unknown"
        })
        
    return formatted
