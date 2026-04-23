"""
FastAPI Application — Pulse-Chennai Serving Layer
=====================================================
Endpoints for position prediction, ETA, ghost recovery,
and system health monitoring.
"""

import time
import logging
from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pulse_chennai.api.schemas import (
    PositionRequest, PositionResponse,
    ETARequest, ETAResponse,
    GhostRecoveryRequest, GhostRecoveryResponse,
    BusStatusResponse, HealthCheckResponse,
    GPSPing,
)
from pulse_chennai import __version__

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────
# Global references (initialized at startup)
# ──────────────────────────────────────────────────────
_pipeline = None
_feature_store = None
_reliability_scorer = None
_start_time = time.time()


def _init_components():
    """
    Initialize all system components.
    Called once at application startup.
    """
    global _pipeline, _feature_store, _reliability_scorer

    from pulse_chennai.config.settings import settings

    # ── Feature Store (Redis) ──
    from pulse_chennai.infrastructure.feature_store import FeatureStoreClient
    _feature_store = FeatureStoreClient(
        host=settings.redis.REDIS_HOST,
        port=settings.redis.REDIS_PORT,
        db=settings.redis.REDIS_DB,
        password=settings.redis.REDIS_PASSWORD,
        node_ttl=settings.redis.NODE_TTL_SECONDS,
        bus_ttl=settings.redis.BUS_TTL_SECONDS,
    )

    # ── Hardware Reliability Scorer ──
    from pulse_chennai.hardware.reliability_scorer import HardwareReliabilityScorer
    _reliability_scorer = HardwareReliabilityScorer(
        min_ping_freq=settings.hardware.MIN_PING_FREQUENCY_HZ,
        max_jitter_m=settings.hardware.MAX_GPS_JITTER_METERS,
        max_speed_kmh=settings.hardware.MAX_SPEED_KMH,
        stale_threshold_s=settings.hardware.STALE_THRESHOLD_SECONDS,
        ghost_threshold=settings.hardware.GHOST_THRESHOLD,
        decay_rate=settings.hardware.SCORE_DECAY_RATE,
    )

    # ── Data Fusion ──
    from pulse_chennai.graph.data_fusion import DataFusion
    data_fusion = DataFusion(
        h3_feature_dim=settings.gnn.H3_FEATURE_DIM,
        bus_feature_dim=settings.gnn.BUS_FEATURE_DIM,
        temporal_dim=settings.gnn.TEMPORAL_DIM,
        gmaps_api_key=settings.gmaps.GMAPS_API_KEY,
        gmaps_weight=settings.gmaps.ETA_CALIBRATION_WEIGHT,
    )

    # ── Graph Builder ──
    from pulse_chennai.graph.graph_builder import DynamicGraphBuilder
    graph_builder = DynamicGraphBuilder(
        h3_feature_dim=settings.gnn.H3_FEATURE_DIM,
        bus_feature_dim=settings.gnn.BUS_FEATURE_DIM,
        temporal_dim=settings.gnn.TEMPORAL_DIM,
        k_ring_radius=settings.h3.K_RING_RADIUS,
    )

    # ── SpatialGNN Model ──
    from pulse_chennai.model.spatial_gnn import SpatialGNN
    model = SpatialGNN(
        h3_feature_dim=settings.gnn.H3_FEATURE_DIM,
        bus_feature_dim=settings.gnn.BUS_FEATURE_DIM,
        hidden_dim=settings.gnn.HIDDEN_DIM,
        num_heads=settings.gnn.NUM_HEADS,
        num_layers=settings.gnn.NUM_LAYERS,
        lstm_hidden=settings.gnn.LSTM_HIDDEN,
        dropout=settings.gnn.DROPOUT,
    )

    # Load pretrained weights if available
    import os
    if os.path.exists(settings.inference.MODEL_PATH):
        device = "cuda" if settings.inference.USE_CUDA and torch.cuda.is_available() else "cpu"
        state_dict = torch.load(settings.inference.MODEL_PATH, map_location=device)
        model.load_state_dict(state_dict)
        logger.info(f"Loaded model weights from {settings.inference.MODEL_PATH}")
    else:
        logger.warning(
            f"No model weights at {settings.inference.MODEL_PATH}. "
            "Running with random weights (for testing)."
        )

    # ── HMM Map Matcher ──
    from pulse_chennai.model.hmm_map_matching import HMMMapMatcher
    map_matcher = HMMMapMatcher()

    # ── Ghost Recovery ──
    from pulse_chennai.model.ghost_recovery import GhostBusRecovery
    ghost_recovery = GhostBusRecovery(
        model=model,
        graph_builder=graph_builder,
        feature_store=_feature_store,
        data_fusion=data_fusion,
        ghost_timeout_s=settings.inference.GHOST_RECOVERY_TIMEOUT_S,
    )

    # ── Inference Pipeline ──
    from pulse_chennai.api.inference_pipeline import InferencePipeline
    _pipeline = InferencePipeline(
        model=model,
        graph_builder=graph_builder,
        feature_store=_feature_store,
        data_fusion=data_fusion,
        map_matcher=map_matcher,
        reliability_scorer=_reliability_scorer,
        ghost_recovery=ghost_recovery,
        h3_resolution=settings.h3.DEFAULT_RESOLUTION,
        k_ring_radius=settings.h3.K_RING_RADIUS,
        use_amp=settings.inference.USE_AMP,
    )

    logger.info("All components initialized successfully.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    logger.info("Pulse-Chennai starting up...")
    _init_components()
    yield
    logger.info("Pulse-Chennai shutting down...")


# ──────────────────────────────────────────────────────
# FastAPI Application
# ──────────────────────────────────────────────────────

app = FastAPI(
    title="Pulse-Chennai",
    description=(
        "Cloud-native geospatial transit engine for real-time bus tracking, "
        "Ghost Bus recovery, and ETA prediction. "
        "Powered by Spatial-Temporal GNN with H3 hexagonal indexing."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────

@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """System health check with component status."""
    cuda_available = torch.cuda.is_available()
    gpu_name = torch.cuda.get_device_name(0) if cuda_available else None
    redis_ok = _feature_store.health_check() if _feature_store else False

    status = "healthy"
    if not redis_ok:
        status = "degraded"
    if _pipeline is None:
        status = "unhealthy"

    return HealthCheckResponse(
        status=status,
        model_loaded=_pipeline is not None,
        redis_connected=redis_ok,
        cuda_available=cuda_available,
        gpu_name=gpu_name,
        uptime_seconds=round(time.time() - _start_time, 1),
        version=__version__,
    )


@app.post("/predict/position", response_model=PositionResponse)
async def predict_position(request: PositionRequest):
    """
    Predict a bus's next H3 cell position with map-matching.

    Pipeline: GPS → H3 → Redis → GNN → HMM → Response
    """
    if _pipeline is None:
        raise HTTPException(503, "Model not loaded")

    try:
        result = _pipeline.predict_position(
            trip_id=request.trip_id,
            lat=request.current_lat,
            lng=request.current_lng,
            speed=request.speed,
            heading=request.heading,
            top_k=request.top_k,
        )
        return PositionResponse(**result)
    except Exception as e:
        logger.error(f"Position prediction failed: {e}", exc_info=True)
        raise HTTPException(500, f"Prediction failed: {str(e)}")


@app.post("/predict/eta", response_model=ETAResponse)
async def predict_eta(request: ETARequest):
    """
    Predict ETA to destination.
    Blends GNN prediction with Google Maps calibration.
    """
    if _pipeline is None:
        raise HTTPException(503, "Model not loaded")

    try:
        result = _pipeline.predict_eta(
            trip_id=request.trip_id,
            current_lat=request.current_lat,
            current_lng=request.current_lng,
            destination_lat=request.destination_lat,
            destination_lng=request.destination_lng,
            speed=request.speed,
            heading=request.heading,
        )
        return ETAResponse(**result)
    except Exception as e:
        logger.error(f"ETA prediction failed: {e}", exc_info=True)
        raise HTTPException(500, f"ETA prediction failed: {str(e)}")


@app.post("/recover/ghost", response_model=GhostRecoveryResponse)
async def recover_ghost_bus(request: GhostRecoveryRequest):
    """
    Estimate a ghost bus's position using GNN + Collaborative Telemetry.

    Triggered when a bus goes offline or hardware is flagged unreliable.
    """
    if _pipeline is None:
        raise HTTPException(503, "Model not loaded")

    try:
        bus_state = _feature_store.get_bus_state(request.trip_id)
        if not bus_state and request.last_known_lat:
            bus_state = {
                "lat": request.last_known_lat,
                "lng": request.last_known_lng,
                "h3_cell": "",
                "speed": 0, "heading": 0,
                "hw_score": 0.1,
                "last_seen": time.time() - 120,
            }
            from pulse_chennai.graph.h3_utils import latlng_to_h3
            bus_state["h3_cell"] = latlng_to_h3(
                request.last_known_lat, request.last_known_lng, 9
            )

        if not bus_state:
            raise HTTPException(404, f"No state for trip {request.trip_id}")

        result = _pipeline.ghost_recovery.recover(
            trip_id=request.trip_id,
            last_known_state=bus_state,
            person_pings=request.person_pings,
        )
        return GhostRecoveryResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ghost recovery failed: {e}", exc_info=True)
        raise HTTPException(500, f"Ghost recovery failed: {str(e)}")


@app.get("/bus/{trip_id}/status", response_model=BusStatusResponse)
async def get_bus_status(trip_id: str):
    """Get full status of a bus including hardware reliability score."""
    if _feature_store is None:
        raise HTTPException(503, "Feature store not available")

    bus_state = _feature_store.get_bus_state(trip_id)
    if not bus_state:
        raise HTTPException(404, f"Bus {trip_id} not found")

    is_ghost = _reliability_scorer.is_ghost(trip_id) if _reliability_scorer else False

    return BusStatusResponse(
        trip_id=trip_id,
        is_ghost=is_ghost,
        **bus_state,
    )


@app.post("/ingest/ping")
async def ingest_ping(ping: GPSPing):
    """
    Ingest a single GPS ping (for testing without Kafka).
    In production, pings flow through Kafka.
    """
    if _feature_store is None:
        raise HTTPException(503, "Feature store not available")

    from pulse_chennai.graph.h3_utils import latlng_to_h3

    h3_cell = latlng_to_h3(ping.lat, ping.lng, 9)

    if ping.ping_type == "bus" and ping.trip_id:
        hw_score = 1.0
        if _reliability_scorer:
            hw_score = _reliability_scorer.score_ping(
                bus_id=ping.bus_id or ping.trip_id,
                lat=ping.lat, lng=ping.lng,
                timestamp=ping.timestamp,
                speed=ping.speed,
            )

        _feature_store.update_bus_state(
            trip_id=ping.trip_id,
            lat=ping.lat, lng=ping.lng,
            h3_cell=h3_cell,
            speed=ping.speed or 0,
            heading=ping.heading or 0,
            hw_score=hw_score,
            passenger_count=ping.passenger_count or 0,
            status="active" if hw_score >= 0.3 else "ghost_suppressed",
        )
    elif ping.ping_type == "person":
        _feature_store.update_node_state(h3_index=h3_cell, person_ping_count=1)

    return {"status": "ingested", "h3_cell": h3_cell}
