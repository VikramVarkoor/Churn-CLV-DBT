"""
Phase 4: builds the per-segment stats JSON that the LLM summary layer reads. No new modeling
decision is made here -- this re-runs Phase 3's "all customers" segmentation (cutoff B) and
Phase 2's churn pipeline and Phase 3's CLV pipeline, exactly as already validated and reported,
and persists the per-customer outputs so they can be joined and averaged per segment. See
docs/design.md, "Phase 4 implementation decisions", for why each of these choices is a reuse of
an already-validated procedure, not a new one.

Usage (from the project root, inside the venv):
    python3 python/build_segment_stats.py

Requires `dbt build --vars '{cutoff_date: "..."}'` to have already been run for all three
cutoffs (2010-12-01 validation, 2011-03-01 train/A, 2011-09-01 test/B) -- same requirement as
Phase 2 and Phase 3.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from churn import data as churn_data  # noqa: E402
from churn import model as churn_model  # noqa: E402
from clv import data as clv_data  # noqa: E402
from clv import model as clv_model  # noqa: E402
from segment import data as segment_data  # noqa: E402
from segment import kmeans  # noqa: E402

VALIDATION_CUTOFF = "2010-12-01"
TRAIN_CUTOFF = "2011-03-01"  # also the CLV calibration cutoff (Phase 3's cutoff A)
TEST_CUTOFF = "2011-09-01"  # segmentation snapshot + scored population (Phase 3's cutoff B)
CLV_HOLDOUT_DAYS = 245  # Phase 3's own validated horizon, reused unchanged

# Fixed, documented rounding precision, applied before the JSON is handed to the LLM, so the
# verification step's tolerance check has an unambiguous source of truth (docs/design.md).
ROUND_PRECISION = {
    "share_of_customers": 4,
    "share_of_revenue": 4,
    "mean_recency_days": 1,
    "mean_frequency": 2,
    "mean_monetary_net": 2,
    "predicted_churn_rate": 4,
    "predicted_clv_245d": 2,
}


def build_segmentation(con) -> pd.DataFrame:
    """Reuses Phase 3's exact 'all customers' pipeline on cutoff B. Returns customer_id ->
    segment label, plus the RFM columns needed for per-segment aggregation."""
    df = segment_data.load_snapshot(con, TEST_CUTOFF)
    prep = kmeans.prepare_matrix(df)
    k_result = kmeans.choose_k(prep["X"])
    final = kmeans.fit_final(prep["X"], k_result["best_k"])
    out = df[["customer_id", "recency_days", "frequency", "monetary_net"]].copy()
    out["segment_id"] = final["labels"]
    print(
        f"[build_segmentation] chosen k={k_result['best_k']} (silhouette={final['silhouette']:.3f}). "
        "p3_segments.md reports k=4 on the real 'all customers' population at this cutoff; on "
        "the sandbox's small synthetic fixture this can legitimately pick a different k, same "
        "as Phase 3's own sandbox-vs-real numbers differed while the pipeline stayed identical."
    )
    return out


def build_churn_scores(con) -> pd.DataFrame:
    """Reuses Phase 2's exact tuning/fit procedure (validation cutoff for tuning, train cutoff
    A for fitting), scored on test cutoff B. Returns customer_id -> predicted churn
    probability."""
    df_val = churn_data.load_cutoff(con, VALIDATION_CUTOFF)
    df_train = churn_data.load_cutoff(con, TRAIN_CUTOFF)
    df_test = churn_data.load_cutoff(con, TEST_CUTOFF)

    tune_result = churn_model.tune_gbm(df_train, df_val)
    gbm = churn_model.fit_final_gbm(df_train, tune_result)
    proba = churn_model.predict_proba(gbm, df_test)

    out = df_test[["customer_id"]].copy()
    out["predicted_churn_proba"] = proba.to_numpy()
    return out


def build_clv_scores(con) -> pd.DataFrame:
    """Refits BG/NBD + Gamma-Gamma on cutoff A's calibration population (random_seed=42, Phase
    4's reproducibility addition -- see python/clv/model.py), then scores cutoff B's own
    customers out-of-sample via predict_clv. Returns customer_id -> predicted_spend over the
    245-day horizon."""
    df_calibration = clv_data.load_calibration(con, TRAIN_CUTOFF)
    df_score_pop = clv_data.load_calibration(con, TEST_CUTOFF)

    bgnbd = clv_model.fit_bgnbd(df_calibration, random_seed=42)
    gg_result = clv_model.fit_gamma_gamma(df_calibration, random_seed=42)
    predictions = clv_model.predict_clv(df_score_pop, bgnbd, gg_result, CLV_HOLDOUT_DAYS)
    return predictions[["customer_id", "predicted_spend"]]


def aggregate_segment_stats(
    segments: pd.DataFrame, churn_scores: pd.DataFrame, clv_scores: pd.DataFrame
) -> list[dict]:
    merged = segments.merge(churn_scores, on="customer_id", how="inner")
    merged = merged.merge(clv_scores, on="customer_id", how="inner")
    if len(merged) != len(segments):
        raise ValueError(
            f"Join dropped rows: segments={len(segments)}, after churn join + clv join="
            f"{len(merged)}. All three populations should be cutoff B's full customer set -- "
            "check that all three dbt builds used the same cutoff_date."
        )

    total_revenue = merged["monetary_net"].sum()
    rows = []
    for segment_id, g in merged.groupby("segment_id"):
        rows.append({
            "segment_id": int(segment_id),
            "n_customers": int(len(g)),
            "share_of_customers": len(g) / len(merged),
            "share_of_revenue": g["monetary_net"].sum() / total_revenue,
            "mean_recency_days": float(g["recency_days"].mean()),
            "mean_frequency": float(g["frequency"].mean()),
            "mean_monetary_net": float(g["monetary_net"].mean()),
            "predicted_churn_rate": float(g["predicted_churn_proba"].mean()),
            "predicted_clv_245d": float(g["predicted_spend"].mean()),
        })
    rows.sort(key=lambda r: r["mean_monetary_net"], reverse=True)

    for r in rows:
        for field, ndigits in ROUND_PRECISION.items():
            r[field] = round(r[field], ndigits)
    return rows


def main() -> None:
    con = segment_data.connect()
    segments = build_segmentation(con)
    churn_scores = build_churn_scores(con)
    clv_scores = build_clv_scores(con)
    con.close()

    segment_stats = aggregate_segment_stats(segments, churn_scores, clv_scores)

    out = {
        "generated": dt.date.today().isoformat(),
        "population_cutoff": TEST_CUTOFF,
        "clv_horizon_days": CLV_HOLDOUT_DAYS,
        "churn_model": "LightGBM, tuned on validation cutoff, fit on train cutoff A, scored on "
                        "population cutoff -- same procedure as docs/evidence/p2_results.md",
        "clv_model": "BG/NBD + Gamma-Gamma, fit on train cutoff A calibration population, "
                     "scored out-of-sample on population cutoff -- same procedure as "
                     "docs/evidence/p3_clv_validation.md, accuracy characteristics there apply "
                     "here unchanged",
        "rounding_precision": ROUND_PRECISION,
        "segments": segment_stats,
    }

    out_path = Path("docs/evidence/segment_stats.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
