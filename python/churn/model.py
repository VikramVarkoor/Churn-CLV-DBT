"""
Phase 2 gradient boosting model (LightGBM), per docs/design.md.

Tuning happens ONLY inside the training period: a small fixed hyperparameter grid is each
fit on cutoff A, early-stopped against the validation cutoff (2010-12-01), and selected by
validation PR-AUC (LightGBM's native "average_precision" eval metric, confirmed to exist by
running it, not assumed from documentation -- see docs/evidence/p2_sandbox_test_log.txt).
The winning config is then refit once on cutoff A alone. Cutoff B is touched only for the
final, single evaluation in the pipeline script, never here.
"""

from __future__ import annotations

from typing import Any

import lightgbm as lgb
import pandas as pd

from churn.data import FEATURE_COLUMNS

GBM_FEATURES = FEATURE_COLUMNS

DEFAULT_PARAM_GRID: list[dict[str, Any]] = [
    {"num_leaves": 7, "learning_rate": 0.1, "min_child_samples": 20},
    {"num_leaves": 15, "learning_rate": 0.05, "min_child_samples": 20},
    {"num_leaves": 31, "learning_rate": 0.05, "min_child_samples": 10},
    {"num_leaves": 15, "learning_rate": 0.1, "min_child_samples": 10},
]


def tune_gbm(
    df_train: pd.DataFrame,
    df_val: pd.DataFrame,
    n_estimators: int = 300,
    early_stopping_rounds: int = 20,
    param_grid: list[dict[str, Any]] | None = None,
    random_state: int = 42,
) -> dict[str, Any]:
    """
    Fits one LightGBM model per entry in param_grid on df_train (cutoff A), early-stopping
    against df_val (the validation cutoff). Selects the entry with the best validation
    average_precision (PR-AUC). Returns a dict with the winning params, the early-stopped
    iteration count, and the validation score it achieved -- all of which get logged to
    p2_results.md so the tuning process is reproducible and visible, not a black box.
    """
    param_grid = param_grid if param_grid is not None else DEFAULT_PARAM_GRID
    X_train = df_train[GBM_FEATURES]
    y_train = df_train["churned"]
    X_val = df_val[GBM_FEATURES]
    y_val = df_val["churned"]

    best: dict[str, Any] | None = None
    trials: list[dict[str, Any]] = []
    for params in param_grid:
        clf = lgb.LGBMClassifier(
            n_estimators=n_estimators,
            objective="binary",
            random_state=random_state,
            verbosity=-1,
            **params,
        )
        clf.fit(
            X_train,
            y_train,
            eval_X=X_val,
            eval_y=y_val,
            eval_metric="average_precision",
            callbacks=[lgb.early_stopping(early_stopping_rounds, verbose=False)],
        )
        val_score = float(clf.best_score_["valid_0"]["average_precision"])
        trial = {
            "params": params,
            "best_iteration": int(clf.best_iteration_),
            "val_pr_auc": val_score,
        }
        trials.append(trial)
        if best is None or val_score > best["val_pr_auc"]:
            best = trial

    assert best is not None
    best["trials"] = trials
    return best


def fit_final_gbm(
    df_fit: pd.DataFrame, best_config: dict[str, Any], random_state: int = 42
) -> lgb.LGBMClassifier:
    """
    Refits one final model on df_fit (cutoff A's population only) using the params and
    iteration count chosen by tune_gbm. This is the model evaluated on cutoff B -- cutoff B
    is never seen during tuning or this refit.
    """
    X = df_fit[GBM_FEATURES]
    y = df_fit["churned"]
    n_estimators = max(best_config["best_iteration"], 1)
    clf = lgb.LGBMClassifier(
        n_estimators=n_estimators,
        objective="binary",
        random_state=random_state,
        verbosity=-1,
        **best_config["params"],
    )
    clf.fit(X, y)
    return clf


def predict_proba(clf: lgb.LGBMClassifier, df: pd.DataFrame) -> "pd.Series":
    return pd.Series(clf.predict_proba(df[GBM_FEATURES])[:, 1], index=df.index)
