"""
Data Fusion Module — Collaborative Telemetry Core
=====================================================
Merges multi-source data into unified feature tensors:

1. AIS 140 bus GPS (weighted by hardware reliability score)
2. Anonymized passenger GPS pings (Collaborative Telemetry)
3. Google Maps Traffic API (external ground-truth calibration)
4. Historical S3 patterns (nightly ETL route features)

Innovation: When AIS 140 hardware is unreliable (hw_score < 0.3),
passenger pings in the same H3 cell become the PRIMARY signal.
This is the "crowdsourced verification" that makes Ghost Buses
recoverable without relying solely on ML hallucination.
"""

import time
import math
import logging
from typing import Optional
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)


class DataFusion:
    """
    Multi-source feature fusion engine.

    Combines heterogeneous data signals into normalized feature
    vectors suitable for GNN consumption.

    Key design principles:
    - Reliability-weighted: unreliable sources get downweighted
    - Temporal-aware: features encode time-of-day for drift handling
    - Fallback-first: always produces output even with partial data
    """

    def __init__(
        self,
        h3_feature_dim: int = 12,
        bus_feature_dim: int = 16,
        temporal_dim: int = 32,
        gmaps_api_key: Optional[str] = None,
        gmaps_weight: float = 0.3,
    ):
        self.h3_feature_dim = h3_feature_dim
        self.bus_feature_dim = bus_feature_dim
        self.temporal_dim = temporal_dim
        self.gmaps_weight = gmaps_weight

        # Google Maps client (stubbed if no key)
        self._gmaps = None
        if gmaps_api_key:
            try:
                import googlemaps
                self._gmaps = googlemaps.Client(key=gmaps_api_key)
                logger.info("Google Maps API client initialized")
            except ImportError:
                logger.warning("googlemaps not installed. Traffic data stubbed.")

    # ──────────────────────────────────────────────────────
    # Collaborative Telemetry: Passenger Ping Fusion
    # ──────────────────────────────────────────────────────

    def fuse_person_pings_to_bus_position(
        self,
        person_pings: list[dict],
        bus_last_known: dict,
        hw_score: float,
    ) -> dict:
        """
        Collaborative Telemetry core algorithm.

        When a bus has low hardware reliability, we estimate its
        true position by clustering passenger pings within the
        same H3 cell and its immediate neighbors.

        Weighting:
        - High hw_score (>0.7): bus GPS dominates (90% weight)
        - Medium hw_score (0.3-0.7): blended (hw_score × bus + rest × pings)
        - Low hw_score (<0.3): person pings dominate (90% weight)

        Args:
            person_pings: List of {lat, lng, timestamp} from passengers
            bus_last_known: {lat, lng, timestamp, speed, heading}
            hw_score: AIS 140 reliability score [0, 1]

        Returns:
            Fused position: {lat, lng, confidence, source}
        """
        if not person_pings:
            return {
                "lat": bus_last_known.get("lat", 0),
                "lng": bus_last_known.get("lng", 0),
                "confidence": hw_score,
                "source": "ais140_only",
            }

        # Filter recent person pings (last 60 seconds)
        now = time.time()
        recent_pings = [
            p for p in person_pings
            if (now - p.get("timestamp", 0) / 1000.0) < 60
        ]

        if not recent_pings:
            return {
                "lat": bus_last_known.get("lat", 0),
                "lng": bus_last_known.get("lng", 0),
                "confidence": hw_score,
                "source": "ais140_only",
            }

        # Compute mean position from person pings
        person_lat = np.mean([p["lat"] for p in recent_pings])
        person_lng = np.mean([p["lng"] for p in recent_pings])

        # Adaptive weighting based on hardware reliability
        if hw_score > 0.7:
            bus_weight = 0.9
        elif hw_score > 0.3:
            bus_weight = hw_score
        else:
            bus_weight = 0.1  # Almost entirely person-driven

        person_weight = 1.0 - bus_weight

        bus_lat = bus_last_known.get("lat", person_lat)
        bus_lng = bus_last_known.get("lng", person_lng)

        fused_lat = bus_weight * bus_lat + person_weight * person_lat
        fused_lng = bus_weight * bus_lng + person_weight * person_lng

        # Confidence: higher when more person pings agree
        position_spread = np.std([p["lat"] for p in recent_pings]) * 111_000  # meters
        ping_confidence = max(0.0, 1.0 - position_spread / 100.0)
        combined_confidence = 0.5 * hw_score + 0.5 * ping_confidence

        source = (
            "collaborative_fused"
            if person_weight > 0.3
            else "ais140_primary"
        )

        return {
            "lat": float(fused_lat),
            "lng": float(fused_lng),
            "confidence": float(combined_confidence),
            "source": source,
            "person_ping_count": len(recent_pings),
            "bus_weight": float(bus_weight),
        }

    # ──────────────────────────────────────────────────────
    # Google Maps Traffic Integration
    # ──────────────────────────────────────────────────────

    def get_traffic_scores(
        self, h3_cells: list[str]
    ) -> dict[str, float]:
        """
        Fetch traffic congestion scores for H3 cells from Google Maps.

        Returns congestion score [0, 1] per cell.
        0 = free-flowing, 1 = gridlocked.

        Falls back to stub values when API is unavailable.
        """
        from pulse_chennai.graph.h3_utils import h3_to_latlng

        scores = {}

        if self._gmaps:
            try:
                # Batch: get directions through cell centroids
                for cell in h3_cells[:20]:  # Rate limit
                    lat, lng = h3_to_latlng(cell)

                    # Use distance_matrix for a quick traffic signal
                    # Origin = destination = cell centroid (self-loop check)
                    result = self._gmaps.distance_matrix(
                        origins=[(lat, lng)],
                        destinations=[(lat + 0.001, lng + 0.001)],
                        mode="driving",
                        departure_time="now",
                        traffic_model="best_guess",
                    )

                    row = result["rows"][0]["elements"][0]
                    if row["status"] == "OK":
                        duration = row["duration"]["value"]
                        duration_traffic = row.get(
                            "duration_in_traffic", {}
                        ).get("value", duration)

                        # Congestion ratio
                        if duration > 0:
                            ratio = duration_traffic / duration
                            scores[cell] = min(1.0, max(0.0, (ratio - 1.0)))
                        else:
                            scores[cell] = 0.0
                    else:
                        scores[cell] = 0.0

            except Exception as e:
                logger.warning(f"Google Maps API error: {e}. Using stubs.")
                scores = self._stub_traffic_scores(h3_cells)
        else:
            scores = self._stub_traffic_scores(h3_cells)

        return scores

    def _stub_traffic_scores(
        self, h3_cells: list[str]
    ) -> dict[str, float]:
        """
        Generate synthetic traffic scores based on time of day.
        Chennai peak hours: 8-10 AM, 5-8 PM.
        """
        hour = datetime.now().hour
        base_congestion = 0.2  # Off-peak baseline

        if 8 <= hour <= 10:
            base_congestion = 0.7  # Morning rush
        elif 17 <= hour <= 20:
            base_congestion = 0.8  # Evening rush
        elif 12 <= hour <= 14:
            base_congestion = 0.4  # Lunch hour

        # Add some cell-level variance
        rng = np.random.RandomState(42)
        scores = {}
        for i, cell in enumerate(h3_cells):
            noise = rng.uniform(-0.15, 0.15)
            scores[cell] = max(0.0, min(1.0, base_congestion + noise))

        return scores

    # ──────────────────────────────────────────────────────
    # Historical Pattern Fusion
    # ──────────────────────────────────────────────────────

    def blend_historical_pattern(
        self,
        current_features: np.ndarray,
        pattern_vector: Optional[list[float]],
        current_hour: int,
        blend_weight: float = 0.2,
    ) -> np.ndarray:
        """
        Blend historical hourly speed pattern into current features.

        The pattern_vector is a 24-dim vector of average speeds per hour,
        computed by nightly ETL. The current hour's value is blended
        into the feature vector to provide "tomorrow's prediction" signal.

        Args:
            current_features: Current H3 cell feature vector
            pattern_vector: 24-dim hourly speed pattern from ETL
            current_hour: Current hour (0-23)
            blend_weight: How much historical data influences current features

        Returns:
            Blended feature vector (same shape)
        """
        if pattern_vector is None or len(pattern_vector) != 24:
            return current_features

        result = current_features.copy()

        # Blend the historical speed at current hour with live speed
        historical_speed = pattern_vector[current_hour] / 60.0  # Normalize

        # Feature index 1 is avg_speed (from graph_builder convention)
        if result.shape[-1] > 1:
            result[..., 1] = (
                (1 - blend_weight) * result[..., 1]
                + blend_weight * historical_speed
            )

        return result

    # ──────────────────────────────────────────────────────
    # Unified Feature Assembly
    # ──────────────────────────────────────────────────────

    def assemble_features(
        self,
        h3_cells: list[str],
        feature_store,
        timestamp: Optional[datetime] = None,
    ) -> tuple[dict[str, dict], dict[str, float]]:
        """
        Full feature assembly pipeline:
        1. Fetch node states from Redis
        2. Get traffic scores from Google Maps
        3. Fetch historical patterns
        4. Blend together

        Returns:
            (h3_states, traffic_scores)
        """
        timestamp = timestamp or datetime.now()

        # Redis fetch (bulk)
        h3_states = feature_store.get_node_states_bulk(h3_cells)

        # Google Maps traffic
        traffic_scores = self.get_traffic_scores(h3_cells)

        # Historical pattern blending
        for cell in h3_cells:
            pattern = feature_store.get_pattern_vector(cell)
            if pattern:
                state = h3_states.get(cell, {})
                # Update avg_speed with blended value
                historical_speed = pattern[timestamp.hour] if len(pattern) > timestamp.hour else 0
                current_speed = state.get("avg_speed", 0)
                blended = (1 - 0.2) * current_speed + 0.2 * historical_speed
                h3_states[cell]["avg_speed"] = blended

        return h3_states, traffic_scores
