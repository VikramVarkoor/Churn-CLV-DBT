"""
Phase 2 evaluation metrics, per docs/design.md: PR-AUC and ROC-AUC as the primary comparison,
lift and capture in the top decile, calibration, and bootstrap confidence intervals over
customers (not over rows -- each customer is one independent resampling unit here, which is
correct since mart_customer_features/mart_churn_labels are already one row per customer per
cutoff).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


def pr_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    return float(average_precision_score(y_true, y_score))


def roc_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    return float(roc_auc_score(y_true, y_score))


def lift_and_capture_top_decile(y_true: np.ndarray, y_score: np.ndarray) -> dict[str, float]:
    """
    Sorts customers by y_score descending, takes the top 10% (rounding down, minimum 1
    customer), and reports:
      - capture_top_decile: fraction of ALL actual churners that fall in that top decile
        (i.e. recall restricted to the top-ranked 10%).
      - lift_top_decile: churn rate inside the top decile divided by the overall churn rate
        (how many times better than random targeting the top decile is).
    """
    n = len(y_true)
    if n == 0:
        raise ValueError("lift_and_capture_top_decile: empty input")
    order = np.argsort(-y_score)
    decile_n = max(1, int(np.floor(n * 0.10)))
    top_idx = order[:decile_n]

    total_churners = int(y_true.sum())
    top_churners = int(y_true[top_idx].sum())
    overall_rate = total_churners / n
    top_rate = top_churners / decile_n

    capture = (top_churners / total_churners) if total_churners > 0 else float("nan")
    lift = (top_rate / overall_rate) if overall_rate > 0 else float("nan")

    return {
        "capture_top_decile": capture,
        "lift_top_decile": lift,
        "decile_n": decile_n,
        "overall_churn_rate": overall_rate,
        "top_decile_churn_rate": top_rate,
    }


def calibration_table(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    """
    Equal-width bins over predicted probability [0, 1]. For each non-empty bin, reports the
    mean predicted probability vs the actual observed churn rate and the bin size. Only
    meaningful for a real probabilistic score (logistic regression, LightGBM) -- not called
    for the recency rule, which has no probability, per docs/design.md.
    """
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_idx = np.digitize(y_prob, bins[1:-1], right=True)
    rows = []
    for b in range(n_bins):
        mask = bin_idx == b
        count = int(mask.sum())
        if count == 0:
            continue
        rows.append(
            {
                "bin": f"[{bins[b]:.1f}, {bins[b + 1]:.1f})",
                "n": count,
                "mean_predicted": float(y_prob[mask].mean()),
                "observed_churn_rate": float(y_true[mask].mean()),
            }
        )
    return pd.DataFrame(rows)


def brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    return float(brier_score_loss(y_true, y_prob))


def bootstrap_ci(
    y_true: np.ndarray,
    y_score: np.ndarray,
    metric_fn,
    n_boot: int = 1000,
    alpha: float = 0.05,
    seed: int = 42,
) -> dict[str, float]:
    """
    Resamples customers (rows) with replacement n_boot times, recomputes metric_fn(y_true,
    y_score) on each resample, and returns the point estimate on the full data plus the
    (alpha/2, 1 - alpha/2) percentile interval across the bootstrap distribution. Skips
    resamples where metric_fn raises (e.g. a resample with zero positives, where PR-AUC/ROC-AUC
    are undefined) and reports how many of the n_boot draws were usable.
    """
    rng = np.random.default_rng(seed)
    n = len(y_true)
    point = float(metric_fn(y_true, y_score))
    draws = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        yt, ys = y_true[idx], y_score[idx]
        if yt.sum() == 0 or yt.sum() == n:
            continue
        try:
            draws.append(float(metric_fn(yt, ys)))
        except Exception:
            continue
    draws_arr = np.array(draws)
    lower = float(np.percentile(draws_arr, 100 * (alpha / 2))) if len(draws_arr) else float("nan")
    upper = (
        float(np.percentile(draws_arr, 100 * (1 - alpha / 2))) if len(draws_arr) else float("nan")
    )
    return {
        "point": point,
        "ci_lower": lower,
        "ci_upper": upper,
        "n_boot_used": len(draws_arr),
        "n_boot_requested": n_boot,
    }
