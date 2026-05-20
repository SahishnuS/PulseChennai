"""
AI Assistant Route (Google Gemini Edition)
=============================================
POST /api/ai/query — calls Google Gemini for transit assistance
Bilingual: English + Tamil
"""

import os
import json
import logging
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["AI"])


class AIQueryRequest(BaseModel):
    message: str = Field(..., description="User's question")
    language: str = Field("en", description="'en' or 'ta'")
    context: Optional[dict] = Field(default_factory=dict, description="Bus/route context")


SYSTEM_PROMPT = """You are "Chennai One AI", a highly intelligent and professional transit assistant for the Pulse Chennai system.
You help passengers navigate public buses in Chennai. Answer questions about routes, stops, ETAs, ticket pricing, and bus travel.
Be extremely concise, professional, and directly address the user's need (under 2 sentences).
If the user's language is "ta", respond in Tamil script.
If the user's language is "en", respond in English.
Analyze the provided live context (bus locations, alerts, crowding, ticket prices) to give accurate answers.
Do not hallucinate data. If a bus isn't in the context, say you don't have real-time data for it.

Available routes:
- 19: Thiruporur → T Nagar
- 102X: Kelambakkam → Broadway
- 515: Tambaram → Mamallapuram"""


@router.post("/ai/query")
async def ai_query(req: AIQueryRequest):
    """
    Send a query to Google Gemini with live transit context fetched from Supabase.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")

    # Fetch live context from DB
    live_context = {}
    try:
        from infrastructure.supabase_client import get_supabase
        client = get_supabase()
        if client:
            raw_buses = client.table("buses").select("*").execute().data or []
            buses = [b for b in raw_buses if b.get("route") in ["19", "102X", "515"]]
            alerts = client.table("alerts").select("*").order("created_at", desc=True).limit(5).execute().data
            live_context = {
                "active_buses": buses,
                "recent_alerts": alerts,
                "ticket_pricing": {"MTC Ordinary": "₹5 to ₹20", "MTC Deluxe": "₹11 to ₹48"}
            }
    except Exception as e:
        logger.warning(f"Could not fetch live context for AI: {e}")

    # Build context string
    context_str = json.dumps(live_context, default=str)
    user_message = f"Language: {req.language}. Live System Context: {context_str}. User question: {req.message}"

    if api_key:
        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(
                model_name="gemini-2.0-flash",
                system_instruction=SYSTEM_PROMPT,
            )

            response = model.generate_content(user_message)
            reply = response.text if response.text else "I couldn't process that question."

            return {
                "response": reply,
                "language": req.language,
                "model": "gemini-2.0-flash",
            }

        except Exception as e:
            logger.warning(f"Gemini API error: {e}")
            # Fall through to template fallback

    # ── Template fallback (no API key or API failure) ──
    reply = _template_response(req.message, req.language, req.context)
    return {
        "response": reply,
        "language": req.language,
        "model": "template_fallback",
    }


def _template_response(message: str, language: str, context: Optional[dict]) -> str:
    """Generate a template response for common questions without API."""
    msg_lower = message.lower()

    if language == "ta":
        if "t நகர" in msg_lower or "t nagar" in msg_lower:
            return "T நகரம் செல்ல 19 பேருந்தை பயன்படுத்தவும். திருப்போரூர் முனையத்தில் இருந்து புறப்படுகிறது."
        if "நெரிசல" in msg_lower or "crowded" in msg_lower:
            return "தற்போதைய நெரிசல் நிலையை சரிபார்க்கிறேன். வரைபடத்தில் பேருந்து குறிகளைப் பாருங்கள்."
        if "எப்போது" in msg_lower or "when" in msg_lower:
            return "பேருந்து ETA ஐ வரைபடத்தில் உள்ள பேருந்து குறியை தட்டி சரிபார்க்கவும்."
        return "மன்னிக்கவும், உங்கள் கேள்வியை புரிந்து கொள்ள முடியவில்லை. மீண்டும் முயற்சிக்கவும்."
    else:
        if "t nagar" in msg_lower:
            return "Take bus 19 to reach T Nagar. It departs from Thiruporur."
        if "broadway" in msg_lower:
            return "Take bus 102X to reach Broadway. It starts from Kelambakkam."
        if "tambaram" in msg_lower or "mamallapuram" in msg_lower:
            return "Take bus 515 which runs between Tambaram and Mamallapuram."
        if "crowded" in msg_lower or "crowd" in msg_lower:
            return "Check the bus markers on the map — green dot means low crowd, yellow is medium, red is high."
        if "ghost" in msg_lower:
            return "Ghost buses have unreliable GPS. We estimate their position using dead reckoning and show a dashed circle."
        if "eta" in msg_lower or "when" in msg_lower or "time" in msg_lower:
            return "Tap on a bus marker on the map to see live ETA to your stop."
        return "I'm your Chennai MTC bus assistant. Ask me about routes, stops, ETAs, or bus crowding!"
