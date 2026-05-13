"""
Pulse-Chennai Dashboard Server
================================
FastAPI application factory with async lifespan management.
Starts/stops all subsystems: Database, Redis, Kafka, TomTom, GNN.

Usage:
    uvicorn api.dashboard_server:app --host 0.0.0.0 --port 8001
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of all subsystems."""
    logger.info("=" * 60)
    logger.info("PULSE-CHENNAI ENGINE STARTING")
    logger.info("=" * 60)

    # ── 1. Database ──
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        from database import connection
        await connection.connect(db_url)
        # Run migrations if using local DB
        migration_path = os.path.join(os.path.dirname(__file__), "..", "database", "migrations", "001_initial.sql")
        if os.path.exists(migration_path):
            await connection.execute_migration(migration_path)
    else:
        logger.warning("DATABASE_URL not set. PostgreSQL features disabled.")

    # ── 2. Redis ──
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    from infrastructure import async_redis
    await async_redis.connect(redis_url)

    # ── 3. Kafka Producer ──
    kafka_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    from infrastructure import kafka_producer
    from fusion.message_handler import handle_message

    # Set fallback: if Kafka is down, process messages directly
    kafka_producer.set_fallback_handler(handle_message)
    await kafka_producer.start(kafka_servers)

    # ── 4. Kafka Consumer ──
    from infrastructure import kafka_consumer
    topics = [
        os.getenv("KAFKA_TOPIC_GPS", "bus-gps-pings"),
        os.getenv("KAFKA_TOPIC_PASSENGER", "passenger-pings"),
    ]
    group_id = os.getenv("KAFKA_CONSUMER_GROUP", "pulse-chennai-consumer")
    await kafka_consumer.start(kafka_servers, topics, group_id, handle_message)

    # ── 5. TomTom Traffic Refresh ──
    tomtom_key = os.getenv("TOMTOM_API_KEY", "")
    from traffic import tomtom_client
    await tomtom_client.init(api_key=tomtom_key if tomtom_key else None)
    refresh_interval = int(os.getenv("TOMTOM_REFRESH_INTERVAL", "120"))
    await tomtom_client.start_refresh_loop(refresh_interval)

    # ── 7. Preload GNN Inference Pipeline ──
    try:
        from api.routes.predict import get_pipeline
        # Running synchronously is fine here since it only happens once at startup
        get_pipeline()
        logger.info("Preloaded InferencePipeline with GNN model")
    except Exception as e:
        logger.warning(f"Failed to preload InferencePipeline: {e}")

    logger.info("=" * 60)
    logger.info("PULSE-CHENNAI ENGINE READY — http://0.0.0.0:8001")
    logger.info("=" * 60)

    # ── 6. Seed initial bus data into the speed layer ──
    # Ensures the dashboard shows buses immediately on load
    import random
    # Seed positions match the FIRST waypoint of each simulator route exactly,
    # so markers do not jump when the simulator starts sending live data.
    _SEED_BUSES = [
        {"id": "MTC-19-001",   "route": "19",   "lat": 12.7427, "lng": 80.2297, "speed": 35.0, "hw": 0.95},
        {"id": "MTC-102X-002", "route": "102X", "lat": 12.7427, "lng": 80.2297, "speed": 38.0, "hw": 0.93},
    ]
    for seed in _SEED_BUSES:
        state = {
            "lat": seed["lat"],
            "lng": seed["lng"],
            "speed": seed["speed"],
            "heading": random.uniform(0, 360),
            "hw_score": seed["hw"],
            "is_ghost": False,
            "status": "active",
            "route_id": seed["route"],
            "h3_cell": "",
            "passenger_count": random.randint(15, 55),
            "source": "AIS140",
            "confidence": 0.98,
        }
        await async_redis.set_bus_state(seed["id"], state)
    logger.info(f"Seeded {len(_SEED_BUSES)} buses into speed layer.")

    yield  # ─── Application is running ───

    # ── Shutdown ──
    logger.info("Shutting down Pulse-Chennai...")
    await kafka_consumer.stop()
    await kafka_producer.stop()
    await tomtom_client.close()
    await async_redis.disconnect()
    if db_url:
        from database import connection
        await connection.disconnect()
    logger.info("Pulse-Chennai shutdown complete.")


# ── Create FastAPI app ──
app = FastAPI(
    title="Pulse-Chennai",
    description="TEST DESCRIPTION",
    version="2.0.0",
    lifespan=lifespan,
)

# ── Middleware ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount routers ──
from api.routes.ingest import router as ingest_router
from api.routes.buses import router as buses_router
from api.routes.health import router as health_router
from api.routes.predict import router as predict_router
from api.routes.eta import router as eta_router
from api.websocket import router as ws_router

app.include_router(ingest_router)
app.include_router(buses_router)
app.include_router(health_router)
app.include_router(predict_router)
app.include_router(eta_router)
app.include_router(ws_router)

# ── Serve frontend ──
_UI_DIR = os.path.join(os.path.dirname(__file__), "..", "ui")

if os.path.exists(_UI_DIR):
    app.mount("/static", StaticFiles(directory=_UI_DIR), name="static")

@app.get("/api/config")
async def get_config():
    """Return public configuration required by the frontend."""
    return {"tomtom_api_key": os.getenv("TOMTOM_API_KEY", "")}


@app.get("/")
async def serve_dashboard():
    index = os.path.join(_UI_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "Pulse-Chennai API is running. No frontend found at /ui/index.html"}


@app.get("/eta")
async def serve_eta_page():
    """Serve the standalone ETA Calculator page."""
    eta_page = os.path.join(_UI_DIR, "eta.html")
    if os.path.exists(eta_page):
        return FileResponse(eta_page)
    return {"message": "ETA page not found at /ui/eta.html"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.dashboard_server:app", host="0.0.0.0", port=8001, reload=True)
