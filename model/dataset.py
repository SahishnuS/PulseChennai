"""
SpatialGraphDataset — PyTorch Dataset for Training PulseGNN
=============================================================
Backs the model training pipeline by loading H3-indexed Parquet
files from S3 (or local disk), transforming GPS trajectory windows
into PyG HeteroData graphs, and generating BPR training triples.

Dataset Schema (Parquet columns):
    trip_id          : str  — unique bus journey ID
    timestamp_ms     : int64 — Unix ms
    lat, lng         : float64
    speed_kmh        : float — can be null
    heading_deg      : float — can be null
    passenger_count  : int   — can be null
    h3_l9            : str   — precomputed or filled here
    h3_l8            : str   — partition column

Usage:
    dataset = SpatialGraphDataset(
        parquet_paths=["s3://pulse-chennai-datalake/h3_l8=8870.../*.parquet"],
        h3_resolution=9,
        sequence_len=5,
        k_ring_radius=2,
    )
    loader = DataLoader(dataset, batch_size=32, collate_fn=dataset.collate)
"""

import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from torch.utils.data import Dataset

logger = logging.getLogger(__name__)


class SpatialGraphDataset(Dataset):
    """
    PyTorch Dataset that loads H3-indexed bus trajectory data from
    Parquet files and constructs graph training samples.

    Each sample = one (trip_id, time_window) pair, producing:
        - A heterogeneous graph (HeteroData) of H3 cells + bus nodes
        - The TRUE next H3 cell the bus moved into (positive label)
        - K NEGATIVE H3 cells sampled from the same k-ring (BPR negatives)
        - Ground-truth ETA in seconds to the next stop
    """

    def __init__(
        self,
        parquet_paths: list[str],
        h3_resolution: int = 9,
        sequence_len: int = 5,       # How many past pings to use as GNN input
        k_ring_radius: int = 2,
        num_negatives: int = 5,      # Number of BPR negative cells per sample
        graph_builder=None,           # DynamicGraphBuilder (injected)
        use_s3: bool = False,
        s3_bucket: Optional[str] = None,
        transform=None,
    ):
        self.h3_resolution = h3_resolution
        self.sequence_len = sequence_len
        self.k_ring_radius = k_ring_radius
        self.num_negatives = num_negatives
        self.graph_builder = graph_builder
        self.transform = transform

        # Load all parquet files into memory (or streaming for large scale)
        self._samples = []   # List of (trip_id, window of pings)
        self._all_h3_cells: set[str] = set()
        self._load_parquet_files(parquet_paths, use_s3, s3_bucket)

        logger.info(
            f"SpatialGraphDataset loaded: {len(self._samples)} samples, "
            f"{len(self._all_h3_cells)} unique H3 cells"
        )

    # ──────────────────────────────────────────────────────
    # Data Loading
    # ──────────────────────────────────────────────────────

    def _load_parquet_files(self, paths, use_s3, s3_bucket):
        """
        Load and preprocess Parquet files.
        Handles both local paths and S3 URIs.
        """
        import pyarrow.parquet as pq
        from pulse_chennai.graph.h3_utils import latlng_to_h3

        all_rows = []

        for path in paths:
            try:
                if use_s3 and path.startswith("s3://"):
                    import boto3
                    import io
                    s3 = boto3.client("s3")
                    bucket, key = path.replace("s3://", "").split("/", 1)
                    obj = s3.get_object(Bucket=bucket, Key=key)
                    table = pq.read_table(io.BytesIO(obj["Body"].read()))
                else:
                    table = pq.read_table(path)

                df = table.to_pandas()
                df = self._validate_and_clean(df, latlng_to_h3)
                all_rows.append(df)
                logger.debug(f"Loaded {len(df)} rows from {path}")
            except Exception as e:
                logger.warning(f"Failed to load {path}: {e}")
                continue

        if not all_rows:
            raise RuntimeError("No valid Parquet files loaded.")

        import pandas as pd
        full_df = pd.concat(all_rows, ignore_index=True)
        full_df = full_df.sort_values(["trip_id", "timestamp_ms"])

        self._build_samples(full_df)

    def _validate_and_clean(self, df, latlng_to_h3_fn):
        """
        Validate schema, fill H3 index if missing,
        and filter rows outside Chennai bounds.
        """
        # Chennai bounding box: lat [12.7, 13.3], lng [79.9, 80.5]
        df = df[
            df["lat"].between(12.7, 13.3) &
            df["lng"].between(79.9, 80.5)
        ].copy()

        # Fill H3 if not precomputed
        if "h3_l9" not in df.columns:
            df["h3_l9"] = df.apply(
                lambda r: latlng_to_h3_fn(r["lat"], r["lng"], self.h3_resolution),
                axis=1,
            )

        # Fill optional columns
        df["speed_kmh"] = df.get("speed_kmh", 0).fillna(0).clip(0, 120)
        df["heading_deg"] = df.get("heading_deg", 0).fillna(0)
        df["passenger_count"] = df.get("passenger_count", 0).fillna(0).astype(int)

        # Track all H3 cells seen for negative sampling
        self._all_h3_cells.update(df["h3_l9"].unique())

        return df

    def _build_samples(self, df):
        """
        Slide a window of `sequence_len` pings over each trip's trajectory.
        Each window becomes one training sample with a positive label (true next H3).
        """
        for trip_id, trip_df in df.groupby("trip_id"):
            pings = trip_df.to_dict("records")

            # Need at least sequence_len + 1 rows to have a prediction target
            if len(pings) < self.sequence_len + 1:
                continue

            for i in range(len(pings) - self.sequence_len):
                window = pings[i : i + self.sequence_len]
                target_ping = pings[i + self.sequence_len]

                self._samples.append({
                    "trip_id": trip_id,
                    "window": window,                    # Past pings (input sequence)
                    "true_h3": target_ping["h3_l9"],    # Ground truth next cell
                    "true_eta": self._compute_eta(window, target_ping),
                })

    def _compute_eta(self, window, target_ping) -> float:
        """ETA in seconds from last known ping to the target ping's timestamp."""
        last_ts = window[-1]["timestamp_ms"]
        target_ts = target_ping["timestamp_ms"]
        return max(0.0, (target_ts - last_ts) / 1000.0)

    # ──────────────────────────────────────────────────────
    # Dataset Protocol
    # ──────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._samples)

    def __getitem__(self, idx: int) -> dict:
        """
        Returns one training sample:
            data       : HeteroData graph
            true_h3    : str — the ground-truth next H3 cell
            neg_h3s    : list[str] — BPR negative cells (same k-ring, not true)
            eta_seconds: float — ground-truth ETA
        """
        sample = self._samples[idx]
        trip_id = sample["trip_id"]
        window = sample["window"]
        true_h3 = sample["true_h3"]
        eta_seconds = sample["true_eta"]

        # ── Build the graph from the feature window ──
        # Use the last ping in the window as the "current" position
        last_ping = window[-1]
        center_h3 = last_ping["h3_l9"]
        timestamp = datetime.fromtimestamp(last_ping["timestamp_ms"] / 1000)

        # Build minimal h3_states from the window
        from pulse_chennai.graph.h3_utils import get_k_ring
        k_ring_cells = get_k_ring(center_h3, self.k_ring_radius)

        h3_states = self._window_to_h3_states(window, k_ring_cells)
        bus_state = self._window_to_bus_state(trip_id, window)

        data = self.graph_builder.build_graph(
            center_h3=center_h3,
            h3_node_states=h3_states,
            active_buses=[bus_state],
            timestamp=timestamp,
        )

        # ── Sample BPR negatives ──
        neg_cells = self._sample_negatives(center_h3, true_h3, k_ring_cells)

        item = {
            "data": data,
            "true_h3": true_h3,
            "neg_h3s": neg_cells,
            "eta_seconds": torch.tensor([eta_seconds], dtype=torch.float32),
            "trip_id": trip_id,
        }

        if self.transform:
            item = self.transform(item)

        return item

    # ──────────────────────────────────────────────────────
    # Helper Methods
    # ──────────────────────────────────────────────────────

    def _window_to_h3_states(self, window, cells) -> dict:
        """
        Aggregate the trajectory window into per-cell feature dicts.
        Simulates what the Redis Feature Store would hold at inference time.
        """
        # Compute average speed across the window
        speeds = [p["speed_kmh"] for p in window if p["speed_kmh"] > 0]
        avg_speed = float(np.mean(speeds)) if speeds else 0.0

        # Count bus pings per cell
        cell_hits = {}
        for ping in window:
            h = ping["h3_l9"]
            cell_hits[h] = cell_hits.get(h, 0) + 1

        states = {}
        for cell in cells:
            states[cell] = {
                "bus_count": cell_hits.get(cell, 0),
                "avg_speed": avg_speed,
                "congestion_score": max(0.0, 1.0 - avg_speed / 60.0),
                "passenger_density": float(window[-1]["passenger_count"]) / 100.0,
                "person_ping_count": 0,
                "last_updated": window[-1]["timestamp_ms"] / 1000,
            }
        return states

    def _window_to_bus_state(self, trip_id, window) -> dict:
        """Convert the last ping in the window into a bus state dict."""
        last = window[-1]
        return {
            "trip_id": trip_id,
            "lat": last["lat"],
            "lng": last["lng"],
            "h3_cell": last["h3_l9"],
            "speed": last["speed_kmh"],
            "heading": last["heading_deg"],
            "hw_score": 0.9,
            "passenger_count": int(last["passenger_count"]),
            "status": "active",
            "last_seen": last["timestamp_ms"] / 1000,
        }

    def _sample_negatives(self, center_h3, true_h3, k_ring_cells) -> list[str]:
        """
        Sample BPR negative H3 cells from:
        1. The k-ring neighborhood (hard negatives — nearby but wrong)
        2. The global cell pool (easy negatives — far away)
        """
        k_ring_excl = [c for c in k_ring_cells if c != true_h3]

        # 60% hard negatives (k-ring), 40% easy negatives (global)
        n_hard = max(1, int(self.num_negatives * 0.6))
        n_easy = self.num_negatives - n_hard

        hard_negs = random.sample(k_ring_excl, min(n_hard, len(k_ring_excl)))

        global_pool = list(self._all_h3_cells - {true_h3} - set(k_ring_cells))
        easy_negs = random.sample(global_pool, min(n_easy, len(global_pool)))

        return (hard_negs + easy_negs)[: self.num_negatives]

    @staticmethod
    def collate(batch: list[dict]) -> dict:
        """
        Custom collate for DataLoader.
        Stacks ETAs; data graphs are returned as a list (PyG Batch handles them).
        """
        from torch_geometric.data import Batch

        graphs = [item["data"] for item in batch]
        return {
            "data": Batch.from_data_list(graphs),
            "true_h3": [item["true_h3"] for item in batch],
            "neg_h3s": [item["neg_h3s"] for item in batch],
            "eta_seconds": torch.cat([item["eta_seconds"] for item in batch]),
            "trip_ids": [item["trip_id"] for item in batch],
        }

    def get_h3_cell_index(self) -> dict[str, int]:
        """Returns a mapping from H3 cell string to integer node index."""
        return {cell: i for i, cell in enumerate(sorted(self._all_h3_cells))}
