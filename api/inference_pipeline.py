"""
Inference Pipeline — GPS → H3 → GNN → Map-Match → Response
================================================================
The end-to-end serving pipeline that transforms a raw GPS ping
into a map-matched, confidence-scored position prediction.

Pipeline stages:
1. Hardware Reliability Check (is this a ghost bus?)
2. H3 Cell Mapping (GPS → H3 L9 index)
3. Feature Fetch (Redis bulk read)
4. Graph Construction (HeteroData assembly)
5. GNN Forward Pass (attention-based message passing)
6. HMM Map-Matching (snap to road segment)
7. Google Maps ETA Calibration (blend GNN ETA with external signal)

Latency budget: < 200ms total
Target split: 5ms HW check, 2ms H3, 10ms Redis, 5ms graph, 100ms GNN, 30ms HMM, 48ms buffer
"""

import time
import logging
from datetime import datetime
from typing import Optional

import torch

logger = logging.getLogger(__name__)


class InferencePipeline:
    """
    Orchestrates the full inference pipeline.

    All components are injected for testability.
    Uses torch.cuda.amp for mixed-precision inference on GPU.
    """

    def __init__(
        self,
        model,               # SpatialGNN
        graph_builder,        # DynamicGraphBuilder
        feature_store,        # FeatureStoreClient
        data_fusion,          # DataFusion
        map_matcher,          # HMMMapMatcher
        reliability_scorer,   # HardwareReliabilityScorer
        ghost_recovery,       # GhostBusRecovery
        h3_resolution: int = 9,
        k_ring_radius: int = 2,
        use_amp: bool = True,
        device: Optional[str] = None,
    ):
        self.model = model
        self.graph_builder = graph_builder
        self.feature_store = feature_store
        self.data_fusion = data_fusion
        self.map_matcher = map_matcher
        self.reliability_scorer = reliability_scorer
        self.ghost_recovery = ghost_recovery
        self.h3_resolution = h3_resolution
        self.k_ring_radius = k_ring_radius
        self.use_amp = use_amp

        # Device selection
        if device:
            self.device = torch.device(device)
        elif torch.cuda.is_available():
            self.device = torch.device("cuda")
        else:
            self.device = torch.device("cpu")

        self.model.to(self.device)
        self.model.eval()

        # LSTM states for temporal continuity per bus
        self._lstm_states: dict[str, tuple] = {}

        logger.info(f"InferencePipeline initialized on {self.device}")

    def predict_position(
        self,
        trip_id: str,
        lat: float,
        lng: float,
        speed: Optional[float] = None,
        heading: Optional[float] = None,
        top_k: int = 3,
        timestamp: Optional[datetime] = None,
    ) -> dict:
        """
        Full position prediction pipeline.

        Returns dict matching PositionResponse schema.
        """
        t_start = time.perf_counter()
        timestamp = timestamp or datetime.now()

        from pulse_chennai.graph.h3_utils import latlng_to_h3, get_k_ring, h3_to_latlng

        # ── 1. H3 Mapping ──
        current_h3 = latlng_to_h3(lat, lng, self.h3_resolution)

        # ── 2. Hardware Reliability Check ──
        hw_score = 1.0
        if speed is not None:
            hw_score = self.reliability_scorer.score_ping(
                bus_id=trip_id, lat=lat, lng=lng,
                timestamp=timestamp.timestamp() * 1000, speed=speed,
            )

        # If ghost bus, delegate to ghost recovery
        if hw_score < 0.3:
            bus_state = self.feature_store.get_bus_state(trip_id)
            if bus_state:
                recovery = self.ghost_recovery.recover(
                    trip_id=trip_id,
                    last_known_state=bus_state,
                    timestamp=timestamp,
                )
                if recovery.get("status") == "recovered":
                    t_end = time.perf_counter()
                    return {
                        "trip_id": trip_id,
                        "primary_prediction": {
                            "h3_index": recovery["estimated_h3"],
                            "lat": recovery["lat"],
                            "lng": recovery["lng"],
                            "score": 1.0,
                            "confidence": recovery["confidence"],
                        },
                        "alternatives": [],
                        "snapped_lat": recovery["lat"],
                        "snapped_lng": recovery["lng"],
                        "road_segment": "ghost_recovered",
                        "road_class": "estimated",
                        "inference_ms": (t_end - t_start) * 1000,
                        "hw_reliability_score": hw_score,
                        "data_source": "ghost_recovery",
                    }

        # ── 3. Feature Fetch from Redis ──
        k_ring_cells = get_k_ring(current_h3, self.k_ring_radius)
        h3_states, traffic_scores = self.data_fusion.assemble_features(
            h3_cells=k_ring_cells,
            feature_store=self.feature_store,
            timestamp=timestamp,
        )

        # Get active buses in the area
        active_buses = self.feature_store.get_active_buses_in_cells(k_ring_cells)

        # ── 4. Graph Construction ──
        data = self.graph_builder.build_graph(
            center_h3=current_h3,
            h3_node_states=h3_states,
            active_buses=active_buses,
            timestamp=timestamp,
            traffic_scores=traffic_scores,
        )

        # ── 5. GNN Inference ──
        lstm_state = self._lstm_states.get(trip_id)

        with torch.no_grad():
            if self.use_amp and self.device.type == "cuda":
                with torch.cuda.amp.autocast():
                    result = self.model.predict_next_cell(
                        data=data, bus_lstm_state=lstm_state, top_k=top_k,
                    )
            else:
                result = self.model.predict_next_cell(
                    data=data, bus_lstm_state=lstm_state, top_k=top_k,
                )

        # Save LSTM state
        if result.get("lstm_state"):
            self._lstm_states[trip_id] = result["lstm_state"]

        top_cells = result.get("top_cells", [])
        if not top_cells:
            t_end = time.perf_counter()
            return {
                "trip_id": trip_id,
                "primary_prediction": {
                    "h3_index": current_h3, "lat": lat, "lng": lng,
                    "score": 0.0, "confidence": 0.0,
                },
                "alternatives": [],
                "snapped_lat": lat, "snapped_lng": lng,
                "road_segment": "none", "road_class": "unknown",
                "inference_ms": (t_end - t_start) * 1000,
                "hw_reliability_score": hw_score,
                "data_source": "fallback",
            }

        # ── 6. Map-Matching ──
        best = top_cells[0]
        pred_lat, pred_lng = h3_to_latlng(best["h3_index"])

        congestion = traffic_scores.get(best["h3_index"], 0.0)
        match_result = self.map_matcher.match_point(
            lat=pred_lat, lng=pred_lng,
            bus_heading=heading,
            congestion_score=congestion,
        )

        # Build alternatives
        alternatives = []
        for cell in top_cells[1:]:
            cell_lat, cell_lng = h3_to_latlng(cell["h3_index"])
            alternatives.append({
                "h3_index": cell["h3_index"],
                "lat": cell_lat,
                "lng": cell_lng,
                "score": cell["score"],
                "confidence": cell["confidence"],
            })

        t_end = time.perf_counter()
        inference_ms = (t_end - t_start) * 1000

        if inference_ms > 200:
            logger.warning(
                f"Inference latency {inference_ms:.1f}ms exceeds 200ms budget!"
            )

        return {
            "trip_id": trip_id,
            "primary_prediction": {
                "h3_index": best["h3_index"],
                "lat": pred_lat,
                "lng": pred_lng,
                "score": best["score"],
                "confidence": best["confidence"],
            },
            "alternatives": alternatives,
            "snapped_lat": match_result.snapped_lat,
            "snapped_lng": match_result.snapped_lng,
            "road_segment": match_result.segment_id,
            "road_class": match_result.road_class,
            "inference_ms": round(inference_ms, 2),
            "hw_reliability_score": hw_score,
            "data_source": "gnn_inference",
        }

    def predict_eta(
        self,
        trip_id: str,
        current_lat: float,
        current_lng: float,
        destination_lat: float,
        destination_lng: float,
        speed: Optional[float] = None,
        heading: Optional[float] = None,
        timestamp: Optional[datetime] = None,
    ) -> dict:
        """
        ETA prediction pipeline.
        Blends GNN ETA with Google Maps ETA for calibration.
        """
        t_start = time.perf_counter()
        timestamp = timestamp or datetime.now()

        from pulse_chennai.graph.h3_utils import latlng_to_h3

        current_h3 = latlng_to_h3(current_lat, current_lng, self.h3_resolution)
        dest_h3 = latlng_to_h3(destination_lat, destination_lng, self.h3_resolution)

        # GNN-based ETA
        position_result = self.predict_position(
            trip_id=trip_id, lat=current_lat, lng=current_lng,
            speed=speed, heading=heading, timestamp=timestamp,
        )

        gnn_eta = 0.0
        if "primary_prediction" in position_result:
            # Rough ETA from GNN output
            # In production: use the model's eta_regressor head directly
            from pulse_chennai.graph.h3_utils import _haversine
            dist_m = _haversine(current_lat, current_lng, destination_lat, destination_lng)
            avg_speed_ms = max((speed or 20) / 3.6, 1.0)  # km/h to m/s, min 1 m/s
            gnn_eta = dist_m / avg_speed_ms  # seconds

        # Google Maps ETA calibration
        gmaps_calibrated = False
        if self.data_fusion._gmaps:
            try:
                result = self.data_fusion._gmaps.distance_matrix(
                    origins=[(current_lat, current_lng)],
                    destinations=[(destination_lat, destination_lng)],
                    mode="transit",
                    departure_time="now",
                )
                element = result["rows"][0]["elements"][0]
                if element["status"] == "OK":
                    gmaps_eta = element["duration"]["value"]
                    # Blend: 70% GNN + 30% Google Maps
                    from pulse_chennai.config.settings import settings
                    w = settings.gmaps.ETA_CALIBRATION_WEIGHT
                    gnn_eta = (1 - w) * gnn_eta + w * gmaps_eta
                    gmaps_calibrated = True
            except Exception as e:
                logger.warning(f"Google Maps ETA calibration failed: {e}")

        t_end = time.perf_counter()

        return {
            "trip_id": trip_id,
            "eta_seconds": round(gnn_eta, 1),
            "eta_minutes": round(gnn_eta / 60, 1),
            "destination_h3": dest_h3,
            "current_h3": current_h3,
            "confidence": position_result.get("primary_prediction", {}).get("confidence", 0),
            "gmaps_calibrated": gmaps_calibrated,
            "inference_ms": round((t_end - t_start) * 1000, 2),
        }
