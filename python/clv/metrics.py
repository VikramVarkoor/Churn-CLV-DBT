"""
CLV holdout validation metrics. Fit quality alone is not validation (per the brief) -- every
function here compares a prediction against mart_clv_holdout_actuals' real outcomes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - predicted)))


def rank_correlation(actual: np.ndarray, predicted: np.ndarray) -> dict:
    rho, p_value = spearmanr(predicted, actual)
    return {"spearman_rho": float(rho), "p_value": float(p_value)}


def decile_table(predicted: pd.Series, actual: pd.Series, n_bins: int = 10) -> pd.DataFrame:
    """Deciles of `predicted` (1 = lowest predicted, n_bins = highest), mean predicted vs
    mean actual per decile. Uses rank-based binning (qcut on rank) so ties in a heavily
    zero-inflated predicted distribution don't collapse the bin count silently."""
    ranks = predicted.rank(method="first")
    bins = pd.qcut(ranks, n_bins, labels=False, duplicates="drop") + 1
    df = pd.DataFrame({"decile": bins, "predicted": predicted.to_numpy(), "actual": actual.to_numpy()})
    table = df.groupby("decile").agg(
        n=("predicted", "size"),
        mean_predicted=("predicted", "mean"),
        mean_actual=("actual", "mean"),
    )
    return table
