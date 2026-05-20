"""
Historical ETA Store — Pulse-Chennai
=====================================
Loads uber_data.csv and builds in-memory lookup tables indexed by
(sourceid, dstid, hod) for sub-millisecond historical ETA retrieval.

Also precomputes per-zone aggregate statistics (source_avg_time,
dest_avg_time) required as input features for the ML ensemble models.

Implements a thread-safe, lazy-loading singleton pattern so the ~825K-row
dataset is loaded at most once per process lifetime.

Usage:
    from traffic.historical_eta_store import get_store
    store = get_store()
    eta = store.get_historical_eta(sourceid=42, dstid=117, hod=8)
"""

import os
import math
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import pytz

logger = logging.getLogger(__name__)

# IST timezone for all time calculations
IST = pytz.timezone("Asia/Kolkata")

# ── Chennai-specific constants ────────────────────────────────────────────────
# Indian public holidays (month, day) — major national + Tamil Nadu holidays
INDIAN_PUBLIC_HOLIDAYS: List[Tuple[int, int]] = [
    (1, 1),    # New Year
    (1, 14),   # Pongal
    (1, 15),   # Thiruvalluvar Day
    (1, 26),   # Republic Day
    (4, 14),   # Tamil New Year
    (5, 1),    # May Day
    (8, 15),   # Independence Day
    (10, 2),   # Gandhi Jayanti
    (11, 1),   # Diwali (approximate)
    (12, 25),  # Christmas
]

# Chennai-specific rush hour windows (IST hours)
CHENNAI_MORNING_RUSH = range(8, 11)    # 08:00 – 10:59
CHENNAI_EVENING_RUSH = range(17, 21)   # 17:00 – 20:59
CHENNAI_LUNCH_PEAK   = range(12, 15)   # 12:00 – 14:59 (school/office lunch)
CHENNAI_LATE_NIGHT   = list(range(22, 24)) + list(range(0, 6))  # 22:00 – 05:59


class HistoricalETAStore:
    """Thread-safe in-memory store for historical travel time data.

    Attributes:
        _lookup: Dict mapping (sourceid, dstid, hod) → {mean_travel_time, std, ...}
        _source_avg: Dict mapping sourceid → average mean_travel_time across all
                     destinations and hours.
        _dest_avg: Dict mapping dstid → average mean_travel_time across all
                   sources and hours.
        _all_source_ids: Sorted list of unique source IDs for nearest-zone lookup.
        _all_dest_ids: Sorted list of unique destination IDs.
    """

    def __init__(self) -> None:
        self._lookup: Dict[Tuple[int, int, int], dict] = {}
        self._source_avg: Dict[int, float] = {}
        self._dest_avg: Dict[int, float] = {}
        self._source_dest_avg: Dict[Tuple[int, int], float] = {}
        self._all_source_ids: List[int] = []
        self._all_dest_ids: List[int] = []
        self._global_mean: float = 0.0
        self._loaded: bool = False
        self._lock = threading.Lock()

    # ── Loading ───────────────────────────────────────────────────────────────

    def load(self, csv_path: Optional[str] = None) -> None:
        """Load uber_data.csv and build all lookup structures.

        Args:
            csv_path: Optional explicit path. Defaults to
                      ``<project_root>/data/uber_data.csv``.
        """
        if self._loaded:
            return

        with self._lock:
            # Double-check after acquiring lock
            if self._loaded:
                return

            if csv_path is None:
                project_root = Path(__file__).resolve().parent.parent
                csv_path = str(project_root / "data" / "uber_data.csv")

            logger.info("HistoricalETAStore: loading %s …", csv_path)

            if not os.path.exists(csv_path):
                logger.error("HistoricalETAStore: %s not found!", csv_path)
                self._loaded = True  # Mark loaded to avoid repeated attempts
                return

            try:
                import pandas as pd

                df = pd.read_csv(csv_path)
                logger.info(
                    "HistoricalETAStore: loaded %d rows, columns=%s",
                    len(df), list(df.columns),
                )

                # ── Build primary lookup: (sourceid, dstid, hod) → record ─────
                for _, row in df.iterrows():
                    key = (int(row["sourceid"]), int(row["dstid"]), int(row["hod"]))
                    self._lookup[key] = {
                        "mean_travel_time": float(row["mean_travel_time"]),
                        "std_travel_time": float(row.get(
                            "standard_deviation_travel_time", 0
                        )),
                        "geo_mean": float(row.get(
                            "geometric_mean_travel_time", row["mean_travel_time"]
                        )),
                        "geo_std": float(row.get(
                            "geometric_standard_deviation_travel_time", 0
                        )),
                    }

                # ── Precompute per-zone aggregates ────────────────────────────
                self._source_avg = (
                    df.groupby("sourceid")["mean_travel_time"]
                    .mean()
                    .to_dict()
                )
                self._dest_avg = (
                    df.groupby("dstid")["mean_travel_time"]
                    .mean()
                    .to_dict()
                )
                self._source_dest_avg = (
                    df.groupby(["sourceid", "dstid"])["mean_travel_time"]
                    .mean()
                    .to_dict()
                )
                self._global_mean = float(df["mean_travel_time"].mean())

                self._all_source_ids = sorted(df["sourceid"].unique().tolist())
                self._all_dest_ids = sorted(df["dstid"].unique().tolist())

                logger.info(
                    "HistoricalETAStore: ready — %d lookup entries, "
                    "%d sources, %d destinations, global_mean=%.1fs",
                    len(self._lookup),
                    len(self._all_source_ids),
                    len(self._all_dest_ids),
                    self._global_mean,
                )
                self._loaded = True

            except Exception:
                logger.exception("HistoricalETAStore: failed to load data")
                self._loaded = True  # Avoid infinite retries

    # ── Public query methods ──────────────────────────────────────────────────

    def get_historical_eta(
        self,
        sourceid: int,
        dstid: int,
        hod: Optional[int] = None,
    ) -> Optional[dict]:
        """Look up historical travel time for a (source, dest, hour) triple.

        Args:
            sourceid: Source zone ID from uber_data.
            dstid: Destination zone ID from uber_data.
            hod: Hour of day (0-23). Defaults to current IST hour.

        Returns:
            Dict with ``mean_travel_time``, ``std_travel_time``, etc.
            or ``None`` if no data is available for this combination.
        """
        self._ensure_loaded()

        if hod is None:
            hod = datetime.now(IST).hour

        key = (sourceid, dstid, hod)
        return self._lookup.get(key)

    def get_yesterday_eta(
        self,
        sourceid: int,
        dstid: int,
    ) -> Optional[float]:
        """Get average travel time across all hours for a source–dest pair.

        Useful as a "yesterday" or "typical day" baseline.

        Args:
            sourceid: Source zone ID.
            dstid: Destination zone ID.

        Returns:
            Average travel time in seconds, or ``None``.
        """
        self._ensure_loaded()
        return self._source_dest_avg.get((sourceid, dstid))

    def get_source_avg_time(self, sourceid: int) -> float:
        """Get average travel time for trips originating from ``sourceid``.

        This is the ``source_avg_time`` feature required by XGB/LGB models.

        Returns:
            Average seconds. Falls back to global mean if zone is unknown.
        """
        self._ensure_loaded()
        return self._source_avg.get(sourceid, self._global_mean)

    def get_dest_avg_time(self, dstid: int) -> float:
        """Get average travel time for trips arriving at ``dstid``.

        This is the ``dest_avg_time`` feature required by XGB/LGB models.

        Returns:
            Average seconds. Falls back to global mean if zone is unknown.
        """
        self._ensure_loaded()
        return self._dest_avg.get(dstid, self._global_mean)

    def get_nearest_source_id(self, target_id: int) -> int:
        """Find the nearest valid source zone ID.

        Uses simple numeric proximity as a fallback when exact zone ID
        is not present in the dataset.

        Args:
            target_id: Desired zone ID.

        Returns:
            Closest valid sourceid from the dataset.
        """
        self._ensure_loaded()
        if not self._all_source_ids:
            return target_id
        if target_id in self._source_avg:
            return target_id
        # Binary-search-like nearest
        return min(self._all_source_ids, key=lambda x: abs(x - target_id))

    def get_nearest_dest_id(self, target_id: int) -> int:
        """Find the nearest valid destination zone ID."""
        self._ensure_loaded()
        if not self._all_dest_ids:
            return target_id
        if target_id in self._dest_avg:
            return target_id
        return min(self._all_dest_ids, key=lambda x: abs(x - target_id))

    @property
    def all_source_ids(self) -> List[int]:
        """Sorted list of all unique source zone IDs."""
        self._ensure_loaded()
        return self._all_source_ids

    @property
    def all_dest_ids(self) -> List[int]:
        """Sorted list of all unique destination zone IDs."""
        self._ensure_loaded()
        return self._all_dest_ids

    @property
    def global_mean_travel_time(self) -> float:
        """Dataset-wide average travel time in seconds."""
        self._ensure_loaded()
        return self._global_mean

    @property
    def is_loaded(self) -> bool:
        """Whether data has been loaded (may still be empty if file missing)."""
        return self._loaded

    # ── IST-aware helpers ─────────────────────────────────────────────────────

    @staticmethod
    def is_indian_holiday(dt: Optional[datetime] = None) -> bool:
        """Check if the given datetime falls on an Indian public holiday.

        Args:
            dt: Datetime to check. Defaults to current IST time.
        """
        if dt is None:
            dt = datetime.now(IST)
        return (dt.month, dt.day) in INDIAN_PUBLIC_HOLIDAYS

    @staticmethod
    def get_chennai_period(hour: Optional[int] = None) -> str:
        """Classify the current period for Chennai traffic patterns.

        Args:
            hour: IST hour (0-23). Defaults to current IST hour.

        Returns:
            One of: ``"morning_rush"``, ``"evening_rush"``,
            ``"lunch_peak"``, ``"late_night"``, ``"normal"``.
        """
        if hour is None:
            hour = datetime.now(IST).hour

        if hour in CHENNAI_MORNING_RUSH:
            return "morning_rush"
        elif hour in CHENNAI_EVENING_RUSH:
            return "evening_rush"
        elif hour in CHENNAI_LUNCH_PEAK:
            return "lunch_peak"
        elif hour in CHENNAI_LATE_NIGHT:
            return "late_night"
        return "normal"

    @staticmethod
    def get_rush_hour_factor(hour: Optional[int] = None) -> float:
        """Get a multiplier reflecting Chennai rush-hour severity.

        Values > 1.0 indicate slower-than-normal conditions.

        Args:
            hour: IST hour (0-23). Defaults to current IST hour.

        Returns:
            Multiplier in range [0.7, 1.6].
        """
        if hour is None:
            hour = datetime.now(IST).hour

        period = HistoricalETAStore.get_chennai_period(hour)
        factors = {
            "morning_rush": 1.45,
            "evening_rush": 1.55,
            "lunch_peak": 1.15,
            "late_night": 0.70,
            "normal": 1.00,
        }
        return factors.get(period, 1.0)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        """Trigger lazy loading if data hasn't been loaded yet."""
        if not self._loaded:
            self.load()


# ── Module-level singleton ────────────────────────────────────────────────────

_store_instance: Optional[HistoricalETAStore] = None
_store_lock = threading.Lock()


def get_store() -> HistoricalETAStore:
    """Return the global singleton ``HistoricalETAStore`` instance.

    Thread-safe. The underlying CSV data is loaded lazily on first access.

    Returns:
        The singleton ``HistoricalETAStore``.
    """
    global _store_instance
    if _store_instance is None:
        with _store_lock:
            if _store_instance is None:
                _store_instance = HistoricalETAStore()
    return _store_instance
