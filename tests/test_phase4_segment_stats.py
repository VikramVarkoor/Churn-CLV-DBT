"""
Phase 4's own pytest checks for python/build_segment_stats.py's aggregation logic
(aggregate_segment_stats). This is pure-Python arithmetic on already-scored per-customer
frames -- it does not touch the warehouse or re-run any model -- so it is tested here with
small synthetic frames rather than against data/warehouse.duckdb, same spirit as the
determinism check in test_phase3_leakage.py.

Checks: share_of_customers and share_of_revenue each sum to 1 across segments; a population
mismatch between the three input frames (segmentation vs churn-scored vs CLV-scored) raises
rather than silently dropping rows; and the rounding precision declared in
ROUND_PRECISION is actually applied.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from build_segment_stats import ROUND_PRECISION, aggregate_segment_stats  # noqa: E402


def _toy_inputs():
    segments = pd.DataFrame({
        "customer_id": [1, 2, 3, 4],
        "recency_days": [10.0, 20.0, 300.0, 310.0],
        "frequency": [10, 8, 1, 1],
        "monetary_net": [1000.0, 800.0, 50.0, 60.333333],
        "segment_id": [0, 0, 1, 1],
    })
    churn_scores = pd.DataFrame({
        "customer_id": [1, 2, 3, 4],
        "predicted_churn_proba": [0.1, 0.3, 0.9, 0.95],
    })
    clv_scores = pd.DataFrame({
        "customer_id": [1, 2, 3, 4],
        "predicted_spend": [500.0, 400.0, 20.0, 25.0],
    })
    return segments, churn_scores, clv_scores


def test_shares_sum_to_one():
    segments, churn_scores, clv_scores = _toy_inputs()
    rows = aggregate_segment_stats(segments, churn_scores, clv_scores)
    assert len(rows) == 2
    assert sum(r["share_of_customers"] for r in rows) == pytest.approx(1.0, abs=1e-6)
    assert sum(r["share_of_revenue"] for r in rows) == pytest.approx(1.0, abs=1e-6)


def test_segment_values_are_segment_specific_means():
    segments, churn_scores, clv_scores = _toy_inputs()
    rows = aggregate_segment_stats(segments, churn_scores, clv_scores)
    by_id = {r["segment_id"]: r for r in rows}
    # segment 0: customers 1, 2 -- churn mean (0.1+0.3)/2, clv mean (500+400)/2
    assert by_id[0]["predicted_churn_rate"] == pytest.approx(0.2, abs=1e-6)
    assert by_id[0]["predicted_clv_245d"] == pytest.approx(450.0, abs=1e-6)
    assert by_id[0]["n_customers"] == 2
    # segment 1: customers 3, 4
    assert by_id[1]["predicted_churn_rate"] == pytest.approx(0.925, abs=1e-6)


def test_raises_on_population_mismatch():
    segments, churn_scores, clv_scores = _toy_inputs()
    churn_scores_missing = churn_scores.iloc[:-1]  # drop customer 4
    with pytest.raises(ValueError, match="Join dropped rows"):
        aggregate_segment_stats(segments, churn_scores_missing, clv_scores)


def test_rounding_precision_applied():
    segments, churn_scores, clv_scores = _toy_inputs()
    rows = aggregate_segment_stats(segments, churn_scores, clv_scores)
    for r in rows:
        for field, ndigits in ROUND_PRECISION.items():
            assert r[field] == round(r[field], ndigits), (
                f"{field}={r[field]} not rounded to {ndigits} digits"
            )
