"""
Phase 2 orchestration: loads the validation cutoff, train cutoff A, and test cutoff B from
the dbt warehouse, fits the two baselines and the LightGBM model (tuned only on
A/validation), evaluates all three ONCE on cutoff B, and writes
docs/evidence/p2_results.md.

Usage (from the project root, inside the venv):
    python3 python/run_phase2.py

Requires `dbt build` to have already been run for all three cutoffs in docs/design.md
(2010-12-01 validation, 2011-03-01 train/A, 2011-09-01 test/B).
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from churn import baselines, data, metrics, model  # noqa: E402

VALIDATION_CUTOFF = "2010-12-01"
TRAIN_CUTOFF = "2011-03-01"
TEST_CUTOFF = "2011-09-01"

N_BOOT = 1000


def evaluate_scorer(name: str, y_true: np.ndarray, y_score: np.ndarray) -> dict:
    pr_ci = metrics.bootstrap_ci(y_true, y_score, metrics.pr_auc, n_boot=N_BOOT)
    roc_ci = metrics.bootstrap_ci(y_true, y_score, metrics.roc_auc, n_boot=N_BOOT)
    lift_capture = metrics.lift_and_capture_top_decile(y_true, y_score)
    return {
        "name": name,
        "pr_auc": pr_ci,
        "roc_auc": roc_ci,
        "lift_capture": lift_capture,
    }


def format_ci(d: dict) -> str:
    return f"{d['point']:.3f} [{d['ci_lower']:.3f}, {d['ci_upper']:.3f}] (n_boot_used={d['n_boot_used']})"


def main() -> None:
    con = data.connect()
    df_val = data.load_cutoff(con, VALIDATION_CUTOFF)
    df_train = data.load_cutoff(con, TRAIN_CUTOFF)
    df_test = data.load_cutoff(con, TEST_CUTOFF)
    con.close()

    class_balance = {
        "validation": (VALIDATION_CUTOFF, len(df_val), int(df_val["churned"].sum())),
        "train_A": (TRAIN_CUTOFF, len(df_train), int(df_train["churned"].sum())),
        "test_B": (TEST_CUTOFF, len(df_test), int(df_test["churned"].sum())),
    }

    # --- Baseline 1: recency rule ---
    threshold, val_f1 = baselines.tune_recency_threshold(df_val)
    recency_score_test = baselines.recency_score(df_test)
    recency_pred_test = baselines.recency_rule_predict(df_test, threshold)
    recency_eval = evaluate_scorer("recency_rule", df_test["churned"].to_numpy(), recency_score_test)

    tp = int(((recency_pred_test == 1) & (df_test["churned"].to_numpy() == 1)).sum())
    fp = int(((recency_pred_test == 1) & (df_test["churned"].to_numpy() == 0)).sum())
    fn = int(((recency_pred_test == 0) & (df_test["churned"].to_numpy() == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    # --- Baseline 2: logistic regression on RFM ---
    logreg = baselines.LogisticRFMBaseline().fit(df_train)
    logreg_score_test = logreg.predict_proba(df_test)
    logreg_eval = evaluate_scorer("logistic_rfm", df_test["churned"].to_numpy(), logreg_score_test)
    logreg_calibration = metrics.calibration_table(df_test["churned"].to_numpy(), logreg_score_test)
    logreg_brier = metrics.brier_score(df_test["churned"].to_numpy(), logreg_score_test)

    # --- Model: LightGBM, tuned on A/validation, evaluated once on B ---
    tune_result = model.tune_gbm(df_train, df_val)
    gbm = model.fit_final_gbm(df_train, tune_result)
    gbm_score_test = model.predict_proba(gbm, df_test).to_numpy()
    gbm_eval = evaluate_scorer("lightgbm", df_test["churned"].to_numpy(), gbm_score_test)
    gbm_calibration = metrics.calibration_table(df_test["churned"].to_numpy(), gbm_score_test)
    gbm_brier = metrics.brier_score(df_test["churned"].to_numpy(), gbm_score_test)

    # --- Write report ---
    lines = []
    lines.append("# Phase 2 results\n")
    lines.append(f"Generated: {dt.date.today().isoformat()}\n")
    lines.append(
        f"Validation cutoff: {VALIDATION_CUTOFF}. Train cutoff A: {TRAIN_CUTOFF}. "
        f"Test cutoff B: {TEST_CUTOFF} (evaluated once, below).\n"
    )

    lines.append("## Class balance\n")
    for label, (cutoff, n, n_churn) in class_balance.items():
        rate = n_churn / n if n else float("nan")
        lines.append(f"- {label} ({cutoff}): n={n}, churned={n_churn}, churn_rate={rate:.3f}")
    lines.append("")

    lines.append("## Recency rule\n")
    lines.append(
        f"Threshold tuned on validation cutoff ({VALIDATION_CUTOFF}) only, maximizing F1: "
        f"X = {threshold:.0f} days (validation F1 = {val_f1:.3f})."
    )
    lines.append(
        f"At this threshold on test cutoff B: precision={precision:.3f}, recall={recall:.3f}, "
        f"tp={tp}, fp={fp}, fn={fn}."
    )
    lines.append("Calibration: not reported for the recency rule -- a raw day count is not a "
                  "probability (see docs/design.md).")
    lines.append("")

    lines.append("## LightGBM tuning (validation cutoff only, never touches B)\n")
    for trial in tune_result["trials"]:
        lines.append(
            f"- params={trial['params']}, best_iteration={trial['best_iteration']}, "
            f"val_pr_auc={trial['val_pr_auc']:.3f}"
        )
    lines.append(
        f"Winner: params={tune_result['params']}, iterations={tune_result['best_iteration']}, "
        f"val_pr_auc={tune_result['val_pr_auc']:.3f}"
    )
    lines.append("")

    lines.append("## Results on test cutoff B (evaluated once)\n")
    lines.append("| Model | PR-AUC (95% CI) | ROC-AUC (95% CI) | Lift @ top decile | Capture @ top decile | Brier score |")
    lines.append("|---|---|---|---|---|---|")
    for ev, brier in [(recency_eval, None), (logreg_eval, logreg_brier), (gbm_eval, gbm_brier)]:
        brier_str = f"{brier:.3f}" if brier is not None else "N/A"
        lc = ev["lift_capture"]
        lines.append(
            f"| {ev['name']} | {format_ci(ev['pr_auc'])} | {format_ci(ev['roc_auc'])} | "
            f"{lc['lift_top_decile']:.2f}x | {lc['capture_top_decile']:.3f} | {brier_str} |"
        )
    lines.append("")

    lines.append("## Calibration tables\n")
    lines.append("### Logistic regression (RFM)\n")
    lines.append(logreg_calibration.to_markdown(index=False))
    lines.append("")
    lines.append("### LightGBM\n")
    lines.append(gbm_calibration.to_markdown(index=False))
    lines.append("")

    lines.append("## Success criterion (docs/design.md)\n")
    gbm_pr = gbm_eval["pr_auc"]
    rec_pr = recency_eval["pr_auc"]
    non_overlapping = gbm_pr["ci_lower"] > rec_pr["ci_upper"]
    lines.append(
        f"LightGBM PR-AUC CI lower bound ({gbm_pr['ci_lower']:.3f}) vs recency rule PR-AUC CI "
        f"upper bound ({rec_pr['ci_upper']:.3f}): "
        + ("non-overlapping, model clearly beats the baseline." if non_overlapping
           else "overlapping or not clearly ahead -- per the brief's ground rules, this is "
                "reported plainly, not glossed over.")
    )

    report = "\n".join(lines) + "\n"
    out_path = Path("docs/evidence/p2_results.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    print(report)
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
