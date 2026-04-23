"""
Pydantic Schemas — API Request/Response Models
=================================================
Type-safe data contracts for the FastAPI serving layer.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ──────────────────────────────────────────────────────
# Request Models
# ──────────────────────────────────────────────────────

class GPSPing(BaseModel):
    """Raw GPS ping from a bus or passenger."""
    lat: float = Field(..., ge=-90, le=90, description="Latitude")
    lng: float = Field(..., ge=-180, le=180, description="Longitude")
    timestamp: float = Field(..., description="Unix timestamp in ms")
    bus_id: Optional[str] = Field(None, description="Bus device ID")
    trip_id: Optional[str] = Field(None, description="Trip identifier")
    speed: Optional[float] = Field(None, ge=0, description="Speed in km/h")
    heading: Optional[float] = Field(None, ge=0, le=360, description="Heading in degrees")
    passenger_count: Optional[int] = Field(None, ge=0)
    ping_type: str = Field("bus", description="'bus' or 'person'")


class PositionRequest(BaseModel):
    """Request for bus position prediction."""
    trip_id: str = Field(..., description="Active trip ID")
    current_lat: float = Field(..., ge=-90, le=90)
    current_lng: float = Field(..., ge=-180, le=180)
    speed: Optional[float] = Field(None, ge=0)
    heading: Optional[float] = Field(None, ge=0, le=360)
    top_k: int = Field(3, ge=1, le=10, description="Number of candidate cells")


class ETARequest(BaseModel):
    """Request for ETA prediction."""
    trip_id: str
    current_lat: float = Field(..., ge=-90, le=90)
    current_lng: float = Field(..., ge=-180, le=180)
    destination_lat: float = Field(..., ge=-90, le=90)
    destination_lng: float = Field(..., ge=-180, le=180)
    speed: Optional[float] = None
    heading: Optional[float] = None


class GhostRecoveryRequest(BaseModel):
    """Request to recover a ghost bus's position."""
    trip_id: str
    last_known_lat: Optional[float] = None
    last_known_lng: Optional[float] = None
    person_pings: Optional[list[dict]] = Field(
        default=None,
        description="Nearby passenger GPS pings for Collaborative Telemetry"
    )


# ──────────────────────────────────────────────────────
# Response Models
# ──────────────────────────────────────────────────────

class H3CellPrediction(BaseModel):
    """A single H3 cell prediction."""
    h3_index: str
    lat: float
    lng: float
    score: float
    confidence: float


class PositionResponse(BaseModel):
    """Response for position prediction."""
    trip_id: str
    primary_prediction: H3CellPrediction
    alternatives: list[H3CellPrediction] = []
    snapped_lat: float = Field(..., description="Map-matched latitude")
    snapped_lng: float = Field(..., description="Map-matched longitude")
    road_segment: str = Field(..., description="Matched road segment ID")
    road_class: str = Field("unknown", description="Road classification")
    inference_ms: float = Field(..., description="Inference latency in ms")
    hw_reliability_score: Optional[float] = None
    data_source: str = Field("gnn_inference", description="How position was determined")


class ETAResponse(BaseModel):
    """Response for ETA prediction."""
    trip_id: str
    eta_seconds: float = Field(..., description="Predicted ETA in seconds")
    eta_minutes: float = Field(..., description="Predicted ETA in minutes")
    destination_h3: str
    current_h3: str
    confidence: float
    gmaps_calibrated: bool = Field(
        False, description="Whether Google Maps ETA was used for calibration"
    )
    inference_ms: float


class GhostRecoveryResponse(BaseModel):
    """Response for ghost bus recovery."""
    trip_id: str
    status: str = Field(..., description="'recovered' or 'unrecoverable'")
    estimated_h3: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    confidence: float = 0.0
    recovery_method: str = "none"
    supporting_evidence: dict = {}
    eta_seconds: Optional[float] = None


class BusStatusResponse(BaseModel):
    """Full status of a single bus."""
    trip_id: str
    lat: float
    lng: float
    h3_cell: str
    speed: float
    heading: float
    hw_reliability_score: float
    passenger_count: int
    status: str  # "active" | "ghost_suppressed" | "recovered" | "offline"
    last_seen: float
    is_ghost: bool


class HealthCheckResponse(BaseModel):
    """System health check."""
    status: str  # "healthy" | "degraded" | "unhealthy"
    model_loaded: bool
    redis_connected: bool
    cuda_available: bool
    gpu_name: Optional[str] = None
    uptime_seconds: float
    version: str
