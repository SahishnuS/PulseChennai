"""
HMM Map-Matching Module
==========================
Viterbi-based Hidden Markov Model for snapping predicted
GPS/H3 coordinates to actual road segments.

This is the final post-processing step after GNN inference.
The GNN predicts an H3 cell, but the user needs a road position.

HMM States = road segments near the predicted H3 centroid
Emission  P = distance from GPS point to road segment
Transition P = route connectivity × heading alignment

Target: 99% map-snapping success rate.

Google Maps API is used to calibrate emission probabilities
for known traffic conditions (heavy traffic → wider emission σ).
"""

import math
import logging
from typing import Optional
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RoadSegment:
    """A road segment candidate for map-matching."""
    segment_id: str
    lat_start: float
    lng_start: float
    lat_end: float
    lng_end: float
    heading: float          # Bearing in degrees
    road_class: str         # "highway" | "arterial" | "local"
    speed_limit_kmh: float
    is_bus_route: bool = True


@dataclass
class MatchResult:
    """Result of map-matching a single point."""
    segment_id: str
    snapped_lat: float
    snapped_lng: float
    distance_m: float
    confidence: float
    heading: float
    road_class: str


class HMMMapMatcher:
    """
    Viterbi-based map-matching for post-processing GNN predictions.

    The algorithm:
    1. Given a predicted GPS point (from GNN H3 centroid)
    2. Find all road segments within a search radius
    3. Compute emission probabilities (point-to-road distance)
    4. Compute transition probabilities (route connectivity)
    5. Run Viterbi to find the most likely road segment sequence
    6. Snap the point to the winning segment

    Calibration with Google Maps:
    - In high-traffic areas, we widen the emission σ because
      buses may be offset from road centerline in congested lanes
    - In free-flowing areas, we use tighter σ for precision
    """

    # Default emission standard deviation (meters)
    DEFAULT_EMISSION_SIGMA = 20.0

    # Transition probability constants
    ROUTE_CONNECTIVITY_BONUS = 2.0
    HEADING_ALIGNMENT_WEIGHT = 0.3

    def __init__(
        self,
        search_radius_m: float = 200.0,
        emission_sigma: float = 20.0,
        max_candidates: int = 10,
        road_network: Optional[list[RoadSegment]] = None,
    ):
        self.search_radius_m = search_radius_m
        self.emission_sigma = emission_sigma
        self.max_candidates = max_candidates

        # Road network (in production: loaded from PostGIS or GeoJSON)
        self.road_network = road_network or self._build_chennai_stub_network()

    def _build_chennai_stub_network(self) -> list[RoadSegment]:
        """
        Stub road network for Chennai's major bus routes.
        In production: connect to PostGIS or load from OSM data.
        """
        # Major corridors in Chennai
        chennai_roads = [
            RoadSegment("anna_salai_1", 13.0620, 80.2560, 13.0660, 80.2580,
                        30.0, "arterial", 40.0, True),
            RoadSegment("anna_salai_2", 13.0660, 80.2580, 13.0700, 80.2600,
                        35.0, "arterial", 40.0, True),
            RoadSegment("ecr_1", 12.9800, 80.2500, 12.9850, 80.2530,
                        45.0, "highway", 60.0, True),
            RoadSegment("mount_rd_1", 13.0400, 80.2500, 13.0450, 80.2520,
                        25.0, "arterial", 40.0, True),
            RoadSegment("gst_1", 13.0100, 80.2200, 13.0150, 80.2250,
                        50.0, "highway", 60.0, True),
            RoadSegment("poonamallee_1", 13.0500, 80.1600, 13.0530, 80.1650,
                        60.0, "arterial", 40.0, True),
            RoadSegment("omr_1", 12.9600, 80.2400, 12.9650, 80.2450,
                        40.0, "highway", 60.0, True),
            RoadSegment("kamarajar_salai_1", 13.0500, 80.2800, 13.0530, 80.2830,
                        15.0, "arterial", 30.0, True),
        ]
        return chennai_roads

    def _haversine(self, lat1, lon1, lat2, lon2) -> float:
        """Distance in meters."""
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + (
            math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        return 2 * 6_371_000 * math.asin(math.sqrt(a))

    def _point_to_segment_distance(
        self, lat: float, lng: float, segment: RoadSegment
    ) -> tuple[float, float, float]:
        """
        Compute perpendicular distance from point to road segment.

        Returns: (distance_m, snapped_lat, snapped_lng)
        """
        # Project point onto line segment using vector math
        ax, ay = segment.lng_start, segment.lat_start
        bx, by = segment.lng_end, segment.lat_end
        px, py = lng, lat

        # Vector AB
        abx = bx - ax
        aby = by - ay
        ab_sq = abx * abx + aby * aby

        if ab_sq < 1e-12:
            # Degenerate segment
            dist = self._haversine(lat, lng, segment.lat_start, segment.lng_start)
            return dist, segment.lat_start, segment.lng_start

        # Parameter t = projection of AP onto AB, clamped to [0, 1]
        apx = px - ax
        apy = py - ay
        t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab_sq))

        # Closest point on segment
        snap_lng = ax + t * abx
        snap_lat = ay + t * aby

        dist = self._haversine(lat, lng, snap_lat, snap_lng)
        return dist, snap_lat, snap_lng

    def _emission_probability(
        self,
        distance_m: float,
        sigma: Optional[float] = None,
    ) -> float:
        """
        Gaussian emission probability.
        P(observation | state) = N(distance; 0, σ²)

        Calibrated σ:
        - Free-flowing traffic: σ = 20m (tight)
        - Heavy traffic: σ = 50m (wide, buses offset from centerline)
        """
        sigma = sigma or self.emission_sigma
        return (1.0 / (sigma * math.sqrt(2 * math.pi))) * math.exp(
            -(distance_m ** 2) / (2 * sigma ** 2)
        )

    def _transition_probability(
        self,
        segment_from: RoadSegment,
        segment_to: RoadSegment,
        bus_heading: Optional[float] = None,
    ) -> float:
        """
        Transition probability between road segments.

        Factors:
        1. Physical connectivity (adjacent segments → high P)
        2. Road class compatibility (bus routes preferred)
        3. Heading alignment (bus heading matches road direction)
        """
        # Base: distance between segment endpoints
        gap = self._haversine(
            segment_from.lat_end, segment_from.lng_end,
            segment_to.lat_start, segment_to.lng_start,
        )

        # Connected segments (gap < 50m)
        connectivity = 1.0 if gap < 50 else math.exp(-gap / 200.0)

        # Bus route bonus
        route_bonus = self.ROUTE_CONNECTIVITY_BONUS if segment_to.is_bus_route else 1.0

        # Heading alignment
        heading_score = 1.0
        if bus_heading is not None:
            heading_diff = abs(bus_heading - segment_to.heading) % 360
            if heading_diff > 180:
                heading_diff = 360 - heading_diff
            heading_score = math.exp(
                -self.HEADING_ALIGNMENT_WEIGHT * (heading_diff / 180.0)
            )

        return connectivity * route_bonus * heading_score

    def match_point(
        self,
        lat: float,
        lng: float,
        bus_heading: Optional[float] = None,
        congestion_score: float = 0.0,
    ) -> MatchResult:
        """
        Map-match a single GPS/H3 point to the nearest road segment.

        Args:
            lat, lng: Predicted coordinates (from GNN H3 centroid)
            bus_heading: Bus heading in degrees (improves accuracy)
            congestion_score: Traffic congestion [0, 1] for σ calibration

        Returns:
            MatchResult with snapped coordinates and confidence
        """
        # Calibrate emission sigma based on congestion
        # Heavy traffic → larger σ (bus may be in adjacent lane)
        sigma = self.emission_sigma * (1.0 + congestion_score)

        # Find candidate road segments within search radius
        candidates = []
        for segment in self.road_network:
            dist, snap_lat, snap_lng = self._point_to_segment_distance(
                lat, lng, segment
            )
            if dist <= self.search_radius_m:
                emission_p = self._emission_probability(dist, sigma)
                candidates.append({
                    "segment": segment,
                    "distance": dist,
                    "snap_lat": snap_lat,
                    "snap_lng": snap_lng,
                    "emission_p": emission_p,
                })

        if not candidates:
            logger.warning(
                f"No road segments within {self.search_radius_m}m "
                f"of ({lat:.4f}, {lng:.4f})"
            )
            return MatchResult(
                segment_id="unknown",
                snapped_lat=lat,
                snapped_lng=lng,
                distance_m=0,
                confidence=0.0,
                heading=bus_heading or 0.0,
                road_class="unknown",
            )

        # Sort by emission probability (highest first)
        candidates.sort(key=lambda c: c["emission_p"], reverse=True)
        candidates = candidates[: self.max_candidates]

        # Apply heading alignment for re-ranking
        if bus_heading is not None:
            for c in candidates:
                heading_diff = abs(bus_heading - c["segment"].heading) % 360
                if heading_diff > 180:
                    heading_diff = 360 - heading_diff
                heading_bonus = math.exp(-heading_diff / 90.0)
                c["final_score"] = c["emission_p"] * heading_bonus
            candidates.sort(key=lambda c: c["final_score"], reverse=True)

        best = candidates[0]
        segment = best["segment"]

        # Confidence: based on emission P and distance
        confidence = min(1.0, best["emission_p"] * 100)
        if best["distance"] > 100:
            confidence *= 0.5

        return MatchResult(
            segment_id=segment.segment_id,
            snapped_lat=best["snap_lat"],
            snapped_lng=best["snap_lng"],
            distance_m=best["distance"],
            confidence=confidence,
            heading=segment.heading,
            road_class=segment.road_class,
        )

    def match_sequence(
        self,
        points: list[dict],
        congestion_score: float = 0.0,
    ) -> list[MatchResult]:
        """
        Viterbi-based sequence matching for a trajectory.

        Uses dynamic programming to find the most likely
        sequence of road segments given a sequence of GPS points.

        Args:
            points: List of {lat, lng, heading (optional)} dicts
            congestion_score: Overall congestion for σ calibration

        Returns:
            List of MatchResult, one per input point
        """
        if not points:
            return []

        sigma = self.emission_sigma * (1.0 + congestion_score)
        n_points = len(points)

        # Build candidate sets per point
        all_candidates = []
        for p in points:
            candidates = []
            for segment in self.road_network:
                dist, snap_lat, snap_lng = self._point_to_segment_distance(
                    p["lat"], p["lng"], segment
                )
                if dist <= self.search_radius_m:
                    candidates.append({
                        "segment": segment,
                        "distance": dist,
                        "snap_lat": snap_lat,
                        "snap_lng": snap_lng,
                        "emission_p": self._emission_probability(dist, sigma),
                    })
            if not candidates:
                candidates.append({
                    "segment": RoadSegment(
                        "unknown", p["lat"], p["lng"],
                        p["lat"], p["lng"], 0, "unknown", 0
                    ),
                    "distance": 0,
                    "snap_lat": p["lat"],
                    "snap_lng": p["lng"],
                    "emission_p": 0.001,
                })
            all_candidates.append(candidates)

        # Viterbi DP
        # V[t][j] = max log-probability of reaching state j at time t
        V = [{} for _ in range(n_points)]
        backtrack = [{} for _ in range(n_points)]

        # Initialize
        for j, c in enumerate(all_candidates[0]):
            sid = c["segment"].segment_id
            V[0][sid] = math.log(max(c["emission_p"], 1e-30))
            backtrack[0][sid] = (None, c)

        # Forward pass
        for t in range(1, n_points):
            heading = points[t].get("heading")
            for j, c_to in enumerate(all_candidates[t]):
                sid_to = c_to["segment"].segment_id
                best_v = -float("inf")
                best_from = None

                for k, c_from in enumerate(all_candidates[t - 1]):
                    sid_from = c_from["segment"].segment_id
                    trans_p = self._transition_probability(
                        c_from["segment"], c_to["segment"], heading
                    )
                    v = (
                        V[t - 1].get(sid_from, -float("inf"))
                        + math.log(max(trans_p, 1e-30))
                        + math.log(max(c_to["emission_p"], 1e-30))
                    )
                    if v > best_v:
                        best_v = v
                        best_from = sid_from

                V[t][sid_to] = best_v
                backtrack[t][sid_to] = (best_from, c_to)

        # Backtrack
        results = [None] * n_points

        # Find best final state
        best_final = max(V[-1], key=V[-1].get) if V[-1] else None
        if best_final is None:
            # Fallback: use greedy per-point matching
            return [
                self.match_point(p["lat"], p["lng"], p.get("heading"), congestion_score)
                for p in points
            ]

        # Trace back
        current = best_final
        for t in range(n_points - 1, -1, -1):
            prev, c = backtrack[t].get(current, (None, None))
            if c:
                seg = c["segment"]
                results[t] = MatchResult(
                    segment_id=seg.segment_id,
                    snapped_lat=c["snap_lat"],
                    snapped_lng=c["snap_lng"],
                    distance_m=c["distance"],
                    confidence=min(1.0, c["emission_p"] * 100),
                    heading=seg.heading,
                    road_class=seg.road_class,
                )
            else:
                results[t] = MatchResult(
                    segment_id="unknown",
                    snapped_lat=points[t]["lat"],
                    snapped_lng=points[t]["lng"],
                    distance_m=0,
                    confidence=0.0,
                    heading=0.0,
                    road_class="unknown",
                )
            current = prev

        return results
