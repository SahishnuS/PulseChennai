from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import random
import string
from datetime import datetime, timezone
import logging

from infrastructure.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/passengers", tags=["Passengers"])

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
    if not sb:
        raise HTTPException(status_code=503, detail="Database not connected")
        
    # Validate bus exists and get route
    try:
        bus_res = sb.table("buses").select("route").eq("id", req.bus_id).execute()
        if not bus_res.data:
            raise HTTPException(status_code=404, detail="Bus not found or inactive")
            
        route_id = bus_res.data[0]["route"]
        
        # Calculate fare estimate: number of remaining stops × 2
        # We need to find the sequence order of the boarding stop
        stops_res = sb.table("route_stops").select("stop_name, sequence_order").eq("route_id", route_id).order("sequence_order").execute()
        stops = stops_res.data or []
        
        boarding_seq = 0
        total_stops = len(stops)
        for s in stops:
            # simple substring match in case of formatting differences
            if req.boarding_stop.lower() in s["stop_name"].lower():
                boarding_seq = s["sequence_order"]
                break
                
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
            "status": "active"
        }
        
        res = sb.table("passenger_registrations").insert(row).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create ticket")
            
        return {
            "ticket_id": ticket_id,
            "route": route_id,
            "bus_id": req.bus_id,
            "boarding_stop": req.boarding_stop,
            "fare_estimate": fare_estimate
        }
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alight")
async def alight_passenger(req: AlightRequest):
    sb = get_supabase()
    if not sb:
        raise HTTPException(status_code=503, detail="Database not connected")
        
    try:
        # Fetch current ticket
        tkt_res = sb.table("passenger_registrations").select("*").eq("ticket_id", req.ticket_id).execute()
        if not tkt_res.data:
            raise HTTPException(status_code=404, detail="Ticket not found")
            
        ticket = tkt_res.data[0]
        if ticket["status"] != "active":
            raise HTTPException(status_code=400, detail="Ticket is not active")
            
        route_id = ticket["route_id"]
        boarding_stop = ticket["boarding_stop"]
        
        # Calculate stops travelled
        stops_res = sb.table("route_stops").select("stop_name, sequence_order").eq("route_id", route_id).order("sequence_order").execute()
        stops = stops_res.data or []
        
        board_seq = 0
        alight_seq = 0
        for s in stops:
            if boarding_stop.lower() in s["stop_name"].lower():
                board_seq = s["sequence_order"]
            if req.alighting_stop.lower() in s["stop_name"].lower():
                alight_seq = s["sequence_order"]
                
        stops_travelled = abs(alight_seq - board_seq)
        if stops_travelled == 0:
            stops_travelled = 1 # min 1 stop
            
        # Final fare: stops_travelled × 2 + base ₹8
        final_fare = (stops_travelled * 2) + 8
        
        # Calculate duration
        boarded_at = datetime.fromisoformat(ticket["boarded_at"])
        now = datetime.now(timezone.utc)
        duration_minutes = int((now - boarded_at).total_seconds() / 60)
        
        # Update record
        update_data = {
            "alighting_stop": req.alighting_stop,
            "alighted_at": now.isoformat(),
            "final_fare": final_fare,
            "status": "completed"
        }
        sb.table("passenger_registrations").update(update_data).eq("ticket_id", req.ticket_id).execute()
        
        return {
            "final_fare": final_fare,
            "journey_duration_minutes": duration_minutes
        }
    except Exception as e:
        logger.error(f"Alighting error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{passenger_id}/tickets")
async def get_passenger_tickets(passenger_id: str):
    sb = get_supabase()
    if not sb:
        raise HTTPException(status_code=503, detail="Database not connected")
        
    try:
        # Get last 20 tickets
        res = sb.table("passenger_registrations").select("*").eq("passenger_id", passenger_id).order("boarded_at", desc=True).limit(20).execute()
        
        # Format keys for frontend (align with MOCK_TICKETS format)
        formatted = []
        for t in (res.data or []):
            formatted.append({
                "id": t["ticket_id"],
                "route": t["route_id"],
                "from": t["boarding_stop"],
                "to": t["alighting_stop"] or "Ongoing",
                "boarded_at": t["boarded_at"],
                "alighted_at": t["alighted_at"],
                "fare": t["final_fare"] or t["fare_estimate"],
                "bus_id": t["bus_id"],
                "status": t["status"],
                "crowding": "unknown" # Could be fetched from bus table ideally, default for now
            })
            
        return formatted
    except Exception as e:
        logger.error(f"Fetch tickets error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
