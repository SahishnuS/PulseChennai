"""
Stateful Chat Endpoint
========================
POST /api/chat — Gemini-powered chat with sliding-window history
and live transit context injection.
"""

import os
import json
import logging
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, List

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Chat"])


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text")


class ChatRequest(BaseModel):
    message: str = Field(..., description="User's current message")
    history: List[ChatMessage] = Field(default_factory=list, description="Conversation history")
    user_id: str = Field("demo_user", description="User ID for ticket context")
    language: str = Field("en", description="'en' or 'ta'")
    ticket_context: str = Field("", description="Active ticket context string from frontend")


class ChatResponse(BaseModel):
    reply: str
    updated_history: List[ChatMessage]
    model: str = "gemini-2.0-flash"


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Stateful chat with Gemini — includes live transit context
    and sliding-window conversation history.
    """
    from app.services.chat_context import build_messages

    # Convert history to dict format
    history_dicts = [{"role": m.role, "content": m.content} for m in req.history]

    # Build the full messages array
    gemini_messages, trimmed_history = build_messages(
        conversation_history=history_dicts,
        new_message=req.message,
        user_id=req.user_id,
        language=req.language,
        ticket_context=req.ticket_context,
    )

    api_key = os.getenv("GEMINI_API_KEY", "")
    reply_text = ""
    model_used = "gemini-2.0-flash"

    if api_key:
        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name="gemini-2.0-flash")

            # Convert to Gemini SDK format
            response = model.generate_content(gemini_messages)
            reply_text = response.text if response.text else "I couldn't process that."

        except Exception as e:
            logger.warning(f"Gemini API error: {e}")
            reply_text = _template_response(req.message, req.language)
            model_used = "template_fallback"
    else:
        reply_text = _template_response(req.message, req.language)
        model_used = "template_fallback"

    # ── Build updated history ──
    updated_history = list(trimmed_history)
    updated_history.append({"role": "user", "content": req.message})
    updated_history.append({"role": "assistant", "content": reply_text})

    # Trim again if over 12
    if len(updated_history) > 12:
        excess = len(updated_history) - 12
        if excess % 2 != 0:
            excess += 1
        updated_history = updated_history[excess:]

    return ChatResponse(
        reply=reply_text,
        updated_history=[ChatMessage(role=m["role"], content=m["content"]) for m in updated_history],
        model=model_used,
    )


def _template_response(message: str, language: str) -> str:
    """Generate intelligent template responses when Gemini API is unavailable."""
    msg = message.lower()

    if language == "ta":
        if "t நகர" in msg or "t nagar" in msg:
            return "T நகரம் செல்ல Route 19 பேருந்தை பயன்படுத்தவும். திருப்போரூரிலிருந்து வேளச்சேரி வழியாக செல்கிறது. Route 47A மூலமாகவும் (குண்டி வழியாக) செல்லலாம்."
        if "நெரிசல" in msg or "crowded" in msg:
            return "தற்போதைய நெரிசல் நிலை: Dashboard-ல் பேருந்து markers-ல் பச்சை = குறைவு, மஞ்சள் = நடுத்தரம், சிவப்பு = அதிகம். Bus marker-ஐ tap செய்து விவரங்களைப் பாருங்கள்."
        if "டிக்கெட்" in msg or "ticket" in msg:
            return "உங்கள் active ticket-ஐ 'My Tickets' tab-ல் பார்க்கலாம். புதிய டிக்கெட் வாங்க 'Plan New Trip' பொத்தானை அழுத்தவும்."
        if "ghost" in msg or "பேய்" in msg:
            return "Ghost Bus என்பது GPS signal இழந்த பேருந்து. Dead reckoning மூலம் இருப்பிடத்தை கணிக்கிறோம். Dashboard-ல் orange dashed circle-ல் காண்பிக்கப்படும்."
        return "நான் PULSE Transit AI. சென்னை MTC பேருந்து routes, ETAs, நெரிசல், டிக்கெட் பற்றி கேளுங்கள்!"

    # English responses
    if "t nagar" in msg:
        return "You can reach T Nagar via Route 19 (from Thiruporur via Velachery) or Route 47A (from Chromepet via Guindy). Route 19 is approximately 34 minutes, Route 47A is approximately 28 minutes."
    if "broadway" in msg:
        return "Take Route 102X from Kelambakkam via OMR to reach Broadway. The journey takes approximately 45 minutes. Next bus is expected in about 12 minutes."
    if "koyambedu" in msg or "adyar" in msg:
        return "Route 21C connects Koyambedu to Adyar via Vadapalani. Journey time is approximately 40 minutes."
    if "ambattur" in msg or "perambur" in msg:
        return "Route 70 runs from Central to Ambattur via Egmore and Perambur. Note: BUS_070_001 is currently a ghost bus — GPS signal was lost near Egmore and position is estimated via dead reckoning."
    if "chromepet" in msg or "guindy" in msg:
        return "Route 47A runs from T Nagar to Chromepet via Guindy. Approximate fare: ₹18. Service runs from 05:00 to 23:30."
    if "crowd" in msg:
        return "Check the bus markers on the Dashboard map — green dot means low crowding, yellow is medium, red is high. Tap any bus marker for live details."
    if "ghost" in msg:
        return "Ghost buses have unreliable GPS signals. Our system detects them via the Hardware Reliability Scorer and estimates their position using dead reckoning and H3 demand clustering. They appear with an orange dashed circle on the map."
    if "eta" in msg or "when" in msg or "how long" in msg:
        return "Tap on any bus marker on the Dashboard map to see its live ETA to each upcoming stop. ETAs use our ML model trained on historical traffic patterns."
    if "ticket" in msg:
        return "Check your active tickets in the 'My Tickets' tab. To purchase a new ticket, click 'Plan New Trip' in the sidebar. Fares are calculated as ₹8 base + ₹2 per stop."
    if "route" in msg and "deviation" in msg:
        return "Route deviations are detected when a bus leaves its assigned polyline by more than 200m. An alert is triggered and affected downstream stops are flagged. The system uses geofencing against TomTom road-snapped polylines."
    if "h3" in msg or "hexagon" in msg:
        return "We use H3 hexagonal indexing at resolution 8 (~460m hexes) for demand density analysis, ghost bus recovery, and underservice detection. Unlike Uber which uses H3 for supply optimization, we use it to hold public transit infrastructure accountable."

    return "I'm PULSE, your Chennai MTC transit assistant. I can help with routes (19, 102X, 515, 21C, 70, 47A), live ETAs, crowding levels, ghost bus tracking, and ticket information. What would you like to know?"
