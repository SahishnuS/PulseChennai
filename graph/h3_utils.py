"""
H3 Hexagonal Indexing Utilities
==================================
Core spatial operations for H3 cell mapping, k-ring neighborhoods,
adjacency construction, and feature vector extraction.

H3 resolutions used:
- L8 (~461m edge): City-block level, used for S3 partitioning
- L9 (~174m edge): Intersection level, used for GNN graph nodes

Why H3 over grid squares?
- Zero overlap at edges (no diagonal ambiguity)
- Uniform neighbor distance (6 equidistant neighbors vs 4+4)
- Natural fit for GNN message passing on spatial graphs

Supports both h3 v3 (geo_to_h3) and h3 v4 (latlng_to_cell) APIs.
"""

import math
import logging
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)

try:
    import h3
    H3_AVAILABLE = True
    # Detect h3 version
    H3_V4 = hasattr(h3, 'latlng_to_cell')
except ImportError:
    H3_AVAILABLE = False
    H3_V4 = False
    logger.warning("h3 library not installed. Using stub implementations.")


def latlng_to_h3(lat: float, lng: float, resolution: int = 9) -> str:
    """
    Convert GPS coordinates to H3 cell index.

    Args:
        lat: Latitude in degrees
        lng: Longitude in degrees
        resolution: H3 resolution (8 or 9)

    Returns:
        H3 cell index string (e.g., '89754e64d53ffff')
    """
    if H3_AVAILABLE:
        if H3_V4:
            return h3.latlng_to_cell(lat, lng, resolution)
        else:
            return h3.geo_to_h3(lat, lng, resolution)
    # Stub for testing without h3 installed
    return f"stub_{resolution}_{round(lat, 4)}_{round(lng, 4)}"


def h3_to_latlng(h3_index: str) -> tuple[float, float]:
    """
    Get the centroid coordinates of an H3 cell.

    Returns:
        (lat, lng) tuple
    """
    if H3_AVAILABLE:
        if H3_V4:
            return h3.cell_to_latlng(h3_index)
        else:
            return h3.h3_to_geo(h3_index)
    # Stub: parse from stub format
    if h3_index.startswith("stub_"):
        parts = h3_index.split("_")
        return float(parts[2]), float(parts[3])
    return 0.0, 0.0


def get_k_ring(h3_index: str, k: int = 2) -> list[str]:
    """
    Get the k-ring neighborhood of an H3 cell.
    k=1 gives 7 cells (center + 6 neighbors).
    k=2 gives 19 cells.

    This defines the receptive field for GNN message passing.

    Args:
        h3_index: Center cell index
        k: Ring radius

    Returns:
        List of H3 cell indices including the center
    """
    if H3_AVAILABLE:
        if H3_V4:
            return list(h3.grid_disk(h3_index, k))
        else:
            return list(h3.k_ring(h3_index, k))
    # Stub: return synthetic neighbors
    return [f"{h3_index}_ring{i}" for i in range(max(1, 3 * k * (k + 1) + 1))]


def h3_distance(h3_a: str, h3_b: str) -> int:
    """
    Grid distance between two H3 cells (number of hops).

    Args:
        h3_a, h3_b: H3 cell indices

    Returns:
        Integer grid distance (0 = same cell)
    """
    if H3_AVAILABLE:
        try:
            if H3_V4:
                return h3.grid_distance(h3_a, h3_b)
            else:
                return h3.h3_distance(h3_a, h3_b)
        except Exception:
            return -1  # Cells in different base cells
    return 1


def get_neighbors(h3_index: str) -> list[str]:
    """
    Get the 6 immediate neighbors of an H3 cell.
    These form the direct edges in the GNN spatial graph.
    """
    if H3_AVAILABLE:
        if H3_V4:
            ring = list(h3.grid_ring(h3_index, 1))
        else:
            ring = list(h3.hex_ring(h3_index, 1))
        return ring
    return [f"{h3_index}_n{i}" for i in range(6)]


def build_h3_adjacency(
    center_h3: str,
    radius_k: int = 2,
) -> tuple[list[str], list[tuple[int, int]], list[float]]:
    """
    Build the adjacency structure for an H3 neighborhood graph.

    Returns:
        - nodes: List of H3 cell indices
        - edges: List of (src_idx, dst_idx) tuples
        - weights: Edge weights (inverse of grid distance)

    The edge weights encode spatial proximity:
    closer cells have higher weight in message passing.
    """
    nodes = get_k_ring(center_h3, radius_k)
    node_to_idx = {n: i for i, n in enumerate(nodes)}

    edges = []
    weights = []

    for node in nodes:
        neighbors = get_neighbors(node)
        for neighbor in neighbors:
            if neighbor in node_to_idx:
                src_idx = node_to_idx[node]
                dst_idx = node_to_idx[neighbor]
                edges.append((src_idx, dst_idx))

                # Weight: inverse distance (closer = stronger influence)
                dist = h3_distance(node, neighbor)
                weight = 1.0 / max(dist, 1)
                weights.append(weight)

    logger.debug(
        f"Built adjacency: {len(nodes)} nodes, {len(edges)} edges "
        f"(center={center_h3}, k={radius_k})"
    )
    return nodes, edges, weights


def compute_temporal_encoding(
    hour: int, day_of_week: int, dim: int = 32
) -> np.ndarray:
    """
    Sinusoidal temporal encoding for time-of-day and day-of-week.

    This addresses the mentor's DATA DRIFT concern:
    Monday morning traffic ≠ Sunday night traffic.

    We encode time cyclically to capture periodic patterns:
    - Hour: 24-hour cycle
    - Day:  7-day cycle

    Args:
        hour: Hour of day (0-23)
        day_of_week: Day of week (0=Monday, 6=Sunday)
        dim: Encoding dimension

    Returns:
        numpy array of shape (dim,)
    """
    encoding = np.zeros(dim, dtype=np.float32)
    half_dim = dim // 2

    for i in range(half_dim):
        # Hour encoding (24-hour period)
        freq_h = 2 * math.pi * (i + 1) / 24
        encoding[2 * i] = math.sin(freq_h * hour)
        encoding[2 * i + 1] = math.cos(freq_h * hour)

    # Overlay day-of-week in the second half
    quarter_dim = half_dim // 2
    for i in range(quarter_dim):
        freq_d = 2 * math.pi * (i + 1) / 7
        idx = half_dim + 2 * i
        if idx + 1 < dim:
            encoding[idx] = math.sin(freq_d * day_of_week)
            encoding[idx + 1] = math.cos(freq_d * day_of_week)

    return encoding


def h3_cell_area_m2(h3_index: str) -> float:
    """Get the area of an H3 cell in square meters."""
    if H3_AVAILABLE:
        if H3_V4:
            return h3.cell_area(h3_index, unit="m^2")
        else:
            return h3.hex_area(9, unit="m^2")
    # Approximate for L9
    return 105_332.0  # ~0.1 km²


def cells_along_path(
    lat_start: float, lng_start: float,
    lat_end: float, lng_end: float,
    resolution: int = 9, step_meters: float = 100.0,
) -> list[str]:
    """
    Get all H3 cells along a straight-line path between two points.
    Useful for estimating route coverage.

    Args:
        step_meters: Interpolation step size

    Returns:
        Ordered list of unique H3 cell indices along the path
    """
    dist = _haversine(lat_start, lng_start, lat_end, lng_end)
    n_steps = max(2, int(dist / step_meters))

    cells = []
    seen = set()
    for i in range(n_steps + 1):
        t = i / n_steps
        lat = lat_start + t * (lat_end - lat_start)
        lng = lng_start + t * (lng_end - lng_start)
        cell = latlng_to_h3(lat, lng, resolution)
        if cell not in seen:
            cells.append(cell)
            seen.add(cell)

    return cells


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + (
        math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(a))
