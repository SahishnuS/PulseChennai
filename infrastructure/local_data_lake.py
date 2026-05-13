import os
import json
import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

class LocalDataLake:
    """
    Filesystem-backed Data Lake for storing historical Parquet data.
    Implements a subset of the DataLakeClient interface without requiring S3.
    """
    def __init__(self, base_dir: str = "data/parquet"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        logger.info(f"LocalDataLake initialized at {self.base_dir}")

    def write_trajectories(self, df: pd.DataFrame, partition_cols: List[str] = ["h3_l8", "date"]) -> bool:
        """
        Write trajectory dataframe to local parquet with hive partitioning.
        """
        try:
            if df.empty:
                return False

            table = pa.Table.from_pandas(df)
            pq.write_to_dataset(
                table,
                root_path=self.base_dir,
                partition_cols=partition_cols,
                compression='snappy'
            )
            logger.info(f"Successfully wrote {len(df)} rows to {self.base_dir}")
            return True
        except Exception as e:
            logger.error(f"Failed to write trajectories: {e}")
            return False

    def read_trajectories(self, h3_l8: Optional[str] = None, date: Optional[str] = None) -> pd.DataFrame:
        """
        Read trajectories, optionally filtered by partition.
        """
        try:
            dataset = pq.ParquetDataset(self.base_dir)
            table = dataset.read()
            df = table.to_pandas()
            
            # Manual filtering if dataset API didn't handle it (for simplicity)
            if h3_l8:
                df = df[df['h3_l8'] == h3_l8]
            if date:
                df = df[df['date'] == date]
                
            return df
        except Exception as e:
            logger.error(f"Failed to read trajectories: {e}")
            return pd.DataFrame()

    def run_nightly_etl(self, feature_store) -> None:
        """
        Compute historical speed patterns from parquet data and push to feature store.
        """
        logger.info("Starting Nightly ETL from LocalDataLake...")
        try:
            df = self.read_trajectories()
            if df.empty:
                logger.warning("No data found for ETL.")
                return

            if 'timestamp_ms' in df.columns:
                df['hour'] = pd.to_datetime(df['timestamp_ms'], unit='ms').dt.hour
                
                # Group by cell and hour to get average speed
                grouped = df.groupby(['h3_l9', 'hour'])['speed_kmh'].mean().reset_index()
                
                # Pivot to create 24-dim vector for each cell
                patterns = {}
                for cell in grouped['h3_l9'].unique():
                    cell_data = grouped[grouped['h3_l9'] == cell]
                    # Fill missing hours with overall average or 0
                    vector = []
                    for h in range(24):
                        match = cell_data[cell_data['hour'] == h]
                        if not match.empty:
                            vector.append(float(match['speed_kmh'].iloc[0]))
                        else:
                            vector.append(20.0)  # Default speed
                    patterns[cell] = vector
                
                # Push to feature store
                count = 0
                for cell, pattern in patterns.items():
                    feature_store.set_pattern_vector(cell, pattern)
                    count += 1
                
                logger.info(f"ETL completed. Updated {count} pattern vectors in FeatureStore.")
            else:
                logger.warning("Required columns missing for ETL.")
        except Exception as e:
            logger.error(f"Nightly ETL failed: {e}")

# Singleton instance for the local pipeline
local_data_lake = LocalDataLake()
