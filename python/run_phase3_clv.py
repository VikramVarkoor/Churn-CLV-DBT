"""
Phase 3 CLV: fits BG/NBD + Gamma-Gamma on the calibration cutoff (2011-03-01), checks the
Gamma-Gamma uncorrelated-frequency-and-monetary-value assumption, predicts transactions and
spend over the 245-day holdout window, and validates against mart_clv_holdout_actuals'
real outcomes (never used in fitting). Writes docs/evidence/p3_clv_validation.md.

Usage (from the project root, inside the venv):
    python3 python/run_phase3_clv.py

Requires `dbt build --vars '{cutoff_date: "2011-03-01"}'` to have already been run (this
builds mart_clv_features and mart_clv_holdout_actuals for that cutoff together).
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from clv import data, metrics, model  # noqa: E402

CALIBRATION_CUTOFF = "2011-03-01"
HOLDOUT_DAYS = 245


def main() -> None:
    con = data.connect()
    df_features = data.load_calibration(con, CALIBRATION_CUTOFF)
    df_actuals = data.load_holdout_actuals(con, CALIBRATION_CUTOFF)
    con.close()

    n_customers = len(df_features)
    n_repeat = int((df_features["frequency_repeat"] >= 1).sum())
    repeat_df = df_features[df_features["frequency_repeat"] >= 1]
    gg_corr = repeat_df["frequency_repeat"].corr(repeat_df["monetary_value"])

    bgnbd = model.fit_bgnbd(df_features)
    gg_result = model.fit_gamma_gamma(df_features)
    predictions = model.predict_clv(df_features, bgnbd, gg_result, HOLDOUT_DAYS)

    merged = predictions.merge(df_actuals, on="customer_id", how="inner")
    assert len(merged) == n_customers, "prediction/actuals row count mismatch -- check joins"

    txn_mae = metrics.mae(merged["actual_transactions"].to_numpy(), merged["predicted_transactions"].to_numpy())
    spend_mae = metrics.mae(merged["actual_spend"].to_numpy(), merged["predicted_spend"].to_numpy())
    spend_rank = metrics.rank_correlation(merged["actual_spend"].to_numpy(), merged["predicted_spend"].to_numpy())
    txn_rank = metrics.rank_correlation(merged["actual_transactions"].to_numpy(), merged["predicted_transactions"].to_numpy())
    txn_decile = metrics.decile_table(merged["predicted_transactions"], merged["actual_transactions"])
    spend_decile = metrics.decile_table(merged["predicted_spend"], merged["actual_spend"])

    lines = []
    lines.append("# Phase 3 CLV validation\n")
    lines.append(f"Generated: {dt.date.today().isoformat()}\n")
    lines.append(
        f"Calibration cutoff: {CALIBRATION_CUTOFF}. Holdout window: {HOLDOUT_DAYS} days "
        f"(evaluated once, below, never used during fitting).\n"
    )
    lines.append(f"n_customers={n_customers}, repeat customers (frequency_repeat >= 1) used to "
                  f"fit Gamma-Gamma: n_repeat={n_repeat}.\n")

    lines.append("## Gamma-Gamma assumption check\n")
    lines.append(
        f"Gamma-Gamma assumes frequency and mean order value are uncorrelated among repeat "
        f"customers. Checked, not assumed: Pearson correlation between frequency_repeat and "
        f"monetary_value over the {n_repeat} repeat customers in the calibration population "
        f"is {gg_corr:.3f}."
    )
    if abs(gg_corr) > 0.3:
        lines.append(
            "This is a real, non-trivial correlation, not close to zero -- the Gamma-Gamma "
            "assumption is violated on this population. The monetary predictions below are "
            "reported anyway, per the brief's instruction to report what is found, but this "
            "is a real limitation of the model on this dataset, not a detail to gloss over."
        )
    lines.append("")

    lines.append("## Holdout validation (never used in fitting)\n")
    lines.append(f"Transaction count MAE: {txn_mae:.3f}. Spend MAE: {spend_mae:.2f}.")
    lines.append(
        f"Spearman rank correlation, predicted vs actual transactions: "
        f"{txn_rank['spearman_rho']:.3f} (p={txn_rank['p_value']:.4f})."
    )
    lines.append(
        f"Spearman rank correlation, predicted vs actual spend (the CLV figure): "
        f"{spend_rank['spearman_rho']:.3f} (p={spend_rank['p_value']:.4f})."
    )
    lines.append("")

    lines.append("### Predicted vs actual transactions, by decile of predicted transactions\n")
    lines.append(txn_decile.round(3).to_markdown())
    lines.append("")
    lines.append("### Predicted vs actual spend, by decile of predicted spend\n")
    lines.append(spend_decile.round(2).to_markdown())
    lines.append("")

    report = "\n".join(lines) + "\n"
    out_path = Path("docs/evidence/p3_clv_validation.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    print(report)
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
