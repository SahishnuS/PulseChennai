"""
Hardware Reliability Scorer
==============================
Continuously audits AIS 140 GPS unit health.

Scoring criteria:
- Ping frequency deviation (expected: ≥1 per 10s)
- GPS jitter (σ of consecutive positions > 50m = suspect)
- Impossible speed detection (>120 km/h)
- Stale data detection (no ping for >60s)

When hw_score < 0.3, the bus is flagged as "Ghost" and suppressed
from the live feed, switching to GNN-estimated state instead.

This is a NOVEL component — Chennai One currently has no hardware
auditing layer. Faulty AIS 140 units broadcast indefinitely,
creating phantom buses on the map.
"""

import time
import math
import logging
from dataclasses import dataclass, field
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)

# Earth radius in meters for Haversine
EARTH_RADIUS_M = 6_371_000


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two GPS points (meters)."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + (
        math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


@dataclass
class BusPingHistory:
    """Rolling window of recent pings for a single bus."""
    timestamps: deque = field(default_factory=lambda: deque(maxlen=50))
    positions: deque = field(default_factory=lambda: deque(maxlen=50))
    speeds: deque = field(default_factory=lambda: deque(maxlen=50))
    jitter_distances: deque = field(default_factory=lambda: deque(maxlen=50))
    rolling_score: float = 1.0
    impossible_speed_count: int = 0
    total_pings: int = 0


class HardwareReliabilityScorer:
    """
    Scores AIS 140 hardware health per bus in real-time.

    The score is a composite of four sub-scores [0, 1]:
    - Frequency Score:  How consistently the unit pings
    - Jitter Score:     Positional stability (low σ = good)
    - Speed Score:      No impossible velocities
    - Freshness Score:  How recent the last ping was

    Final: hw_score = 0.3·freq + 0.25·jitter + 0.25·speed + 0.2·freshness
    Applied with exponential decay to smooth transient glitches.
    """

    # Sub-score weights
    W_FREQUENCY = 0.30
    W_JITTER = 0.25
    W_SPEED = 0.25
    W_FRESHNESS = 0.20

    def __init__(
        self,
        min_ping_freq: float = 0.1,       # 1 ping per 10 seconds
        max_jitter_m: float = 50.0,        # meters
        max_speed_kmh: float = 120.0,
        stale_threshold_s: float = 60.0,
        ghost_threshold: float = 0.3,
        decay_rate: float = 0.95,
    ):
        self.min_ping_freq = min_ping_freq
        self.max_jitter_m = max_jitter_m
        self.max_speed_kmh = max_speed_kmh
        self.stale_threshold_s = stale_threshold_s
        self.ghost_threshold = ghost_threshold
        self.decay_rate = decay_rate

        # Per-bus ping history
        self._history: dict[str, BusPingHistory] = {}

    def _get_history(self, bus_id: str) -> BusPingHistory:
        if bus_id not in self._history:
            self._history[bus_id] = BusPingHistory()
        return self._history[bus_id]

    def _frequency_score(self, history: BusPingHistory) -> float:
        """
        Score based on ping frequency consistency.
        Expected: at least min_ping_freq Hz.
        """
        if len(history.timestamps) < 2:
            return 1.0  # Not enough data to penalize

        intervals = []
        ts_list = list(history.timestamps)
        for i in range(1, len(ts_list)):
            dt = (ts_list[i] - ts_list[i - 1]) / 1000.0  # ms to seconds
            if dt > 0:
                intervals.append(dt)

        if not intervals:
            return 1.0

        avg_interval = sum(intervals) / len(intervals)
        expected_interval = 1.0 / self.min_ping_freq  # 10 seconds

        # Score: 1.0 if on time, decays if too slow
        if avg_interval <= expected_interval:
            return 1.0
        return max(0.0, 1.0 - (avg_interval - expected_interval) / expected_interval)

    def _jitter_score(self, history: BusPingHistory) -> float:
        """
        Score based on GPS positional stability.
        High jitter (σ > max_jitter_m) indicates faulty hardware.
        """
        if len(history.jitter_distances) < 3:
            return 1.0

        distances = list(history.jitter_distances)
        mean_d = sum(distances) / len(distances)
        variance = sum((d - mean_d) ** 2 for d in distances) / len(distances)
        sigma = math.sqrt(variance)

        if sigma <= self.max_jitter_m:
            return 1.0
        return max(0.0, 1.0 - (sigma - self.max_jitter_m) / self.max_jitter_m)

    def _speed_score(self, history: BusPingHistory) -> float:
        """
        Score based on impossible speed detection.
        Buses reporting >120 km/h are physically impossible on Chennai roads.
        """
        if history.total_pings == 0:
            return 1.0

        violation_ratio = history.impossible_speed_count / max(
            history.total_pings, 1
        )
        return max(0.0, 1.0 - violation_ratio * 5)  # 20% violations = score 0

    def _freshness_score(self, history: BusPingHistory) -> float:
        """
        Score based on how recent the last ping was.
        Stale for >60s = decaying score.
        """
        if not history.timestamps:
            return 0.0

        last_ts = history.timestamps[-1] / 1000.0  # ms to seconds
        age = time.time() - last_ts

        if age <= self.stale_threshold_s:
            return 1.0
        return max(0.0, 1.0 - (age - self.stale_threshold_s) / self.stale_threshold_s)

    def score_ping(
        self,
        bus_id: str,
        lat: float,
        lng: float,
        timestamp: float,
        speed: Optional[float] = None,
    ) -> float:
        """
        Process a single GPS ping and return the updated hw_score.

        Args:
            bus_id: Unique identifier for the bus/AIS 140 unit
            lat, lng: GPS coordinates
            timestamp: Unix timestamp in milliseconds
            speed: Reported speed in km/h (optional)

        Returns:
            hw_score in [0.0, 1.0]. Below ghost_threshold = ghost bus.
        """
        history = self._get_history(bus_id)
        history.total_pings += 1

        # Record timestamp
        history.timestamps.append(timestamp)

        # Calculate jitter distance from previous position
        if history.positions:
            prev_lat, prev_lng = history.positions[-1]
            dist = haversine_distance(prev_lat, prev_lng, lat, lng)
            history.jitter_distances.append(dist)

            # Compute speed from position change if not reported
            if len(history.timestamps) >= 2:
                dt = (history.timestamps[-1] - history.timestamps[-2]) / 1000.0
                if dt > 0:
                    computed_speed_kmh = (dist / dt) * 3.6  # m/s to km/h
                    if computed_speed_kmh > self.max_speed_kmh:
                        history.impossible_speed_count += 1

        # Check reported speed for impossibility
        if speed is not None and speed > self.max_speed_kmh:
            history.impossible_speed_count += 1

        # Record position
        history.positions.append((lat, lng))
        if speed is not None:
            history.speeds.append(speed)

        # Compute composite score
        freq_s = self._frequency_score(history)
        jitter_s = self._jitter_score(history)
        speed_s = self._speed_score(history)
        fresh_s = self._freshness_score(history)

        raw_score = (
            self.W_FREQUENCY * freq_s
            + self.W_JITTER * jitter_s
            + self.W_SPEED * speed_s
            + self.W_FRESHNESS * fresh_s
        )

        # Exponential moving average to smooth transient glitches
        history.rolling_score = (
            self.decay_rate * history.rolling_score
            + (1 - self.decay_rate) * raw_score
        )

        final_score = round(history.rolling_score, 4)

        if final_score < self.ghost_threshold:
            logger.warning(
                f"GHOST BUS DETECTED: {bus_id} | score={final_score:.4f} "
                f"(freq={freq_s:.2f}, jitter={jitter_s:.2f}, "
                f"speed={speed_s:.2f}, fresh={fresh_s:.2f})"
            )

        return final_score

    def is_ghost(self, bus_id: str) -> bool:
        """Check if a bus is currently flagged as a ghost."""
        history = self._history.get(bus_id)
        if not history:
            return False
        return history.rolling_score < self.ghost_threshold

    def get_all_scores(self) -> dict[str, float]:
        """Return current hw_scores for all tracked buses."""
        return {
            bus_id: round(h.rolling_score, 4)
            for bus_id, h in self._history.items()
        }

    def get_ghost_buses(self) -> list[str]:
        """Return list of bus IDs currently flagged as ghosts."""
        return [
            bus_id
            for bus_id, h in self._history.items()
            if h.rolling_score < self.ghost_threshold
        ]

    def reset_bus(self, bus_id: str) -> None:
        """Reset scoring history for a bus (e.g., after hardware replacement)."""
        if bus_id in self._history:
            del self._history[bus_id]
            logger.info(f"Reset reliability history for bus {bus_id}")
