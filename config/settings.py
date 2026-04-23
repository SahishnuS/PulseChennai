"""
Pulse-Chennai Configuration
============================
All environment variables, constants, and hyperparameters for the system.
Uses pydantic-settings for validated env-var loading.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class H3Config(BaseSettings):
    """H3 hexagonal indexing configuration."""
    RESOLUTION_L8: int = 8          # City-block level (~460m edge)
    RESOLUTION_L9: int = 9          # Intersection level (~174m edge)
    DEFAULT_RESOLUTION: int = 9     # Use L9 for fine-grained inference
    K_RING_RADIUS: int = 2          # 2-ring neighborhood for graph construction


class RedisConfig(BaseSettings):
    """Redis Feature Store (Speed Layer) configuration."""
    REDIS_HOST: str = Field(default="localhost", alias="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, alias="REDIS_PORT")
    REDIS_DB: int = Field(default=0, alias="REDIS_DB")
    REDIS_PASSWORD: Optional[str] = Field(default=None, alias="REDIS_PASSWORD")
    NODE_TTL_SECONDS: int = 300     # 5 min TTL for stale node data
    BUS_TTL_SECONDS: int = 300      # 5 min TTL for stale bus data


class KafkaConfig(BaseSettings):
    """Kafka Ingestion Pipeline configuration."""
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="localhost:9092", alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    BUS_GPS_TOPIC: str = "bus_gps_pings"
    PERSON_GPS_TOPIC: str = "person_gps_pings"
    CONSUMER_GROUP: str = "pulse_chennai_consumers"
    S3_FLUSH_INTERVAL_SECONDS: int = 30   # Flush write buffer to S3 every 30s


class S3Config(BaseSettings):
    """S3 Data Lake (Batch Layer) configuration."""
    S3_BUCKET: str = Field(default="pulse-chennai-datalake", alias="S3_BUCKET")
    S3_REGION: str = Field(default="ap-south-1", alias="S3_REGION")
    PARQUET_PARTITION_COLS: list[str] = ["h3_l8", "date"]
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(
        default=None, alias="AWS_SECRET_ACCESS_KEY"
    )


class GNNConfig(BaseSettings):
    """Spatial-Temporal GNN hyperparameters."""
    # Architecture
    HIDDEN_DIM: int = 128
    NUM_HEADS: int = 4              # GAT attention heads
    NUM_LAYERS: int = 3             # GAT depth
    DROPOUT: float = 0.2
    TEMPORAL_DIM: int = 32          # Sinusoidal time encoding dimension
    LSTM_HIDDEN: int = 64           # Temporal LSTM hidden size

    # Node feature dimensions (computed from DataFusion output)
    H3_FEATURE_DIM: int = 12       # congestion, density, speed, time_enc...
    BUS_FEATURE_DIM: int = 16      # position_emb, speed, heading, hw_score...

    # Loss weights (Kendall multi-task)
    BPR_WEIGHT: float = 0.6
    MSE_WEIGHT: float = 0.4

    # Training
    LEARNING_RATE: float = 1e-3
    WEIGHT_DECAY: float = 1e-5
    BATCH_SIZE: int = 64
    EPOCHS: int = 100


class HardwareConfig(BaseSettings):
    """AIS 140 Hardware Reliability Scoring thresholds."""
    MIN_PING_FREQUENCY_HZ: float = 0.1     # At least 1 ping per 10 seconds
    MAX_GPS_JITTER_METERS: float = 50.0     # σ of consecutive positions
    MAX_SPEED_KMH: float = 120.0            # Impossible speed threshold
    STALE_THRESHOLD_SECONDS: float = 60.0   # No ping for 60s = stale
    GHOST_THRESHOLD: float = 0.3            # hw_score < 0.3 → suppress bus
    SCORE_DECAY_RATE: float = 0.95          # Exponential decay for rolling score


class InferenceConfig(BaseSettings):
    """Inference and serving constraints."""
    MAX_INFERENCE_MS: int = 200     # Latency budget
    USE_CUDA: bool = True
    USE_AMP: bool = True            # Mixed-precision inference
    MODEL_PATH: str = "models/spatial_gnn_v1.pt"
    GHOST_RECOVERY_TIMEOUT_S: int = 60   # Trigger recovery after 60s offline


class GoogleMapsConfig(BaseSettings):
    """Google Maps API for ETA calibration (optional)."""
    GMAPS_API_KEY: Optional[str] = Field(default=None, alias="GMAPS_API_KEY")
    TRAFFIC_MODEL: str = "best_guess"   # pessimistic | best_guess | optimistic
    ETA_CALIBRATION_WEIGHT: float = 0.3  # Blend factor with GNN ETA


class TomTomConfig(BaseSettings):
    """TomTom Traffic Flow API — free real-time traffic (2,500 req/day)."""
    TOMTOM_API_KEY: Optional[str] = Field(default=None, alias="TOMTOM_API_KEY")
    CACHE_TTL_SECONDS: int = 30         # Cache per-cell result for 30s
    REQUEST_TIMEOUT_S: int = 5          # API call timeout
    ETA_CALIBRATION_WEIGHT: float = 0.3 # Blend factor with GNN ETA


class Settings(BaseSettings):
    """Master configuration aggregating all subsystems."""
    h3: H3Config = H3Config()
    redis: RedisConfig = RedisConfig()
    kafka: KafkaConfig = KafkaConfig()
    s3: S3Config = S3Config()
    gnn: GNNConfig = GNNConfig()
    hardware: HardwareConfig = HardwareConfig()
    inference: InferenceConfig = InferenceConfig()
    gmaps: GoogleMapsConfig = GoogleMapsConfig()
    tomtom: TomTomConfig = TomTomConfig()

    # Chennai bounding box (for validation)
    CHENNAI_LAT_MIN: float = 12.8
    CHENNAI_LAT_MAX: float = 13.3
    CHENNAI_LNG_MIN: float = 80.1
    CHENNAI_LNG_MAX: float = 80.35

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton instance
settings = Settings()
