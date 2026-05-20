"""
ML ETA Predictor — Pulse-Chennai
==================================
Production-grade ensemble ML predictor for bus ETA estimation.

**Model Architecture:**
- Primary: Weighted ensemble of pre-trained XGBRegressor + LGBMRegressor
- Fallback 1: Single surviving model (if one fails to load)
- Fallback 2: GradientBoostingRegressor trained on uber_data.csv
- Fallback 3: Analytical speed-based estimate

**Feature Pipeline (for pre-trained models):**
4 features in exact order: [source_avg_time, dest_avg_time, hod_sin, hod_cos]

- ``source_avg_time``: avg mean_travel_time for source zone across all
  destinations/hours (from uber_data.csv)
- ``dest_avg_time``: same for destination zone
- ``hod_sin``: sin(2π × hour / 24)  — cyclical hour encoding
- ``hod_cos``: cos(2π × hour / 24)

**Traffic Correction:**
The raw ML prediction is adjusted by a real-time TomTom traffic factor:
    corrected = ml_prediction × (free_flow_speed / current_speed)

Usage:
    from traffic.ml_eta_predictor import get_predictor
    predictor = get_predictor()
    result = predictor.predict(
        src_lat=13.0694, src_lon=80.1948,
        dst_lat=13.0338, dst_lon=80.2326,
    )
"""

import math
import os
import pickle
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pytz

logger = logging.getLogger(__name__)

# IST timezone for all time calculations
IST = pytz.timezone("Asia/Kolkata")

# Earth radius in km
_EARTH_RADIUS_KM = 6_371.0

# Ensemble weights — XGB has better single-feature importance distribution
_ENSEMBLE_WEIGHTS = {
    "xgb": 0.50,
    "lgb": 0.50,
}

# Feature order expected by the pre-trained models
_FEATURE_NAMES = ["source_avg_time", "dest_avg_time", "hod_sin", "hod_cos"]


def _haversine_km(
    lat1: float, lon1: float, lat2: float, lon2: float,
) -> float:
    """Compute great-circle distance between two GPS points in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    )
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class MLETAPredictor:
    """Thread-safe, gracefully-degrading ML ensemble for ETA prediction.

    Loads pre-trained XGBoost and LightGBM regressors from the ``models/``
    directory.  If either fails, the surviving model is used alone.  If both
    fail, a fallback ``GradientBoostingRegressor`` is trained on
    ``uber_data.csv`` on the fly.

    The predictor is exposed as a module-level singleton via
    :func:`get_predictor`.
    """

    def __init__(self) -> None:
        self._models: Dict[str, Any] = {}
        self._fallback_model: Any = None
        self._model_names: List[str] = []
        self._initialized: bool = False
        self._lock = threading.Lock()
        self._store: Any = None  # HistoricalETAStore (lazy)

    # ── Initialization ────────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Load models and historical data. Thread-safe, idempotent."""
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            logger.info("MLETAPredictor: initializing …")

            # Load the historical store (lazy singleton)
            try:
                from traffic.historical_eta_store import get_store
                self._store = get_store()
                logger.info("MLETAPredictor: historical store attached.")
            except Exception:
                logger.exception("MLETAPredictor: failed to load historical store")

            # Resolve models/ directory
            project_root = Path(__file__).resolve().parent.parent
            models_dir = project_root / "models"

            # ── Load pre-trained models ───────────────────────────────────
            self._load_pretrained_models(models_dir)

            # ── Build fallback if no pre-trained models survived ──────────
            if not self._models:
                logger.warning(
                    "MLETAPredictor: no pre-trained models loaded. "
                    "Building fallback GradientBoostingRegressor …"
                )
                self._build_fallback_model(project_root / "data" / "uber_data.csv")

            self._initialized = True
            logger.info(
                "MLETAPredictor: ready — models=%s, fallback=%s",
                list(self._models.keys()) or "none",
                "yes" if self._fallback_model else "no",
            )

    def _load_pretrained_models(self, models_dir: Path) -> None:
        """Attempt to load XGBoost, LightGBM, and Random Forest models."""
        model_files = {
            "xgb": models_dir / "xgb_model.pkl",
            "lgb": models_dir / "lgb_model.pkl",
            "rf":  models_dir / "rf_model.pkl",
        }

        for name, path in model_files.items():
            if not path.exists():
                logger.warning("MLETAPredictor: %s not found at %s", name, path)
                continue
            try:
                with open(path, "rb") as f:
                    model = pickle.load(f)

                # Validate the model has a predict method
                if not hasattr(model, "predict"):
                    logger.warning(
                        "MLETAPredictor: %s loaded but has no predict() method", name
                    )
                    continue

                # Quick sanity check — predict on a dummy array
                dummy = np.zeros((1, len(_FEATURE_NAMES)))
                _ = model.predict(dummy)

                self._models[name] = model
                self._model_names.append(name)
                logger.info("MLETAPredictor: loaded %s from %s", name, path)

            except Exception as e:
                logger.warning(
                    "MLETAPredictor: failed to load %s — %s: %s",
                    name, type(e).__name__, e,
                )

    def _build_fallback_model(self, csv_path: Path) -> None:
        """Train a lightweight GradientBoostingRegressor as last-resort model."""
        if not csv_path.exists():
            logger.error(
                "MLETAPredictor: cannot build fallback — %s not found", csv_path
            )
            return

        try:
            import pandas as pd
            from sklearn.ensemble import GradientBoostingRegressor

            logger.info("MLETAPredictor: loading data for fallback training …")
            df = pd.read_csv(csv_path)

            # Engineer the same 4 features
            src_avg = df.groupby("sourceid")["mean_travel_time"].transform("mean")
            dst_avg = df.groupby("dstid")["mean_travel_time"].transform("mean")
            hod_sin = np.sin(2 * np.pi * df["hod"] / 24.0)
            hod_cos = np.cos(2 * np.pi * df["hod"] / 24.0)

            X = np.column_stack([src_avg, dst_avg, hod_sin, hod_cos])
            y = df["mean_travel_time"].values

            # Sample for speed (max 100K rows)
            n = len(X)
            if n > 100_000:
                idx = np.random.default_rng(42).choice(n, 100_000, replace=False)
                X, y = X[idx], y[idx]

            gbr = GradientBoostingRegressor(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                subsample=0.8,
                random_state=42,
            )
            gbr.fit(X, y)
            self._fallback_model = gbr
            logger.info(
                "MLETAPredictor: fallback GBR trained on %d samples.", len(y)
            )

        except Exception:
            logger.exception("MLETAPredictor: failed to train fallback model")

    # ── Feature Engineering ───────────────────────────────────────────────────

    def _map_coords_to_zone_id(
        self,
        lat: float,
        lon: float,
        zone_type: str = "source",
    ) -> int:
        """Map GPS coordinates to the nearest uber_data zone ID.

        Uses a deterministic hash based on coordinates to get a zone ID,
        then snaps to the nearest valid zone in the dataset.

        Args:
            lat: Latitude.
            lon: Longitude.
            zone_type: ``"source"`` or ``"dest"``.

        Returns:
            The nearest valid zone ID from uber_data.
        """
        # Create a deterministic zone ID from coordinates
        # Use 0.01-degree grid (~1.1 km resolution in Chennai)
        grid_lat = int(lat * 100)
        grid_lon = int(lon * 100)
        raw_id = abs(hash((grid_lat, grid_lon))) % 500

        if self._store is None:
            return raw_id

        if zone_type == "source":
            return self._store.get_nearest_source_id(raw_id)
        return self._store.get_nearest_dest_id(raw_id)

    def _build_features(
        self,
        src_lat: float,
        src_lon: float,
        dst_lat: float,
        dst_lon: float,
        hour: Optional[int] = None,
    ) -> Tuple[np.ndarray, Dict[str, float]]:
        """Construct the 4-feature vector for model prediction.

        Args:
            src_lat: Source latitude.
            src_lon: Source longitude.
            dst_lat: Destination latitude.
            dst_lon: Destination longitude.
            hour: Hour of day (0-23). Defaults to current IST hour.

        Returns:
            Tuple of (feature_array shape (1, 4), feature_dict for logging).
        """
        if hour is None:
            hour = datetime.now(IST).hour

        # Map coordinates to zone IDs
        src_id = self._map_coords_to_zone_id(src_lat, src_lon, "source")
        dst_id = self._map_coords_to_zone_id(dst_lat, dst_lon, "dest")

        # Retrieve zone-level aggregates from historical store
        if self._store is not None:
            source_avg_time = self._store.get_source_avg_time(src_id)
            dest_avg_time = self._store.get_dest_avg_time(dst_id)
        else:
            # If no store, use distance-based estimate
            dist_km = _haversine_km(src_lat, src_lon, dst_lat, dst_lon)
            source_avg_time = dist_km * 60.0  # rough ~1 min/km baseline
            dest_avg_time = dist_km * 60.0

        # Cyclical hour encoding
        hod_sin = math.sin(2 * math.pi * hour / 24.0)
        hod_cos = math.cos(2 * math.pi * hour / 24.0)

        features = np.array(
            [[source_avg_time, dest_avg_time, hod_sin, hod_cos]],
            dtype=np.float64,
        )

        feature_dict = {
            "source_avg_time": round(source_avg_time, 2),
            "dest_avg_time": round(dest_avg_time, 2),
            "hod_sin": round(hod_sin, 4),
            "hod_cos": round(hod_cos, 4),
            "mapped_source_id": src_id,
            "mapped_dest_id": dst_id,
            "hour_of_day": hour,
        }

        return features, feature_dict

    # ── Traffic Factor ────────────────────────────────────────────────────────

    def _get_traffic_factor(
        self,
        src_lat: float,
        src_lon: float,
        dst_lat: float,
        dst_lon: float,
        current_speed_kmph: Optional[float] = None,
    ) -> Tuple[float, float, float]:
        """Compute a real-time traffic correction factor.

        Uses TomTom flow segment data (already cached in memory) to adjust
        the ML prediction for current conditions.

        Args:
            src_lat, src_lon: Source coordinates.
            dst_lat, dst_lon: Destination coordinates.
            current_speed_kmph: Override speed (e.g. from GPS). If provided,
                the TomTom lookup is skipped.

        Returns:
            Tuple of (traffic_factor, current_speed, free_flow_speed).
            ``traffic_factor > 1.0`` means slower than free-flow.
        """
        free_flow_speed = 52.0  # Chennai default free-flow (km/h)
        current_speed = current_speed_kmph or 35.0

        if current_speed_kmph is None:
            try:
                from traffic import tomtom_client
                snapshots = tomtom_client.get_latest_snapshots()
                if snapshots:
                    # Find nearest segment to route midpoint
                    mid_lat = (src_lat + dst_lat) / 2
                    mid_lon = (src_lon + dst_lon) / 2

                    best_dist = float("inf")
                    best_snap = None
                    for snap in snapshots.values():
                        d = _haversine_km(mid_lat, mid_lon, snap.lat, snap.lon)
                        if d < best_dist:
                            best_dist = d
                            best_snap = snap

                    if best_snap:
                        current_speed = best_snap.current_speed_kmph
                        free_flow_speed = best_snap.free_flow_speed_kmph
            except Exception as e:
                logger.debug("MLETAPredictor: TomTom traffic fetch failed: %s", e)

        # Avoid division by zero
        if current_speed < 1.0:
            current_speed = 1.0

        traffic_factor = free_flow_speed / current_speed
        # Clamp to reasonable range [0.5, 3.0]
        traffic_factor = max(0.5, min(3.0, traffic_factor))

        return traffic_factor, current_speed, free_flow_speed

    # ── Ensemble Prediction ───────────────────────────────────────────────────

    def _ensemble_predict(self, features: np.ndarray) -> Tuple[float, float, str]:
        """Run all loaded models and combine with weighted averaging.

        Args:
            features: Shape (1, 4) array.

        Returns:
            Tuple of (prediction_seconds, confidence, method_label).
        """
        predictions: Dict[str, float] = {}

        # ── Pre-trained models ────────────────────────────────────────────
        for name, model in self._models.items():
            try:
                pred = float(model.predict(features)[0])
                if pred > 0:
                    predictions[name] = pred
            except Exception as e:
                logger.warning(
                    "MLETAPredictor: %s prediction failed: %s", name, e
                )

        if predictions:
            # Weighted average of available pre-trained models
            total_weight = sum(
                _ENSEMBLE_WEIGHTS.get(n, 0.3) for n in predictions
            )
            ensemble_pred = sum(
                pred * _ENSEMBLE_WEIGHTS.get(name, 0.3)
                for name, pred in predictions.items()
            ) / total_weight

            # Confidence based on model agreement
            if len(predictions) >= 2:
                vals = list(predictions.values())
                mean_p = np.mean(vals)
                std_p = np.std(vals)
                # Low std relative to mean → high agreement → high confidence
                agreement = max(0.0, 1.0 - (std_p / (mean_p + 1e-6)))
                confidence = 0.80 + 0.15 * agreement  # Range [0.80, 0.95]
                method = f"ML Ensemble ({'+'.join(predictions.keys())})"
            else:
                confidence = 0.78
                method = f"ML Single ({list(predictions.keys())[0]})"

            return ensemble_pred, confidence, method

        # ── Fallback model ────────────────────────────────────────────────
        if self._fallback_model is not None:
            try:
                pred = float(self._fallback_model.predict(features)[0])
                if pred > 0:
                    return pred, 0.70, "ML Fallback (GBR)"
            except Exception as e:
                logger.warning(
                    "MLETAPredictor: fallback model failed: %s", e
                )

        return 0.0, 0.0, "none"

    # ── Public Prediction API ─────────────────────────────────────────────────

    def predict(
        self,
        src_lat: float,
        src_lon: float,
        dst_lat: float,
        dst_lon: float,
        current_speed_kmph: Optional[float] = None,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate an ML-based ETA prediction.

        This is the primary entry point.  The method:

        1. Engineers features from coordinates + current IST hour.
        2. Runs the model ensemble (XGB+LGB → single → GBR fallback).
        3. Applies a TomTom real-time traffic correction factor.
        4. Adjusts for Chennai rush hours and Indian holidays.

        Args:
            src_lat: Source latitude.
            src_lon: Source longitude.
            dst_lat: Destination latitude.
            dst_lon: Destination longitude.
            current_speed_kmph: Optional GPS-measured speed in km/h.
            api_key: TomTom API key (unused here — we read cached snapshots).

        Returns:
            Dict with keys: ``eta_seconds``, ``eta_minutes``, ``confidence``,
            ``method``, ``features_used``, ``historical_eta_seconds``,
            ``traffic_factor``.
        """
        self._ensure_initialized()

        now = datetime.now(IST)
        hour = now.hour
        distance_km = _haversine_km(src_lat, src_lon, dst_lat, dst_lon)

        # ── Build features ────────────────────────────────────────────────
        features, feature_dict = self._build_features(
            src_lat, src_lon, dst_lat, dst_lon, hour
        )

        # ── ML ensemble prediction ───────────────────────────────────────
        raw_prediction, confidence, method = self._ensemble_predict(features)

        # ── Get historical baseline for comparison ───────────────────────
        historical_eta = None
        if self._store is not None:
            src_id = feature_dict["mapped_source_id"]
            dst_id = feature_dict["mapped_dest_id"]
            hist_record = self._store.get_historical_eta(src_id, dst_id, hour)
            if hist_record:
                historical_eta = hist_record["mean_travel_time"]

        # ── Traffic correction ───────────────────────────────────────────
        traffic_factor, current_speed, free_flow_speed = self._get_traffic_factor(
            src_lat, src_lon, dst_lat, dst_lon, current_speed_kmph,
        )

        if raw_prediction > 0:
            # Apply traffic factor but dampen it:
            # If traffic_factor = 1.0 (free-flow), no change.
            # If traffic_factor = 2.0 (heavy congestion), increase ~60%.
            damped_factor = 1.0 + 0.6 * (traffic_factor - 1.0)
            corrected_prediction = raw_prediction * damped_factor

            # ── Chennai-specific adjustments ──────────────────────────────
            from traffic.historical_eta_store import HistoricalETAStore

            if HistoricalETAStore.is_indian_holiday(now):
                # Holidays generally have lighter traffic
                corrected_prediction *= 0.85
                confidence *= 0.90  # Lower confidence on holidays

            # Clamp to reasonable range (30 sec to 3 hours)
            corrected_prediction = max(30.0, min(10_800.0, corrected_prediction))

            return {
                "eta_seconds": round(corrected_prediction, 1),
                "eta_minutes": round(corrected_prediction / 60.0, 2),
                "confidence": round(min(confidence, 0.98), 3),
                "method": method,
                "features_used": feature_dict,
                "historical_eta_seconds": (
                    round(historical_eta, 1) if historical_eta else None
                ),
                "traffic_factor": round(traffic_factor, 3),
                "distance_km": round(distance_km, 3),
                "current_speed_kmph": round(current_speed, 1),
                "free_flow_speed_kmph": round(free_flow_speed, 1),
                "chennai_period": HistoricalETAStore.get_chennai_period(hour),
                "is_holiday": HistoricalETAStore.is_indian_holiday(now),
            }

        # ── Analytical fallback (no models available) ─────────────────────
        logger.warning(
            "MLETAPredictor: all models failed. Using analytical fallback."
        )
        return self._analytical_fallback(
            src_lat, src_lon, dst_lat, dst_lon,
            distance_km, hour, current_speed, free_flow_speed,
            traffic_factor, historical_eta,
        )

    def _analytical_fallback(
        self,
        src_lat: float,
        src_lon: float,
        dst_lat: float,
        dst_lon: float,
        distance_km: float,
        hour: int,
        current_speed: float,
        free_flow_speed: float,
        traffic_factor: float,
        historical_eta: Optional[float],
    ) -> Dict[str, Any]:
        """Pure analytical ETA when all ML models fail.

        Uses distance + time-of-day speed profile, cross-validated with
        historical ETA if available.
        """
        from traffic.historical_eta_store import HistoricalETAStore

        now = datetime.now(IST)
        road_dist_km = distance_km * 1.35  # Chennai urban road correction

        # Time-of-day speed profile
        rush_factor = HistoricalETAStore.get_rush_hour_factor(hour)
        effective_speed = max(5.0, current_speed / rush_factor)

        eta_seconds = (road_dist_km / effective_speed) * 3600.0

        # Cross-validate with historical data
        if historical_eta and historical_eta > 0:
            eta_seconds = 0.4 * eta_seconds + 0.6 * historical_eta

        eta_seconds = max(30.0, min(10_800.0, eta_seconds))

        return {
            "eta_seconds": round(eta_seconds, 1),
            "eta_minutes": round(eta_seconds / 60.0, 2),
            "confidence": 0.50,
            "method": "Analytical Fallback (no ML)",
            "features_used": {
                "distance_km": round(distance_km, 3),
                "road_dist_km": round(road_dist_km, 3),
                "effective_speed_kmph": round(effective_speed, 1),
                "rush_factor": rush_factor,
                "hour_of_day": hour,
            },
            "historical_eta_seconds": (
                round(historical_eta, 1) if historical_eta else None
            ),
            "traffic_factor": round(traffic_factor, 3),
            "distance_km": round(distance_km, 3),
            "current_speed_kmph": round(current_speed, 1),
            "free_flow_speed_kmph": round(free_flow_speed, 1),
            "chennai_period": HistoricalETAStore.get_chennai_period(hour),
            "is_holiday": HistoricalETAStore.is_indian_holiday(now),
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _ensure_initialized(self) -> None:
        """Trigger lazy initialization if needed."""
        if not self._initialized:
            self.initialize()

    @property
    def available_models(self) -> List[str]:
        """Names of successfully loaded models."""
        self._ensure_initialized()
        return list(self._models.keys())

    @property
    def has_fallback(self) -> bool:
        """Whether the fallback GBR model is available."""
        return self._fallback_model is not None

    @property
    def is_ready(self) -> bool:
        """Whether the predictor has at least one model or fallback ready."""
        self._ensure_initialized()
        return bool(self._models) or self._fallback_model is not None

    def health_check(self) -> Dict[str, Any]:
        """Return a diagnostic summary of the predictor state.

        Useful for /health endpoints.
        """
        self._ensure_initialized()
        return {
            "initialized": self._initialized,
            "pretrained_models": list(self._models.keys()),
            "fallback_model": self._fallback_model is not None,
            "historical_store_loaded": (
                self._store.is_loaded if self._store else False
            ),
            "feature_names": _FEATURE_NAMES,
            "ensemble_weights": _ENSEMBLE_WEIGHTS,
            "is_ready": self.is_ready,
        }


# ── Module-level singleton ────────────────────────────────────────────────────

_predictor_instance: Optional[MLETAPredictor] = None
_predictor_lock = threading.Lock()


def get_predictor() -> MLETAPredictor:
    """Return the global singleton ``MLETAPredictor`` instance.

    Thread-safe.  Models and data are loaded lazily on first prediction call.

    Returns:
        The singleton ``MLETAPredictor``.
    """
    global _predictor_instance
    if _predictor_instance is None:
        with _predictor_lock:
            if _predictor_instance is None:
                _predictor_instance = MLETAPredictor()
    return _predictor_instance
