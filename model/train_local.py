import os
import sys
import logging
import torch
from torch.utils.data import DataLoader, random_split

# Add pulse_chennai to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Add parent of pulse_chennai to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import settings
from graph.graph_builder import DynamicGraphBuilder
from model.spatial_gnn import SpatialGNN
from model.losses import MultiTaskLoss
from model.dataset import SpatialGraphDataset
from model.train import train_one_epoch, validate

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def train_local_model():
    data_dir = "data/parquet"
    output_dir = "models"
    os.makedirs(output_dir, exist_ok=True)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Starting local training on {device}")

    # Build components
    graph_builder = DynamicGraphBuilder(
        h3_feature_dim=settings.gnn.H3_FEATURE_DIM,
        bus_feature_dim=settings.gnn.BUS_FEATURE_DIM,
        temporal_dim=settings.gnn.TEMPORAL_DIM,
        k_ring_radius=2,
    )

    # Load local Parquet files
    parquet_files = [os.path.join(dp, f) for dp, dn, filenames in os.walk(data_dir) for f in filenames if f.endswith('.parquet')]
    
    if not parquet_files:
        logger.error(f"No parquet files found in {data_dir}. Run generate_sample_data.py first.")
        return

    logger.info(f"Found {len(parquet_files)} parquet files. Building dataset...")

    dataset = SpatialGraphDataset(
        parquet_paths=parquet_files,
        h3_resolution=9,
        sequence_len=5,
        k_ring_radius=2,
        num_negatives=5,
        graph_builder=graph_builder,
        use_s3=False
    )
    
    dataset = torch.utils.data.Subset(dataset, range(min(100, len(dataset))))
    h3_index_map = dataset.dataset.get_h3_cell_index()

    val_size = int(len(dataset) * 0.1)
    train_size = len(dataset) - val_size
    train_ds, val_ds = random_split(dataset, [train_size, val_size])

    train_loader = DataLoader(
        train_ds, batch_size=32, shuffle=True,
        collate_fn=SpatialGraphDataset.collate
    )
    val_loader = DataLoader(
        val_ds, batch_size=32,
        collate_fn=SpatialGraphDataset.collate
    )

    # Initialize model
    model = SpatialGNN(
        h3_feature_dim=settings.gnn.H3_FEATURE_DIM,
        bus_feature_dim=settings.gnn.BUS_FEATURE_DIM,
        hidden_dim=128,
        num_heads=4,
        num_layers=3,
        lstm_hidden=settings.gnn.LSTM_HIDDEN,
        dropout=settings.gnn.DROPOUT,
    ).to(device)

    loss_fn = MultiTaskLoss(learnable=True).to(device)
    optimizer = torch.optim.AdamW(
        list(model.parameters()) + list(loss_fn.parameters()),
        lr=1e-3, weight_decay=1e-5,
    )

    # Train for 5 epochs (fast demo training)
    epochs = 5
    best_val_loss = float("inf")
    
    for epoch in range(1, epochs + 1):
        train_loss = train_one_epoch(model, train_loader, optimizer, loss_fn, device, h3_index_map)
        val_loss = validate(model, val_loader, loss_fn, device, h3_index_map)

        logger.info(
            f"Epoch {epoch:03d}/{epochs} | "
            f"Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f}"
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            path = os.path.join(output_dir, "pulse_gnn_best.pt")
            torch.save(model.state_dict(), path)
            logger.info(f"  ✓ New best model saved → {path}")

    logger.info(f"Local training complete. Best val loss: {best_val_loss:.4f}")

if __name__ == "__main__":
    train_local_model()
