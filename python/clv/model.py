"""
BG/NBD (via pymc-marketing's BetaGeoModel) and Gamma-Gamma (via GammaGammaModel). See
docs/design.md, Phase 3 implementation decisions, and BUGLOG.md entry 6 for a real
sandbox-caught issue with the zero-frequency monetary fallback.
"""

from __future__ import annotations

import pandas as pd
from pymc_marketing.clv import BetaGeoModel, GammaGammaModel

BGNBD_RENAME = {"frequency_repeat": "frequency", "recency_cal_days": "recency", "t_days": "T"}


def fit_bgnbd(df_features: pd.DataFrame) -> BetaGeoModel:
    """Fits on ALL customers (frequency=0 single-purchase customers included -- BG/NBD is
    designed to handle them, unlike Gamma-Gamma)."""
    bg_df = df_features.rename(columns=BGNBD_RENAME)[["customer_id", "frequency", "recency", "T"]]
    model = BetaGeoModel()
    model.fit(bg_df, progressbar=False)
    return model


def fit_gamma_gamma(df_features: pd.DataFrame) -> dict:
    """Fits ONLY on repeat customers (frequency_repeat >= 1) -- Gamma-Gamma is conditioned on
    at least one repeat purchase's mean value and is not meaningful for frequency=0 customers
    (see BUGLOG.md entry 6). Also returns the empirical mean monetary_value among those repeat
    customers, used as a plug-in estimate for frequency_repeat=0 customers (see predict_clv)."""
    repeat = df_features[df_features["frequency_repeat"] >= 1].rename(
        columns={"frequency_repeat": "frequency"}
    )[["customer_id", "frequency", "monetary_value"]]
    model = GammaGammaModel()
    model.fit(repeat, progressbar=False)
    repeat_mean_monetary = float(repeat["monetary_value"].mean())
    return {"model": model, "repeat_mean_monetary": repeat_mean_monetary, "n_repeat": len(repeat)}


def predict_clv(
    df_features: pd.DataFrame,
    bgnbd_model: BetaGeoModel,
    gg_result: dict,
    holdout_days: int,
) -> pd.DataFrame:
    """Predicted transactions and spend over `holdout_days`, for every customer in
    df_features (including frequency_repeat=0 ones).

    predicted_transactions: BetaGeoModel.expected_purchases(future_t=holdout_days), posterior
    mean across chains/draws.
    predicted_monetary: GammaGammaModel.expected_customer_spend(...) posterior mean for
    frequency_repeat >= 1 customers; the empirical repeat_mean_monetary plug-in for
    frequency_repeat == 0 customers (see BUGLOG.md entry 6 for why the model's own
    expected_new_customer_spend() was not used for this).
    predicted_spend = predicted_transactions * predicted_monetary.
    """
    bg_df = df_features.rename(columns=BGNBD_RENAME)[["customer_id", "frequency", "recency", "T"]]
    predicted_transactions = (
        bgnbd_model.expected_purchases(bg_df, future_t=holdout_days)
        .mean(dim=["chain", "draw"])
        .to_series()
        .rename("predicted_transactions")
    )

    gg_model = gg_result["model"]
    repeat_mask = df_features["frequency_repeat"] >= 1
    repeat_df = df_features.loc[repeat_mask].rename(columns={"frequency_repeat": "frequency"})[
        ["customer_id", "frequency", "monetary_value"]
    ]
    repeat_spend = (
        gg_model.expected_customer_spend(repeat_df)
        .mean(dim=["chain", "draw"])
        .to_series()
        .rename("predicted_monetary")
    )

    out = df_features[["customer_id", "frequency_repeat"]].set_index("customer_id")
    out = out.join(predicted_transactions).join(repeat_spend)
    out["predicted_monetary"] = out["predicted_monetary"].fillna(gg_result["repeat_mean_monetary"])
    out["predicted_spend"] = out["predicted_transactions"] * out["predicted_monetary"]
    return out.reset_index()
