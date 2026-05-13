"""
Spatial-Temporal GNN — The Brain of Pulse-Chennai
=====================================================
A Multi-Head Graph Attention Network (GAT) designed for
dynamic bus position prediction on H3 hexagonal grids.

Architecture:
┌─────────────────────────────────────┐
│  Input: HeteroData                  │
│  (h3_cell + bus_trip nodes/edges)   │
└──────────────┬──────────────────────┘
               │
   ┌───────────▼───────────┐
   │  Linear Projection    │  (h3_feat_dim → hidden_dim)
   │  (per node type)      │  (bus_feat_dim → hidden_dim)
   └───────────┬───────────┘
               │
   ┌───────────▼───────────┐
   │  GAT Layer 1          │  Multi-head attention
   │  (heterogeneous)      │  learns which neighbors matter
   └───────────┬───────────┘
               │ + Residual + LayerNorm
   ┌───────────▼───────────┐
   │  GAT Layer 2          │
   └───────────┬───────────┘
               │ + Residual + LayerNorm
   ┌───────────▼───────────┐
   │  GAT Layer 3          │
   └───────────┬───────────┘
               │
   ┌───────────▼───────────┐
   │  Temporal LSTM Cell   │  Sequential state evolution
   └───────────┬───────────┘
               │
       ┌───────┴────────┐
       │                │
   ┌───▼────┐     ┌─────▼─────┐
   │ H3     │     │ ETA       │
   │ Ranker │     │ Regressor │
   │ (BPR)  │     │ (MSE)     │
   └────────┘     └───────────┘

Innovation over Uber's approach:
- Uber used GraphSAGE (uniform aggregation) for static graphs
- We use GAT (attention-weighted) for dynamic spatial-temporal graphs
- Attention learns that intersections/bottlenecks matter more than
  open road cells — critical for Chennai's chaotic traffic topology
"""

import logging
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)

try:
    from torch_geometric.nn import GATConv, to_hetero, Linear
    from torch_geometric.data import HeteroData
    PYG_AVAILABLE = True
except ImportError:
    PYG_AVAILABLE = False
    logger.warning("PyTorch Geometric not installed. SpatialGNN is stub-only.")


class HomogeneousGATBackbone(nn.Module):
    """
    Base homogeneous GAT, later converted to heterogeneous via to_hetero().

    Using the to_hetero() pattern because:
    1. Cleaner code than manually defining per-edge-type convolutions
    2. Automatic handling of different feature spaces
    3. PyG's lazy initialization handles dimension mismatches
    """

    def __init__(
        self,
        hidden_dim: int = 128,
        num_heads: int = 4,
        num_layers: int = 3,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.num_layers = num_layers

        # GAT convolution layers
        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()

        for i in range(num_layers):
            # Input dim = -1 enables lazy initialization
            conv = GATConv(
                in_channels=(-1, -1),
                out_channels=hidden_dim // num_heads,
                heads=num_heads,
                dropout=dropout,
                add_self_loops=False,   # Explicit in hetero graph
                concat=True,
            )
            self.convs.append(conv)
            self.norms.append(nn.LayerNorm(hidden_dim))

        self.dropout = nn.Dropout(dropout)

    def forward(self, x, edge_index, edge_attr=None):
        """
        Forward pass through GAT layers with residuals.

        The attention mechanism automatically learns:
        - Intersection cells with high traffic → high attention weight
        - Empty cells on straight roads → low attention weight
        This is the KEY advantage over Uber's GraphSAGE.
        """
        for i in range(self.num_layers):
            residual = x if i > 0 else None

            x = self.convs[i](x, edge_index)
            x = self.norms[i](x)
            x = F.elu(x)
            x = self.dropout(x)

            # Residual connection (after first layer aligns dims)
            if residual is not None:
                x = x + residual

        return x


class SpatialGNN(nn.Module):
    """
    The main Pulse-Chennai inference model.

    Dual-head output:
    1. H3 Ranker: scores candidate cells for bus's next position
       → trained with BPR (Bayesian Personalized Ranking)
    2. ETA Regressor: predicts seconds to destination
       → trained with MSE

    The temporal LSTM captures sequential position evolution:
    bus moves cell A → B → C over time steps t, t+1, t+2.
    The LSTM hidden state encodes "movement momentum."
    """

    def __init__(
        self,
        h3_feature_dim: int = 12,
        bus_feature_dim: int = 16,
        hidden_dim: int = 128,
        num_heads: int = 4,
        num_layers: int = 3,
        lstm_hidden: int = 64,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.lstm_hidden = lstm_hidden

        # Input projections: map different feature spaces → hidden_dim
        self.h3_proj = nn.Linear(h3_feature_dim, hidden_dim)
        self.bus_proj = nn.Linear(bus_feature_dim, hidden_dim)

        # GAT backbone (homogeneous, will be converted to hetero)
        self._backbone = HomogeneousGATBackbone(
            hidden_dim=hidden_dim,
            num_heads=num_heads,
            num_layers=num_layers,
            dropout=dropout,
        )

        # The magic: convert homogeneous GAT → heterogeneous
        # This creates per-edge-type message passing automatically
        self._hetero_model = None  # Built lazily on first forward

        # Temporal LSTM for sequential state tracking
        self.temporal_lstm = nn.LSTMCell(
            input_size=hidden_dim,
            hidden_size=lstm_hidden,
        )

        # ── Output Heads ──

        # H3 Ranker: score each H3 cell as candidate next position
        self.h3_ranker = nn.Sequential(
            nn.Linear(hidden_dim + lstm_hidden, hidden_dim),
            nn.ELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),  # Scalar score per cell
        )

        # ETA Regressor: predict seconds to destination
        self.eta_regressor = nn.Sequential(
            nn.Linear(hidden_dim + lstm_hidden, hidden_dim),
            nn.ELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),  # Scalar ETA in seconds
            nn.ReLU(),                 # ETA must be non-negative
        )

        # Ghost Recovery Head: estimate confidence of position
        self.ghost_confidence = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ELU(),
            nn.Linear(64, 1),
            nn.Sigmoid(),  # Confidence [0, 1]
        )

    def _build_hetero_model(self, data: "HeteroData"):
        """
        Lazily build the heterogeneous model from the first data sample.
        This resolves the metadata (node types, edge types) at runtime.
        """
        if PYG_AVAILABLE and self._hetero_model is None:
            metadata = data.metadata()
            self._hetero_model = to_hetero(
                self._backbone, metadata, aggr="mean"
            )
            logger.info(
                f"Hetero model built with metadata: "
                f"node_types={metadata[0]}, edge_types={metadata[1]}"
            )

    def forward(
        self,
        data: "HeteroData",
        bus_lstm_state: Optional[tuple[torch.Tensor, torch.Tensor]] = None,
    ) -> dict:
        """
        Forward pass: HeteroData → predictions.

        Args:
            data: HeteroData graph from DynamicGraphBuilder
            bus_lstm_state: (h, c) from previous timestep for LSTM continuity

        Returns:
            Dict with:
            - h3_scores: [num_h3,] ranking scores for each H3 cell
            - eta_seconds: [num_buses,] ETA predictions
            - ghost_confidence: [num_h3,] position confidence
            - h3_embeddings: [num_h3, hidden_dim] learned representations
            - bus_embeddings: [num_buses, hidden_dim] learned representations
            - lstm_state: (h, c) for next timestep
        """
        # ── 1. Project input features to hidden_dim ──
        data["h3_cell"].x = self.h3_proj(data["h3_cell"].x)
        data["bus_trip"].x = self.bus_proj(data["bus_trip"].x)

        # ── 2. Heterogeneous GAT message passing ──
        self._build_hetero_model(data)

        if self._hetero_model is not None:
            x_dict = self._hetero_model(data.x_dict, data.edge_index_dict)
        else:
            # Fallback: simple linear pass (no message passing)
            x_dict = {
                "h3_cell": data["h3_cell"].x,
                "bus_trip": data["bus_trip"].x,
            }

        h3_emb = x_dict["h3_cell"]      # [num_h3, hidden_dim]
        bus_emb = x_dict["bus_trip"]     # [num_buses, hidden_dim]

        # ── 3. Temporal LSTM (per bus) ──
        if bus_lstm_state is None:
            h_0 = torch.zeros(bus_emb.size(0), self.lstm_hidden, device=bus_emb.device)
            c_0 = torch.zeros(bus_emb.size(0), self.lstm_hidden, device=bus_emb.device)
        else:
            h_0, c_0 = bus_lstm_state
            # Handle size mismatch if number of buses changed
            if h_0.size(0) != bus_emb.size(0):
                h_0 = torch.zeros(bus_emb.size(0), self.lstm_hidden, device=bus_emb.device)
                c_0 = torch.zeros(bus_emb.size(0), self.lstm_hidden, device=bus_emb.device)

        # LSTM encodes "movement momentum" across timesteps
        h_new, c_new = self.temporal_lstm(bus_emb, (h_0, c_0))

        # ── 4. Output Heads ──

        # H3 Ranker: combine H3 embeddings with bus temporal state
        # Broadcast bus state to all H3 cells (global context)
        bus_context = h_new.mean(dim=0, keepdim=True)  # [1, lstm_hidden]
        bus_context_expanded = bus_context.expand(h3_emb.size(0), -1)  # [num_h3, lstm_hidden]

        h3_with_temporal = torch.cat([h3_emb, bus_context_expanded], dim=-1)
        h3_scores = self.h3_ranker(h3_with_temporal).squeeze(-1)  # [num_h3]

        # ETA Regressor: per-bus prediction
        bus_with_temporal = torch.cat([bus_emb, h_new], dim=-1)
        eta_pred = self.eta_regressor(bus_with_temporal).squeeze(-1)  # [num_buses]

        # Ghost Confidence: per-H3-cell
        ghost_conf = self.ghost_confidence(h3_emb).squeeze(-1)  # [num_h3]

        return {
            "h3_scores": h3_scores,
            "eta_seconds": eta_pred,
            "ghost_confidence": ghost_conf,
            "h3_embeddings": h3_emb,
            "bus_embeddings": bus_emb,
            "lstm_state": (h_new, c_new),
        }

    def predict_next_cell(
        self,
        data: "HeteroData",
        bus_lstm_state: Optional[tuple] = None,
        top_k: int = 3,
    ) -> dict:
        """
        Inference convenience: get the top-k predicted H3 cells.

        Returns:
            Dict with:
            - top_cells: List of (h3_index, score, confidence) tuples
            - eta_seconds: float
            - lstm_state: for next timestep
        """
        self.eval()
        with torch.no_grad():
            output = self.forward(data, bus_lstm_state)

        scores = output["h3_scores"]
        confidences = output["ghost_confidence"]
        cell_indices = getattr(data["h3_cell"], "cell_indices", None)

        top_k_vals, top_k_idx = torch.topk(scores, min(top_k, len(scores)))

        top_cells = []
        for i in range(len(top_k_idx)):
            idx = top_k_idx[i].item()
            cell_name = cell_indices[idx] if cell_indices else f"cell_{idx}"
            top_cells.append({
                "h3_index": cell_name,
                "score": float(top_k_vals[i]),
                "confidence": float(confidences[idx]),
            })

        eta = float(output["eta_seconds"].mean()) if output["eta_seconds"].numel() > 0 else 0.0

        return {
            "top_cells": top_cells,
            "eta_seconds": eta,
            "lstm_state": output["lstm_state"],
        }
