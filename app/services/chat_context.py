"""
Pulse-Chennai Chat Context Manager
====================================
Builds the structured prompt payload for the Gemini chatbot,
including system prompt, live transit context, and sliding-window
conversation history.
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

IST = timedelta(hours=5, minutes=30)

# ── All known routes and stops ──
KNOWN_ROUTES = {
    "19":   "Thiruporur → Velachery → T Nagar",
    "102X": "Kelambakkam → OMR → Broadway",
    "515":  "Tambaram → GST Road → Mamallapuram",
    "21C":  "Koyambedu → Vadapalani → Adyar",
    "70":   "Central → Egmore → Perambur → Ambattur",
    "47A":  "T Nagar → Guindy → Chromepet",
}

MAX_HISTORY = 12  # 6 turns (user + assistant)


def build_system_prompt() -> str:
    """Return the static system prompt for the PULSE transit assistant."""
    return """You are PULSE, an intelligent transit assistant for Chennai's MTC bus network.
You have real-time access to live bus data, ETAs, and passenger information.

CAPABILITIES:
- Answer questions about Routes 19, 102X, 515, 21C, 70, 47A
- Provide live ETAs and crowding information
- Explain ghost bus recovery and GPS reliability
- Help passengers with their active tickets
- Respond fluently in both English and Tamil (தமிழ்)
- Alert passengers about route deviations

PERSONALITY: Precise, helpful, local. Use Chennai landmarks naturally 
(Anna Salai, T Nagar, OMR, GST Road). Never say "I don't know" — 
estimate from available data and say "approximately."

CRITICAL RULES:
- If asked in Tamil, respond entirely in Tamil script
- If asked about a ticket the user holds, reference it directly
- Never hallucinate stop names — only use stops from the 6 known routes
- Keep responses under 120 words unless a list is needed
"""


def build_live_context(user_id: str = "") -> str:
    """
    Fetch and format live transit context to inject into the prompt.
    Includes: active buses, ghost buses, deviation alerts, user ticket, current time.
    """
    lines = []

    # ── Current time context ──
    now_ist = datetime.now(timezone.utc) + IST
    hour = now_ist.hour
    if 7 <= hour <= 10:
        rush = "MORNING RUSH HOUR"
    elif 16 <= hour <= 20:
        rush = "EVENING RUSH HOUR"
    elif 22 <= hour or hour < 5:
        rush = "LATE NIGHT — REDUCED SERVICE"
    else:
        rush = "NORMAL HOURS"

    day_name = now_ist.strftime("%A")
    time_str = now_ist.strftime("%H:%M IST")
    lines.append(f"Current time: {time_str} | Day: {day_name} | Status: {rush}")
    lines.append("")

    # ── Active buses ──
    try:
        from infrastructure.supabase_client import get_supabase
        client = get_supabase()
        if client:
            raw_buses = client.table("buses").select("*").execute().data or []
            valid_routes = set(KNOWN_ROUTES.keys())
            buses = [b for b in raw_buses if b.get("route") in valid_routes]

            lines.append("ACTIVE BUSES:")
            for bus in buses:
                is_ghost = bus.get("is_ghost", False)
                reliability = bus.get("reliability_score", bus.get("reliability", 1.0))
                speed = bus.get("speed", 0)
                crowding = bus.get("crowding", "unknown").upper()
                route = bus.get("route", "?")
                bus_id = bus.get("id", "?")
                status = "GHOST — GPS LOST" if is_ghost else "ACTIVE"

                if is_ghost:
                    last_stop = bus.get("last_known_stop", "unknown")
                    est_pos = bus.get("estimated_position", "unknown")
                    lines.append(
                        f"  GHOST: {bus_id} | Route {route} | GPS LOST | "
                        f"Recovering via dead reckoning | Last seen: {last_stop} | "
                        f"Estimated position: near {est_pos}"
                    )
                else:
                    next_stop = bus.get("next_stop", "unknown")
                    eta_min = bus.get("eta_minutes", "?")
                    lines.append(
                        f"  {bus_id} | Route {route} | Speed: {speed}km/h | "
                        f"Next stop: {next_stop} ({eta_min} min) | "
                        f"Crowding: {crowding} | Reliability: {reliability:.2f} | "
                        f"Status: {status}"
                    )

            # ── Deviation alerts ──
            try:
                alerts = client.table("alerts").select("*").order(
                    "created_at", desc=True
                ).limit(5).execute().data or []
                if alerts:
                    lines.append("")
                    lines.append("ACTIVE ALERTS:")
                    for alert in alerts:
                        lines.append(f"  {alert.get('type', 'ALERT')}: {alert.get('message', '')}")
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Could not fetch live context: {e}")
        lines.append("ACTIVE BUSES: (data temporarily unavailable)")

    # ── User's active ticket ──
    lines.append("")
    # In a real system, we'd query by user_id. For demo, we note the absence.
    lines.append("USER ACTIVE TICKET: Check user's localStorage for active tickets (sent from frontend)")

    # ── Available routes summary ──
    lines.append("")
    lines.append("AVAILABLE ROUTES:")
    for route_id, route_name in KNOWN_ROUTES.items():
        lines.append(f"  Route {route_id}: {route_name}")

    return "\n".join(lines)


def build_messages(
    conversation_history: list,
    new_message: str,
    user_id: str = "",
    language: str = "en",
    ticket_context: str = "",
) -> list:
    """
    Assemble the full messages array for the Gemini API call.

    Structure:
      1. System prompt + live context (as first user message)
      2. Model acknowledgment
      3. Sliding window of conversation history (max 12 messages)
      4. Current user message
    """
    system_prompt = build_system_prompt()
    live_context = build_live_context(user_id)

    # Append Tamil preference if needed
    if language == "ta":
        system_prompt += (
            "\n\nThe user prefers Tamil. "
            "Respond in Tamil script (தமிழ்) regardless of input language."
        )

    # Build the initial context injection
    context_message = f"{system_prompt}\n\n--- LIVE TRANSIT DATA ---\n{live_context}"

    messages = [
        {"role": "user", "parts": [{"text": context_message}]},
        {"role": "model", "parts": [{"text": "Understood. I have access to the live transit data. I'm ready to help."}]},
    ]

    # ── Sliding window: trim history to MAX_HISTORY ──
    trimmed_history = conversation_history
    if len(trimmed_history) > MAX_HISTORY:
        # Drop oldest pairs (always drop 2 at a time: user + model)
        excess = len(trimmed_history) - MAX_HISTORY
        if excess % 2 != 0:
            excess += 1
        trimmed_history = trimmed_history[excess:]

    # Append history
    for msg in trimmed_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        # Map frontend roles to Gemini roles
        gemini_role = "model" if role == "assistant" else "user"
        messages.append({"role": gemini_role, "parts": [{"text": content}]})

    # ── Current message with optional ticket context injection ──
    final_message = new_message
    if ticket_context:
        final_message = f"[Context: {ticket_context}]\n{new_message}"

    messages.append({"role": "user", "parts": [{"text": final_message}]})

    return messages, trimmed_history
