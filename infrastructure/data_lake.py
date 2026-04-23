"""
Data Lake Module (Batch Layer)
================================
S3/GCS Parquet storage for historical trajectory data.
Partitioned by (h3_l8, date) for efficient range queries.
Nightly ETL computes route pattern features and pushes to Redis.
"""

import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime, date
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Parquet Schema Definition
# ──────────────────────────────────────────────────────────

TRAJECTORY_SCHEMA = pa.schema([
    pa.field("bus_id", pa.string(), nullable=False),
    pa.field("trip_id", pa.string(), nullable=False),
    pa.field("lat", pa.float64(), nullable=False),
    pa.field("lon", pa.float64(), nullable=False),
    pa.field("h3_l8", pa.string(), nullable=False),
    pa.field("h3_l9", pa.string(), nullable=False),
    pa.field("timestamp", pa.timestamp("ms", tz="Asia/Kolkata"), nullable=False),
    pa.field("speed", pa.float32()),
    pa.field("heading", pa.float32()),
    pa.field("passenger_count", pa.int32()),
    pa.field("hw_reliability_score", pa.float32()),
    pa.field("source", pa.string()),           # "ais140" | "crowdsourced"
    pa.field("date", pa.date32(), nullable=False),   # Partition column
])


class DataLakeClient:
    """
    Manages reads/writes to the S3-backed Parquet data lake.

    Partitioning strategy:
      - L1: h3_l8 (city-block spatial partition)
      - L2: date  (temporal partition)

    This gives O(1) partition pruning for spatial-temporal queries,
    critical for training the GNN on route-specific historical data.
    """

    def __init__(self, bucket: str, region: str = "ap-south-1",
                 aws_access_key: Optional[str] = None,
                 aws_secret_key: Optional[str] = None):
        self.bucket = bucket
        self.region = region
        self.base_path = f"s3://{bucket}/trajectories"

        # Initialize S3 filesystem
        import pyarrow.fs as fs
        if aws_access_key and aws_secret_key:
            self._fs = fs.S3FileSystem(
                region=region,
                access_key=aws_access_key,
                secret_key=aws_secret_key,
            )
        else:
            # Use default credentials chain (IAM role, env vars, etc.)
            self._fs = fs.S3FileSystem(region=region)

        logger.info(f"DataLake initialized: s3://{bucket} in {region}")

    def write_trajectories(self, records: list[dict]) -> None:
        """
        Write a batch of trajectory records to the data lake.

        Each record is a dict matching TRAJECTORY_SCHEMA fields.
        Records are converted to a PyArrow Table and written as
        partitioned Parquet files.
        """
        if not records:
            return

        # Ensure date partition column exists
        for r in records:
            if "date" not in r and "timestamp" in r:
                ts = r["timestamp"]
                if isinstance(ts, datetime):
                    r["date"] = ts.date()
                elif isinstance(ts, (int, float)):
                    r["date"] = datetime.fromtimestamp(ts / 1000).date()

        table = pa.Table.from_pylist(records, schema=TRAJECTORY_SCHEMA)

        pq.write_to_dataset(
            table,
            root_path=f"{self.bucket}/trajectories",
            partition_cols=["h3_l8", "date"],
            filesystem=self._fs,
            existing_data_behavior="overwrite_or_ignore",
        )
        logger.info(f"Wrote {len(records)} trajectory records to data lake")

    def read_trajectories(
        self,
        h3_cells: list[str],
        date_start: date,
        date_end: date,
        columns: Optional[list[str]] = None,
    ) -> pa.Table:
        """
        Read trajectory data for specific H3 cells and date range.

        Uses partition pruning for efficient reads — only touches
        the Parquet files in matching h3_l8/date partitions.
        """
        import pyarrow.dataset as ds

        dataset = ds.dataset(
            f"{self.bucket}/trajectories",
            filesystem=self._fs,
            format="parquet",
            partitioning=ds.partitioning(
                pa.schema([
                    pa.field("h3_l8", pa.string()),
                    pa.field("date", pa.date32()),
                ]),
                flavor="hive",
            ),
        )

        # Build filter expression for partition pruning
        h3_filter = ds.field("h3_l8").isin(h3_cells)
        date_filter = (ds.field("date") >= date_start) & (
            ds.field("date") <= date_end
        )

        table = dataset.to_table(
            filter=h3_filter & date_filter,
            columns=columns,
        )
        logger.info(
            f"Read {table.num_rows} records for {len(h3_cells)} cells, "
            f"{date_start} to {date_end}"
        )
        return table

    def run_nightly_etl(self, target_date: date) -> dict:
        """
        Nightly batch ETL job:
        1. Read all trajectories for target_date
        2. Compute per-H3-cell aggregate features
        3. Return feature dict for pushing to Redis

        Returns:
            Dict mapping h3_index -> {avg_speed, trip_count,
                                       peak_congestion, pattern_vector}
        """
        import numpy as np

        table = self.read_trajectories(
            h3_cells=[],  # all cells
            date_start=target_date,
            date_end=target_date,
            columns=["h3_l9", "speed", "passenger_count", "timestamp"],
        )

        if table.num_rows == 0:
            logger.warning(f"No data for nightly ETL on {target_date}")
            return {}

        df = table.to_pandas()
        features = {}

        for h3_cell, group in df.groupby("h3_l9"):
            hour_groups = group.groupby(group["timestamp"].dt.hour)

            # 24-dim pattern vector: average speed per hour
            pattern = np.zeros(24, dtype=np.float32)
            for hour, hg in hour_groups:
                pattern[hour] = hg["speed"].mean()

            features[h3_cell] = {
                "avg_speed": float(group["speed"].mean()),
                "trip_count": int(group["speed"].count()),
                "peak_congestion": float(group["passenger_count"].max()),
                "pattern_vector": pattern.tolist(),
            }

        logger.info(
            f"Nightly ETL computed features for {len(features)} cells "
            f"on {target_date}"
        )
        return features
