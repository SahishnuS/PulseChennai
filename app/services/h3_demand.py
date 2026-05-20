"""
H3 Demand Heatmap Service
=========================
Aggregates passenger pings into H3 hexagonal demand cells
with a rolling 10-minute TTL window.
"""

import time
from collections import defaultdict
from typing import Dict, List

try:
    import h3
    H3_AVAILABLE = True
except ImportError:
    H3_AVAILABLE = False
    print("WARNING: h3 library not installed. Run: pip install h3")

# ── In-memory stores ──────────────────────────────────────────────────────────
# hex_id → list of epoch timestamps (float)
hex_timestamps: Dict[str, List[float]] = defaultdict(list)

_TTL_SECONDS = 600  # 10-minute rolling window
_LEVEL_THRESHOLDS = {"high": 8, "medium": 3}  # >8 = high, 3-8 = medium, <3 = low


# ── Core helpers ──────────────────────────────────────────────────────────────

def bin_ping_to_hex(lat: float, lng: float, resolution: int = 8) -> str:
    """Returns the H3 index string for a coordinate at given resolution."""
    if not H3_AVAILABLE:
        # Graceful fallback: encode as coarse grid cell string
        return f"{round(lat, 2)}:{round(lng, 2)}"
    return h3.latlng_to_cell(lat, lng, resolution)


def _demand_level(count: int) -> str:
    if count > _LEVEL_THRESHOLDS["high"]:
        return "high"
    elif count >= _LEVEL_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def _prune_hex(hex_id: str, now: float) -> int:
    """Remove stale timestamps and return current live count."""
    cutoff = now - _TTL_SECONDS
    hex_timestamps[hex_id] = [t for t in hex_timestamps[hex_id] if t >= cutoff]
    return len(hex_timestamps[hex_id])


# ── Public API ────────────────────────────────────────────────────────────────

def record_ping(lat: float, lng: float, resolution: int = 8) -> str:
    """
    Accept a passenger ping, bin it into an H3 cell, and store timestamp.
    Returns the hex_id for the ping.
    """
    hex_id = bin_ping_to_hex(lat, lng, resolution)
    hex_timestamps[hex_id].append(time.time())
    return hex_id


def get_demand_hexes() -> list:
    """
    For each hex with at least 1 live ping (within 10-min TTL window), return
    its demand metadata including center, boundary, count, and demand level.
    """
    now = time.time()
    results = []

    for hex_id in list(hex_timestamps.keys()):
        count = _prune_hex(hex_id, now)
        if count == 0:
            continue

        if H3_AVAILABLE:
            lat, lng = h3.cell_to_latlng(hex_id)
            # h3.cell_to_boundary returns [(lat, lng), ...] tuples
            boundary_raw = h3.cell_to_boundary(hex_id)
            boundary = [[p[0], p[1]] for p in boundary_raw]
        else:
            # Fallback: approximate center from encoded key
            try:
                parts = hex_id.split(":")
                lat, lng = float(parts[0]), float(parts[1])
            except Exception:
                lat, lng = 13.0827, 80.2707
            # Tiny square boundary approximation
            d = 0.005
            boundary = [
                [lat - d, lng - d], [lat - d, lng + d],
                [lat + d, lng + d], [lat + d, lng - d]
            ]

        results.append({
            "hex_id": hex_id,
            "count": count,
            "center": [lat, lng],
            "boundary": boundary,
            "level": _demand_level(count),
        })

    # Sort by count descending so frontend can prioritise dense cells
    results.sort(key=lambda x: x["count"], reverse=True)
    return results
