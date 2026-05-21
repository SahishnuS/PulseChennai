"""
Pulse-Chennai Dashboard Server (Free Tier Edition)
=====================================================
FastAPI application using Supabase + Upstash Redis.
No Kafka, no local Redis, no local PostgreSQL required.

Usage:
    uvicorn api.dashboard_server:app --host 0.0.0.0 --port 8000
"""

import os
import sys
import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pulse_chennai")

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(env_path)
    logger.info("Loaded .env")
except ImportError:
    logger.warning("python-dotenv not installed. Using system env vars only.")


# ── Background polling task ──
_polling_task = None


async def _bus_polling_loop():
    """Background task: poll Supabase buses table, run reliability scorer, flag ghosts."""
    from infrastructure.supabase_client import get_supabase
    from infrastructure import upstash_redis
    from hardware.reliability_scorer import HardwareReliabilityScorer
    import time, json

    scorer = HardwareReliabilityScorer(decay_rate=0.3, ghost_threshold=0.4)

    while True:
        try:
            supabase = get_supabase()
            if not supabase:
                await asyncio.sleep(3)
                continue

            # Fetch all buses
            result = supabase.table("buses").select("*").execute()
            raw_buses = result.data if result.data else []
            buses = [b for b in raw_buses if b.get("route") in ["19", "102X", "515", "21C", "70", "47A"]]

            for bus in buses:
                bus_id = bus.get("id", "")
                lat = bus.get("lat", 0)
                lng = bus.get("lng", 0)
                speed = bus.get("speed", 0)

                # Run reliability scorer
                score = scorer.score_ping(
                    bus_id=bus_id,
                    lat=lat,
                    lng=lng,
                    timestamp=time.time() * 1000,
                    speed=speed,
                )

                is_ghost = score < 0.4

                # Update bus if ghost status changed
                if is_ghost != bus.get("is_ghost", False):
                    try:
                        supabase.table("buses").update({
                            "is_ghost": is_ghost,
                            "reliability_score": round(score, 4),
                        }).eq("id", bus_id).execute()
                    except Exception as e:
                        logger.debug(f"Failed to update ghost status for {bus_id}: {e}")

                # Publish update to Upstash Redis channel
                update_data = {
                    "type": "bus_update",
                    "bus_id": bus_id,
                    "lat": lat,
                    "lng": lng,
                    "speed": speed,
                    "is_ghost": is_ghost,
                    "reliability_score": round(score, 4),
                    "route": bus.get("route", ""),
                    "crowding": bus.get("crowding", "low"),
                    "stop_index": bus.get("stop_index", 0),
                }
                await upstash_redis.publish_json("bus-updates", update_data)

        except Exception as e:
            logger.warning(f"Bus polling error: {e}")

        await asyncio.sleep(3)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of all subsystems."""
    global _polling_task

    logger.info("=" * 60)
    logger.info("PULSE-CHENNAI ENGINE STARTING (Free Tier)")
    logger.info("=" * 60)

    # ── 1. Initialize Supabase ──
    from infrastructure.supabase_client import get_supabase
    sb = get_supabase()
    if sb:
        logger.info("✅ Supabase connected")
    else:
        logger.warning("⚠ Supabase not configured — check SUPABASE_URL and SUPABASE_SERVICE_KEY")

    # ── 2. Initialize Upstash Redis ──
    from infrastructure import upstash_redis
    await upstash_redis.init()
    health = await upstash_redis.health_check()
    if health.get("status") == "connected":
        logger.info("✅ Upstash Redis connected")
    else:
        logger.warning(f"⚠ Upstash Redis: {health}")

    # ── 3. Start background polling loop ──
    _polling_task = asyncio.create_task(_bus_polling_loop())
    logger.info("✅ Background bus polling started (3s interval)")

    logger.info("=" * 60)
    logger.info("PULSE-CHENNAI ENGINE READY — http://0.0.0.0:8000")
    logger.info("=" * 60)

    yield  # ─── Application is running ───

    # ── Shutdown ──
    logger.info("Shutting down Pulse-Chennai...")
    if _polling_task:
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:
            pass
    await upstash_redis.close()
    logger.info("Pulse-Chennai shutdown complete.")


# ── Create FastAPI app ──
app = FastAPI(
    title="Pulse-Chennai",
    description="Cloud-native transit intelligence engine for Chennai MTC buses",
    version="3.0.0",
    lifespan=lifespan,
)

# ── Middleware ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from api.routes.ingest import router as ingest_router
from api.routes.buses import router as buses_router
from api.routes.health import router as health_router
from api.routes.stops import router as stops_router
from api.routes.routes import router as routes_router
from api.routes.alerts import router as alerts_router
from api.routes.ai import router as ai_router
from api.routes.eta import router as eta_router
from api.routes.polylines import router as polylines_router
from api.routes.h3_demand import router as h3_demand_router
from api.routes.chat import router as chat_router
from app.routers.passengers import router as passengers_router
from api.dashboard_routes import router as dashboard_router

app.include_router(ingest_router)
app.include_router(buses_router)
app.include_router(health_router)
app.include_router(stops_router)
app.include_router(routes_router)
app.include_router(alerts_router)
app.include_router(ai_router)
app.include_router(eta_router)
app.include_router(polylines_router)
app.include_router(h3_demand_router)
app.include_router(chat_router)
app.include_router(passengers_router)
app.include_router(dashboard_router)

# ── Serve frontend (Vite build output) ──
_FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
_UI_DIR = os.path.join(os.path.dirname(__file__), "..", "ui")


@app.get("/api/config")
async def get_config():
    """Return public configuration required by the frontend."""
    return {
        "supabase_url": os.getenv("VITE_SUPABASE_URL", ""),
        "supabase_anon_key": os.getenv("VITE_SUPABASE_ANON_KEY", ""),
    }


# Serve static assets from frontend dist if it exists
if os.path.exists(_FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_FRONTEND_DIST, "assets")), name="assets")


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """Serve the React SPA. Falls back to index.html for client-side routing.
    API paths (/api/*) are never handled here — they are routed by the
    registered APIRouter instances above.
    """
    # Never shadow API routes — let FastAPI's 404 handler take over
    if full_path.startswith("api/"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"API route not found: /{full_path}")

    # Try frontend dist first
    if os.path.exists(_FRONTEND_DIST):
        file_path = os.path.join(_FRONTEND_DIST, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        index = os.path.join(_FRONTEND_DIST, "index.html")
        if os.path.exists(index):
            return FileResponse(index)

    # Fallback to ui/ directory
    if os.path.exists(_UI_DIR):
        file_path = os.path.join(_UI_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        index = os.path.join(_UI_DIR, "index.html")
        if os.path.exists(index):
            return FileResponse(index)

    return {"message": "Pulse-Chennai API is running. Build the frontend with: cd frontend && npm run build"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.dashboard_server:app", host="0.0.0.0", port=8000, reload=True)
