"""
Multi-Task Loss Functions
============================
Custom loss combining:
1. BPR (Bayesian Personalized Ranking) — H3 cell ranking
2. MSE — ETA regression

Uses Kendall's Uncertainty Weighting for automatic
task balancing (learns α, β during training instead of
hand-tuning).

BPR ensures the GNN ranks the correct next H3 cell higher
than incorrect cells. MSE ensures the ETA prediction is
precise in seconds.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import logging

logger = logging.getLogger(__name__)


class BPRLoss(nn.Module):
    """
    Bayesian Personalized Ranking Loss.

    For ranking H3 cells as candidates for the bus's next position.

    loss = -log(σ(score_positive - score_negative))

    Where:
    - score_positive = model score for the TRUE next H3 cell
    - score_negative = model score for a RANDOMLY SAMPLED wrong cell

    This loss encourages the model to score the correct cell
    RELATIVELY higher than incorrect cells, without caring about
    absolute magnitudes.
    """

    def __init__(self, reduction: str = "mean"):
        super().__init__()
        self.reduction = reduction

    def forward(
        self,
        positive_scores: torch.Tensor,
        negative_scores: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            positive_scores: [batch] scores for correct H3 cells
            negative_scores: [batch] scores for sampled wrong H3 cells

        Returns:
            BPR loss scalar
        """
        diff = positive_scores - negative_scores
        loss = -F.logsigmoid(diff)

        if self.reduction == "mean":
            return loss.mean()
        elif self.reduction == "sum":
            return loss.sum()
        return loss

    @staticmethod
    def sample_negatives(
        h3_scores: torch.Tensor,
        positive_idx: torch.Tensor,
        num_negatives: int = 1,
    ) -> torch.Tensor:
        """
        Sample negative H3 cells (wrong next cells) for BPR training.

        Avoids sampling the positive cell itself.

        Args:
            h3_scores: [num_h3] model scores for all cells
            positive_idx: [batch] indices of the correct cells
            num_negatives: Number of negatives per positive

        Returns:
            negative_scores: [batch * num_negatives]
        """
        num_cells = h3_scores.size(0)
        batch_size = positive_idx.size(0)

        negative_indices = []
        for i in range(batch_size):
            pos = positive_idx[i].item()
            # Sample random indices excluding the positive
            candidates = list(range(num_cells))
            candidates.remove(pos) if pos < num_cells else None
            if candidates:
                neg_idx = torch.tensor(
                    candidates[:num_negatives], device=h3_scores.device
                )
            else:
                neg_idx = torch.zeros(num_negatives, dtype=torch.long,
                                       device=h3_scores.device)
            negative_indices.append(neg_idx)

        neg_indices = torch.cat(negative_indices)
        return h3_scores[neg_indices]


class ETALoss(nn.Module):
    """
    ETA Regression Loss.

    Simple MSE but with optional Huber fallback for robustness
    against outlier ETAs (e.g., a bus stuck for 30 minutes at
    a Chennai railway crossing).
    """

    def __init__(self, use_huber: bool = False, delta: float = 30.0):
        super().__init__()
        self.use_huber = use_huber
        self.delta = delta  # Huber threshold in seconds

    def forward(
        self,
        predicted_eta: torch.Tensor,
        actual_eta: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            predicted_eta: [batch] predicted ETA in seconds
            actual_eta: [batch] actual ETA in seconds

        Returns:
            Loss scalar
        """
        if self.use_huber:
            return F.huber_loss(predicted_eta, actual_eta, delta=self.delta)
        return F.mse_loss(predicted_eta, actual_eta)


class MultiTaskLoss(nn.Module):
    """
    Combined Multi-Task Loss with Kendall Uncertainty Weighting.

    L = (1/2σ₁²) * L_BPR + (1/2σ₂²) * L_ETA + log(σ₁) + log(σ₂)

    Where σ₁, σ₂ are LEARNABLE parameters that automatically balance
    the two task losses. The model learns how much to weight each task
    without manual α, β tuning.

    Fallback: fixed weights α=0.6, β=0.4 if learnable=False.

    Reference: Kendall et al., "Multi-Task Learning Using Uncertainty
    to Weigh Losses for Scene Geometry and Semantics" (CVPR 2018)
    """

    def __init__(
        self,
        bpr_weight: float = 0.6,
        mse_weight: float = 0.4,
        learnable: bool = True,
        use_huber_eta: bool = False,
    ):
        super().__init__()
        self.bpr_loss = BPRLoss()
        self.eta_loss = ETALoss(use_huber=use_huber_eta)
        self.learnable = learnable

        if learnable:
            # Log variance parameters (initialized to log(1) = 0)
            self.log_var_bpr = nn.Parameter(torch.zeros(1))
            self.log_var_eta = nn.Parameter(torch.zeros(1))
        else:
            self.bpr_weight = bpr_weight
            self.mse_weight = mse_weight

    def forward(
        self,
        h3_scores: torch.Tensor,
        positive_h3_idx: torch.Tensor,
        negative_h3_scores: torch.Tensor,
        predicted_eta: torch.Tensor,
        actual_eta: torch.Tensor,
    ) -> dict:
        """
        Compute combined loss.

        Args:
            h3_scores: [num_h3] model H3 cell scores
            positive_h3_idx: [batch] indices of correct next cells
            negative_h3_scores: [batch] scores of sampled wrong cells
            predicted_eta: [batch] predicted ETA seconds
            actual_eta: [batch] actual ETA seconds

        Returns:
            Dict with total_loss, bpr_loss, eta_loss, and weights
        """
        positive_scores = h3_scores[positive_h3_idx]
        loss_bpr = self.bpr_loss(positive_scores, negative_h3_scores)
        loss_eta = self.eta_loss(predicted_eta, actual_eta)

        if self.learnable:
            # Kendall uncertainty weighting
            precision_bpr = torch.exp(-self.log_var_bpr)
            precision_eta = torch.exp(-self.log_var_eta)

            total = (
                0.5 * precision_bpr * loss_bpr
                + 0.5 * precision_eta * loss_eta
                + self.log_var_bpr
                + self.log_var_eta
            )

            w_bpr = float(precision_bpr.item())
            w_eta = float(precision_eta.item())
        else:
            total = self.bpr_weight * loss_bpr + self.mse_weight * loss_eta
            w_bpr = self.bpr_weight
            w_eta = self.mse_weight

        return {
            "total_loss": total,
            "bpr_loss": loss_bpr.detach(),
            "eta_loss": loss_eta.detach(),
            "bpr_weight": w_bpr,
            "eta_weight": w_eta,
        }
