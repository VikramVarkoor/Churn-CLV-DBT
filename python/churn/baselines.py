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


def tune_recency_threshold(df_val: pd.DataFrame) -> tuple[float, float]:
    """
    Grid search over every observed recency_days value in the validation cutoff's
    population, picking the threshold X that maximizes F1 for the rule
    "churned if recency_days > X". Training-period only: df_val must be the validation
    cutoff's data, never cutoff B.

    Returns (best_threshold, best_f1_on_validation).
    """
    y = df_val["churned"].to_numpy()
    candidates = np.unique(df_val["recency_days"].to_numpy(dtype=float))
    best_threshold = None
    best_f1 = -1.0
    for x in candidates:
        pred = (df_val["recency_days"].to_numpy(dtype=float) > x).astype(int)
        tp = int(((pred == 1) & (y == 1)).sum())
        fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum())
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = float(x)
    if best_threshold is None:
        raise ValueError("tune_recency_threshold: no candidates found (empty df_val?)")
    return best_threshold, best_f1


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
