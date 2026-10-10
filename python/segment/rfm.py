"""
RFM quintile scoring. See docs/design.md, Phase 3 implementation decisions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _quintile_score(values: pd.Series, reverse: bool) -> tuple[pd.Series, int]:
    """Ranks `values` into up to 5 quintiles (1=worst, 5=best). `reverse=True` means a
    LOWER raw value is better (used for recency_days: fewer days since last purchase is
    good). Returns (scores, n_bins_actually_used) -- n_bins can be < 5 if the data has
    ties at a bin edge (pd.qcut with duplicates='drop'), which is reported, not hidden."""
    ranks, bin_edges = pd.qcut(values, 5, labels=False, duplicates="drop", retbins=True)
    n_bins = len(bin_edges) - 1
    # ranks are 0..n_bins-1, ascending with the raw value. Rescale to 1..5 regardless of
    # n_bins so quintile scores stay comparable in range even when ties collapsed bins.
    scores = 1 + ranks * (4 / (n_bins - 1)) if n_bins > 1 else pd.Series(3, index=values.index)
    scores = scores.round().astype(int)
    if reverse:
        scores = 6 - scores
    return scores, n_bins


def score(df: pd.DataFrame) -> dict:
    """Adds r_score, f_score, m_score, rfm_sum to a copy of df. Returns
    {"scored": df_copy, "bins_used": {"r": n, "f": n, "m": n}}."""
    out = df.copy()
    out["r_score"], r_bins = _quintile_score(out["recency_days"], reverse=True)
    out["f_score"], f_bins = _quintile_score(out["frequency"], reverse=False)
    out["m_score"], m_bins = _quintile_score(out["monetary_net"], reverse=False)
    out["rfm_sum"] = out["r_score"] + out["f_score"] + out["m_score"]
    return {"scored": out, "bins_used": {"r": r_bins, "f": f_bins, "m": m_bins}}
