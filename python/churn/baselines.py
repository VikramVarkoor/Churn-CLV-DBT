"""
Phase 2 baselines, per docs/design.md:
  (1) a recency rule, used both as a ranking score (recency_days itself) and as a tuned
      threshold classifier for an interpretable operating point.
  (2) logistic regression on RFM features only (recency_days, frequency, monetary_net).

Both are tuned ONLY on training-period data (cutoff A to fit, the validation cutoff to tune),
never touching cutoff B until the final, single evaluation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from churn.data import RFM_COLUMNS


def recency_score(df: pd.DataFrame) -> np.ndarray:
    """Higher recency_days = more likely to have churned. Used directly as a continuous
    ranking score for PR-AUC / ROC-AUC / lift / decile capture -- no threshold involved."""
    return df["recency_days"].to_numpy(dtype=float)


def tune_recency_threshold(df_val: pd.DataFrame) -> dict:
    """
    Grid search over every observed recency_days value in the validation cutoff's
    population, picking the threshold X that maximizes Youden's J statistic
    (true positive rate minus false positive rate) for the rule
    "churned if recency_days > X". Training-period only: df_val must be the validation
    cutoff's data, never cutoff B.

    NOT F1: an earlier version of this function maximized F1, which on the real validation
    cutoff (66.8% churned -- a majority-positive population under this label definition)
    collapsed to a near-trivial threshold (X=1 day, precision=0.574, recall=0.996 on test B)
    because F1-argmax is known to degenerate toward predicting the majority class under class
    imbalance. Found on the real first run, not hypothesized -- see BUGLOG.md entry 5. Youden's
    J does not have this failure mode: it is the point on the ROC curve furthest from the
    diagonal, and is insensitive to class prevalence in a way F1 is not.

    Returns a dict with the chosen threshold and the validation-set confusion stats at that
    threshold, so the tuning process is visible, not a black box.
    """
    y = df_val["churned"].to_numpy()
    n_pos = int(y.sum())
    n_neg = int(len(y) - n_pos)
    candidates = np.unique(df_val["recency_days"].to_numpy(dtype=float))
    best_threshold = None
    best_j = -2.0
    best_stats = None
    for x in candidates:
        pred = (df_val["recency_days"].to_numpy(dtype=float) > x).astype(int)
        tp = int(((pred == 1) & (y == 1)).sum())
        fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum())
        tn = int(((pred == 0) & (y == 0)).sum())
        tpr = tp / n_pos if n_pos else 0.0
        fpr = fp / n_neg if n_neg else 0.0
        j = tpr - fpr
        if j > best_j:
            best_j = j
            best_threshold = float(x)
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            best_stats = {
                "tpr": tpr, "fpr": fpr, "precision": precision,
                "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            }
    if best_threshold is None:
        raise ValueError("tune_recency_threshold: no candidates found (empty df_val?)")
    return {"threshold": best_threshold, "youden_j": best_j, "validation_stats": best_stats}


def recency_rule_predict(df: pd.DataFrame, threshold: float) -> np.ndarray:
    return (df["recency_days"].to_numpy(dtype=float) > threshold).astype(int)


class LogisticRFMBaseline:
    """Logistic regression on RFM features only (recency_days, frequency, monetary_net),
    standardized before fitting. Fit on cutoff A's population; the validation cutoff is not
    used to tune this baseline since it has no hyperparameters worth tuning here, only an
    L2 regularization default -- scikit-learn's default C=1.0 is used as-is and documented as
    not tuned, rather than tuned and not disclosed."""

    FEATURES = RFM_COLUMNS

    def __init__(self) -> None:
        self.scaler = StandardScaler()
        self.model = LogisticRegression(max_iter=1000)

    def fit(self, df_train: pd.DataFrame) -> "LogisticRFMBaseline":
        X = df_train[self.FEATURES].to_numpy(dtype=float)
        y = df_train["churned"].to_numpy(dtype=int)
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
        return self

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        X = df[self.FEATURES].to_numpy(dtype=float)
        X_scaled = self.scaler.transform(X)
        return self.model.predict_proba(X_scaled)[:, 1]
