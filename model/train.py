"""
PulseGNN Training Script
=========================
Trains the SpatialGNN model on historical S3 Parquet data.

Usage:
    python -m pulse_chennai.model.train \
        --data_dir ./data/parquet \
        --epochs 50 \
        --batch_size 32 \
        --output_dir ./models

For GPU training, ensure CUDA is available:
    python -m pulse_chennai.model.train --device cuda
"""

import argparse
import logging
import os
from pathlib import Path

import torch
from torch.utils.data import DataLoader, random_split

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Train PulseGNN")
    parser.add_argument("--data_dir", type=str, required=True, help="Directory with Parquet files")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--hidden_dim", type=int, default=256)
    parser.add_argument("--num_heads", type=int, default=4)
    parser.add_argument("--num_layers", type=int, default=3)
    parser.add_argument("--device", type=str, default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--output_dir", type=str, default="./models")
    parser.add_argument("--val_split", type=float, default=0.1)
    parser.add_argument("--checkpoint_every", type=int, default=5)
    parser.add_argument("--sequence_len", type=int, default=5)
    return parser.parse_args()


def build_dataset(data_dir: str, sequence_len: int, graph_builder):
    """Load all parquet files from a directory into SpatialGraphDataset."""
    from pulse_chennai.model.dataset import SpatialGraphDataset

    parquet_files = list(Path(data_dir).rglob("*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(f"No .parquet files found in {data_dir}")

    logger.info(f"Found {len(parquet_files)} Parquet files")

    return SpatialGraphDataset(
        parquet_paths=[str(f) for f in parquet_files],
        h3_resolution=9,
        sequence_len=sequence_len,
        k_ring_radius=2,
        num_negatives=5,
        graph_builder=graph_builder,
    )


def train_one_epoch(model, loader, optimizer, loss_fn, device, h3_index_map):
    model.train()
    total_loss = 0.0

    for batch in loader:
        data = batch["data"].to(device)
        true_h3_list = batch["true_h3"]        # list of str
        neg_h3s_list = batch["neg_h3s"]         # list of list[str]
        true_eta = batch["eta_seconds"].to(device)

        optimizer.zero_grad()
        output = model(data)

        h3_scores = output["h3_scores"]         # (num_h3_nodes_in_batch,)
        pred_eta = output["eta_seconds"]         # (num_buses_in_batch,)

        # Map true/neg H3 strings to node indices
        num_scores = h3_scores.size(0)
        pos_indices = torch.tensor(
            [min(h3_index_map.get(h, 0), max(0, num_scores - 1)) for h in true_h3_list],
            dtype=torch.long, device=device
        )
        neg_scores = torch.stack([
            torch.tensor(
                [h3_scores[min(h3_index_map.get(n, 0), max(0, num_scores - 1))].item() for n in negs],
                device=device
            )
            for negs in neg_h3s_list
        ]).mean(dim=1)

        result = loss_fn(
            h3_scores=h3_scores,
            positive_h3_idx=pos_indices,
            negative_h3_scores=neg_scores,
            predicted_eta=pred_eta,
            actual_eta=true_eta,
        )

        loss = result["total_loss"]
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        total_loss += loss.item()

    return total_loss / len(loader)


@torch.no_grad()
def validate(model, loader, loss_fn, device, h3_index_map):
    model.eval()
    total_loss = 0.0

    for batch in loader:
        data = batch["data"].to(device)
        true_h3_list = batch["true_h3"]
        neg_h3s_list = batch["neg_h3s"]
        true_eta = batch["eta_seconds"].to(device)

        output = model(data)
        h3_scores = output["h3_scores"]
        pred_eta = output["eta_seconds"]

        num_scores = h3_scores.size(0)
        pos_indices = torch.tensor(
            [min(h3_index_map.get(h, 0), max(0, num_scores - 1)) for h in true_h3_list],
            dtype=torch.long, device=device
        )
        neg_scores = torch.stack([
            torch.tensor(
                [h3_scores[min(h3_index_map.get(n, 0), max(0, num_scores - 1))].item() for n in negs],
                device=device
            )
            for negs in neg_h3s_list
        ]).mean(dim=1)

        result = loss_fn(h3_scores, pos_indices, neg_scores, pred_eta, true_eta)
        total_loss += result["total_loss"].item()

    return total_loss / len(loader)


def main():
    args = parse_args()
    device = torch.device(args.device)
    os.makedirs(args.output_dir, exist_ok=True)

    logger.info(f"Training on {device}")

    # ── Build Components ──
    from pulse_chennai.config.settings import settings
    from pulse_chennai.graph.graph_builder import DynamicGraphBuilder
    from pulse_chennai.model.spatial_gnn import SpatialGNN
    from pulse_chennai.model.losses import MultiTaskLoss

    graph_builder = DynamicGraphBuilder(
        h3_feature_dim=settings.gnn.H3_FEATURE_DIM,
        bus_feature_dim=settings.gnn.BUS_FEATURE_DIM,
        temporal_dim=settings.gnn.TEMPORAL_DIM,
        k_ring_radius=2,
    )

    # ── Dataset ──
    dataset = build_dataset(args.data_dir, args.sequence_len, graph_builder)
    h3_index_map = dataset.get_h3_cell_index()

    val_size = int(len(dataset) * args.val_split)
    train_size = len(dataset) - val_size
    train_ds, val_ds = random_split(dataset, [train_size, val_size])

    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True,
        collate_fn=dataset.collate, num_workers=4, pin_memory=True,
    )
    val_loader = DataLoader(
        val_ds, batch_size=args.batch_size,
        collate_fn=dataset.collate, num_workers=2,
    )

    # ── Model ──
    model = SpatialGNN(
        h3_feature_dim=settings.gnn.H3_FEATURE_DIM,
        bus_feature_dim=settings.gnn.BUS_FEATURE_DIM,
        hidden_dim=args.hidden_dim,
        num_heads=args.num_heads,
        num_layers=args.num_layers,
        lstm_hidden=settings.gnn.LSTM_HIDDEN,
        dropout=settings.gnn.DROPOUT,
    ).to(device)

    loss_fn = MultiTaskLoss(learnable=True).to(device)
    optimizer = torch.optim.AdamW(
        list(model.parameters()) + list(loss_fn.parameters()),
        lr=args.lr, weight_decay=1e-5,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=args.epochs, eta_min=1e-5
    )

    # ── Training Loop ──
    best_val_loss = float("inf")
    for epoch in range(1, args.epochs + 1):
        train_loss = train_one_epoch(model, train_loader, optimizer, loss_fn, device, h3_index_map)
        val_loss = validate(model, val_loader, loss_fn, device, h3_index_map)
        scheduler.step()

        logger.info(
            f"Epoch {epoch:03d}/{args.epochs} | "
            f"Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f} | "
            f"LR: {scheduler.get_last_lr()[0]:.2e}"
        )

        # Save best checkpoint
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            path = os.path.join(args.output_dir, "pulse_gnn_best.pt")
            torch.save(model.state_dict(), path)
            logger.info(f"  ✓ New best model saved → {path}")

        # Periodic checkpoint
        if epoch % args.checkpoint_every == 0:
            path = os.path.join(args.output_dir, f"pulse_gnn_epoch_{epoch:03d}.pt")
            torch.save(model.state_dict(), path)

    logger.info(f"Training complete. Best val loss: {best_val_loss:.4f}")


if __name__ == "__main__":
    main()
