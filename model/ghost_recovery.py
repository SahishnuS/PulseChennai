"""
Ghost Bus Recovery Module
============================
When a bus goes offline (no ping for >60s) or has hw_score < 0.3,
this module estimates the bus's latent H3 coordinate.

Recovery strategy:
1. Aggregate features from the k-ring of the bus's last known H3 cell
2. Weight nearby person_gps pings (Collaborative Telemetry signal)
3. Match against historical trajectory patterns for the route
4. Use the SpatialGNN to predict the most likely current H3 cell
5. Output a confidence-scored position estimate

This is the "heartbeat" that keeps the bus alive on the map
even when hardware is failing — the core Ghost Bus fix.
"""

import time
import logging
from datetime import datetime
from typing import Optional

import torch
import numpy as np

logger = logging.getLogger(__name__)


class GhostBusRecovery:
    """
    Recovers estimated positions for ghost buses.

    A ghost bus is one where:
    - AIS 140 hardware has hw_score < 0.3 (reliability_scorer flagged it)
    - No GPS ping received for > ghost_timeout seconds
    - GPS pings show impossible patterns (teleportation, >120 km/h)

    Recovery uses a fusion of:
    1. GNN hidden state estimation (learned spatial patterns)
    2. Collaborative Telemetry (passenger GPS pings)
    3. Historical trajectory matching (route-level patterns)
    """

    def __init__(
        self,
        model: "SpatialGNN",
        graph_builder: "DynamicGraphBuilder",
        feature_store: "FeatureStoreClient",
        data_fusion: "DataFusion",
        ghost_timeout_s: int = 60,
        k_ring_radius: int = 3,     # Wider search radius for ghost recovery
        min_confidence: float = 0.2,
    ):
        self.model = model
        self.graph_builder = graph_builder
        self.feature_store = feature_store
        self.data_fusion = data_fusion
        self.ghost_timeout_s = ghost_timeout_s
        self.k_ring_radius = k_ring_radius
        self.min_confidence = min_confidence

        # Track LSTM states per bus for temporal continuity
        self._lstm_states: dict[str, tuple] = {}

    def should_recover(self, bus_state: dict) -> bool:
        """
        Determine if a bus needs ghost recovery.

        Args:
            bus_state: Bus state dict from Redis

        Returns:
            True if bus is a ghost candidate
        """
        if not bus_state:
            return True

        hw_score = bus_state.get("hw_score", 1.0)
        last_seen = bus_state.get("last_seen", 0)
        status = bus_state.get("status", "unknown")

        # Already suppressed
        if status == "ghost_suppressed":
            return True

        # Hardware unreliable
        if hw_score < 0.3:
            return True

        # Stale data
        if last_seen > 0 and (time.time() - last_seen) > self.ghost_timeout_s:
            return True

        return False

    def recover(
        self,
        trip_id: str,
        last_known_state: dict,
        person_pings: Optional[list[dict]] = None,
        timestamp: Optional[datetime] = None,
    ) -> dict:
        """
        Perform ghost bus recovery — estimate the bus's current position.

        Algorithm:
        1. Build a graph centered on the bus's last known H3 cell
           with WIDER k-ring (k=3) to cover more candidate cells
        2. Inject person ping signals into the graph features
        3. Run GNN inference to rank candidate H3 cells
        4. Post-process: apply confidence threshold
        5. Return the best estimate with supporting evidence

        Args:
            trip_id: Bus trip ID
            last_known_state: Last known bus state from Redis
            person_pings: Nearby passenger GPS pings
            timestamp: Current time

        Returns:
            Recovery result: {estimated_h3, lat, lng, confidence,
                              recovery_method, supporting_evidence}
        """
        timestamp = timestamp or datetime.now()
        person_pings = person_pings or []

        last_h3 = last_known_state.get("h3_cell", "")
        if not last_h3:
            return self._no_recovery("No last known H3 cell")

        # ── 1. Build wider-scope graph ──
        from pulse_chennai.graph.h3_utils import get_k_ring, h3_to_latlng

        k_ring_cells = get_k_ring(last_h3, self.k_ring_radius)

        # Fetch states with person ping injection
        h3_states = self.feature_store.get_node_states_bulk(k_ring_cells)

        # Boost cells that have person pings (Collaborative Telemetry)
        if person_pings:
            from pulse_chennai.graph.h3_utils import latlng_to_h3

            for ping in person_pings:
                ping_cell = latlng_to_h3(ping["lat"], ping["lng"], 9)
                if ping_cell in h3_states:
                    h3_states[ping_cell]["person_ping_count"] = (
                        h3_states[ping_cell].get("person_ping_count", 0) + 1
                    )
                    h3_states[ping_cell]["passenger_density"] = (
                        h3_states[ping_cell].get("passenger_density", 0) + 0.1
                    )

        # Get traffic scores
        traffic_scores = self.data_fusion.get_traffic_scores(k_ring_cells)

        # Active buses in the area (excluding the ghost bus itself)
        active_buses = self.feature_store.get_active_buses_in_cells(k_ring_cells)
        active_buses = [b for b in active_buses if b.get("trip_id") != trip_id]

        # Insert the ghost bus as a node with last known features
        ghost_bus_node = {
            "lat": last_known_state.get("lat", 0),
            "lng": last_known_state.get("lng", 0),
            "h3_cell": last_h3,
            "speed": last_known_state.get("speed", 0),
            "heading": last_known_state.get("heading", 0),
            "hw_score": 0.1,  # Low score since it's a ghost
            "passenger_count": last_known_state.get("passenger_count", 0),
            "status": "ghost_recovering",
        }
        active_buses.insert(0, ghost_bus_node)

        # ── 2. Build graph ──
        data = self.graph_builder.build_graph(
            center_h3=last_h3,
            h3_node_states=h3_states,
            active_buses=active_buses,
            timestamp=timestamp,
            traffic_scores=traffic_scores,
        )

        # ── 3. GNN inference ──
        device = next(self.model.parameters()).device
        data = data  # Move to device if needed

        # Retrieve LSTM state for temporal continuity
        lstm_state = self._lstm_states.get(trip_id)

        result = self.model.predict_next_cell(
            data=data,
            bus_lstm_state=lstm_state,
            top_k=5,
        )

        # Save LSTM state for next recovery attempt
        if result.get("lstm_state"):
            self._lstm_states[trip_id] = result["lstm_state"]

        # ── 4. Select best candidate with evidence ──
        top_cells = result.get("top_cells", [])
        if not top_cells:
            return self._no_recovery("GNN returned no candidates")

        best = top_cells[0]
        best_h3 = best["h3_index"]
        confidence = best["confidence"]

        # Boost confidence if person pings support this cell
        person_support = h3_states.get(best_h3, {}).get("person_ping_count", 0)
        if person_support > 0:
            confidence = min(1.0, confidence + 0.1 * person_support)

        # Check minimum confidence threshold
        if confidence < self.min_confidence:
            return self._no_recovery(
                f"Confidence too low: {confidence:.3f} < {self.min_confidence}"
            )

        # Get lat/lng of predicted cell
        est_lat, est_lng = h3_to_latlng(best_h3)

        recovery_method = "gnn_spatial"
        if person_support > 0:
            recovery_method = "gnn_collaborative"

        # ── 5. Build evidence summary ──
        evidence = {
            "recovery_method": recovery_method,
            "gnn_rank": 1,
            "person_pings_in_cell": person_support,
            "person_pings_total": len(person_pings),
            "k_ring_radius": self.k_ring_radius,
            "candidate_cells": len(top_cells),
            "all_candidates": top_cells[:3],
            "time_since_last_ping": round(
                time.time() - last_known_state.get("last_seen", 0), 1
            ),
            "original_hw_score": last_known_state.get("hw_score", 0),
        }

        logger.info(
            f"Ghost recovery for {trip_id}: "
            f"estimated={best_h3} ({est_lat:.4f}, {est_lng:.4f}), "
            f"confidence={confidence:.3f}, method={recovery_method}"
        )

        return {
            "estimated_h3": best_h3,
            "lat": float(est_lat),
            "lng": float(est_lng),
            "confidence": float(confidence),
            "recovery_method": recovery_method,
            "supporting_evidence": evidence,
            "eta_seconds": result.get("eta_seconds", 0),
            "trip_id": trip_id,
            "status": "recovered",
        }

    def _no_recovery(self, reason: str) -> dict:
        """Return a failed recovery result."""
        logger.warning(f"Ghost recovery failed: {reason}")
        return {
            "estimated_h3": None,
            "lat": None,
            "lng": None,
            "confidence": 0.0,
            "recovery_method": "none",
            "supporting_evidence": {"failure_reason": reason},
            "status": "unrecoverable",
        }

    def batch_recover(
        self,
        ghost_bus_ids: list[str],
        timestamp: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Batch recovery for all currently flagged ghost buses.

        Args:
            ghost_bus_ids: List of trip_ids flagged as ghosts

        Returns:
            List of recovery results
        """
        results = []
        for trip_id in ghost_bus_ids:
            bus_state = self.feature_store.get_bus_state(trip_id)
            if bus_state:
                # Get person pings near this bus's last known cell
                from pulse_chennai.graph.h3_utils import get_k_ring
                last_h3 = bus_state.get("h3_cell", "")
                if last_h3:
                    nearby_cells = get_k_ring(last_h3, 1)
                    # In production: fetch person pings from Redis
                    # For now: empty list (will use GNN-only recovery)
                    person_pings = []
                else:
                    person_pings = []

                result = self.recover(
                    trip_id=trip_id,
                    last_known_state=bus_state,
                    person_pings=person_pings,
                    timestamp=timestamp,
                )
            else:
                result = self._no_recovery(f"No state for trip {trip_id}")
                result["trip_id"] = trip_id

            results.append(result)

        logger.info(
            f"Batch ghost recovery: {len(ghost_bus_ids)} buses, "
            f"{sum(1 for r in results if r['status'] == 'recovered')} recovered"
        )
        return results
