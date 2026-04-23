"""
Feature Store Module (Speed Layer)
=====================================
Redis-backed real-time node state cache for low-latency
GNN message passing. Stores H3 cell features and bus states.

Key design:
- Hash maps for structured node data
- TTL-based eviction for stale entries
- Bulk operations for graph construction batches
"""

import json
import time
import logging
from typing import Optional
import redis

logger = logging.getLogger(__name__)


class FeatureStoreClient:
    """
    Redis Feature Store for the GNN's real-time speed layer.

    Key schema:
      node:{h3_index} -> Hash {
          bus_count, avg_speed, congestion_score,
          passenger_density, person_ping_count, last_updated
      }
      bus:{trip_id} -> Hash {
          lat, lng, h3_cell, speed, heading, status,
          hw_score, passenger_count, last_seen
      }
      pattern:{h3_index} -> String (JSON-serialized 24-dim vector)
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        node_ttl: int = 300,
        bus_ttl: int = 300,
    ):
        self._pool = redis.ConnectionPool(
            host=host, port=port, db=db, password=password,
            decode_responses=True, max_connections=50,
        )
        self._client = redis.Redis(connection_pool=self._pool)
        self.node_ttl = node_ttl
        self.bus_ttl = bus_ttl

        # Verify connection
        try:
            self._client.ping()
            logger.info(f"FeatureStore connected to Redis at {host}:{port}")
        except redis.ConnectionError:
            logger.warning(
                f"Redis not available at {host}:{port}. "
                "Running in degraded mode (no caching)."
            )

    # ──────────────────────────────────────────────────────
    # H3 Node State Operations
    # ──────────────────────────────────────────────────────

    def update_node_state(
        self,
        h3_index: str,
        bus_count: int = 0,
        avg_speed: float = 0.0,
        congestion_score: float = 0.0,
        passenger_density: float = 0.0,
        person_ping_count: int = 0,
    ) -> None:
        """Update the real-time state of an H3 cell."""
        key = f"node:{h3_index}"
        pipe = self._client.pipeline()
        pipe.hset(key, mapping={
            "bus_count": bus_count,
            "avg_speed": round(avg_speed, 2),
            "congestion_score": round(congestion_score, 4),
            "passenger_density": round(passenger_density, 4),
            "person_ping_count": person_ping_count,
            "last_updated": time.time(),
        })
        pipe.expire(key, self.node_ttl)
        pipe.execute()

    def get_node_state(self, h3_index: str) -> Optional[dict]:
        """Retrieve the current state of an H3 cell."""
        key = f"node:{h3_index}"
        data = self._client.hgetall(key)
        if not data:
            return None
        return {
            "bus_count": int(data.get("bus_count", 0)),
            "avg_speed": float(data.get("avg_speed", 0)),
            "congestion_score": float(data.get("congestion_score", 0)),
            "passenger_density": float(data.get("passenger_density", 0)),
            "person_ping_count": int(data.get("person_ping_count", 0)),
            "last_updated": float(data.get("last_updated", 0)),
        }

    def get_node_states_bulk(self, h3_indices: list[str]) -> dict[str, dict]:
        """
        Bulk fetch node states for graph construction.
        Uses Redis pipeline for batch efficiency.
        Returns dict mapping h3_index -> state dict.
        """
        pipe = self._client.pipeline()
        for idx in h3_indices:
            pipe.hgetall(f"node:{idx}")

        results = pipe.execute()
        states = {}
        for idx, data in zip(h3_indices, results):
            if data:
                states[idx] = {
                    "bus_count": int(data.get("bus_count", 0)),
                    "avg_speed": float(data.get("avg_speed", 0)),
                    "congestion_score": float(data.get("congestion_score", 0)),
                    "passenger_density": float(data.get("passenger_density", 0)),
                    "person_ping_count": int(data.get("person_ping_count", 0)),
                    "last_updated": float(data.get("last_updated", 0)),
                }
            else:
                # Return zero-state for missing cells (unseen area)
                states[idx] = {
                    "bus_count": 0,
                    "avg_speed": 0.0,
                    "congestion_score": 0.0,
                    "passenger_density": 0.0,
                    "person_ping_count": 0,
                    "last_updated": 0.0,
                }
        return states

    # ──────────────────────────────────────────────────────
    # Bus State Operations
    # ──────────────────────────────────────────────────────

    def update_bus_state(
        self,
        trip_id: str,
        lat: float,
        lng: float,
        h3_cell: str,
        speed: float = 0.0,
        heading: float = 0.0,
        hw_score: float = 1.0,
        passenger_count: int = 0,
        status: str = "active",
    ) -> None:
        """Update the real-time state of a bus."""
        key = f"bus:{trip_id}"
        pipe = self._client.pipeline()
        pipe.hset(key, mapping={
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "h3_cell": h3_cell,
            "speed": round(speed, 2),
            "heading": round(heading, 2),
            "hw_score": round(hw_score, 4),
            "passenger_count": passenger_count,
            "status": status,
            "last_seen": time.time(),
        })
        pipe.expire(key, self.bus_ttl)
        pipe.execute()

    def get_bus_state(self, trip_id: str) -> Optional[dict]:
        """Retrieve the current state of a bus."""
        key = f"bus:{trip_id}"
        data = self._client.hgetall(key)
        if not data:
            return None
        return {
            "lat": float(data.get("lat", 0)),
            "lng": float(data.get("lng", 0)),
            "h3_cell": data.get("h3_cell", ""),
            "speed": float(data.get("speed", 0)),
            "heading": float(data.get("heading", 0)),
            "hw_score": float(data.get("hw_score", 1)),
            "passenger_count": int(data.get("passenger_count", 0)),
            "status": data.get("status", "unknown"),
            "last_seen": float(data.get("last_seen", 0)),
        }

    def get_active_buses_in_cells(
        self, h3_cells: list[str]
    ) -> list[dict]:
        """
        Find all active buses in the given H3 cells.
        Scans bus:* keys and filters by h3_cell membership.

        Note: In production, maintain a Redis Set per H3 cell
        for O(1) lookup instead of SCAN.
        """
        cell_set = set(h3_cells)
        buses = []

        # Use SCAN to avoid blocking (production: use secondary index)
        cursor = 0
        while True:
            cursor, keys = self._client.scan(
                cursor=cursor, match="bus:*", count=100
            )
            if keys:
                pipe = self._client.pipeline()
                for key in keys:
                    pipe.hgetall(key)
                results = pipe.execute()

                for key, data in zip(keys, results):
                    if data and data.get("h3_cell") in cell_set:
                        trip_id = key.replace("bus:", "")
                        buses.append({
                            "trip_id": trip_id,
                            **{
                                "lat": float(data.get("lat", 0)),
                                "lng": float(data.get("lng", 0)),
                                "h3_cell": data.get("h3_cell", ""),
                                "speed": float(data.get("speed", 0)),
                                "heading": float(data.get("heading", 0)),
                                "hw_score": float(data.get("hw_score", 1)),
                                "passenger_count": int(
                                    data.get("passenger_count", 0)
                                ),
                                "status": data.get("status", "unknown"),
                                "last_seen": float(data.get("last_seen", 0)),
                            },
                        })

            if cursor == 0:
                break

        return buses

    # ──────────────────────────────────────────────────────
    # Historical Pattern Cache (from nightly ETL)
    # ──────────────────────────────────────────────────────

    def set_pattern_vector(
        self, h3_index: str, pattern: list[float]
    ) -> None:
        """Store the 24-dim hourly speed pattern for an H3 cell."""
        self._client.set(
            f"pattern:{h3_index}",
            json.dumps(pattern),
            ex=86400,  # 24h TTL
        )

    def get_pattern_vector(self, h3_index: str) -> Optional[list[float]]:
        """Retrieve the hourly speed pattern for an H3 cell."""
        data = self._client.get(f"pattern:{h3_index}")
        if data:
            return json.loads(data)
        return None

    # ──────────────────────────────────────────────────────
    # Utility
    # ──────────────────────────────────────────────────────

    def flush_all(self) -> None:
        """Clear all data. USE ONLY IN TESTING."""
        self._client.flushdb()
        logger.warning("FeatureStore flushed all data!")

    def health_check(self) -> bool:
        """Check Redis connectivity."""
        try:
            return self._client.ping()
        except redis.ConnectionError:
            return False
