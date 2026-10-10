"""
Loads Phase 2 modeling data straight from the dbt warehouse (data/warehouse.duckdb).
No feature engineering happens here -- that is dbt's job (models/marts/mart_customer_features.sql,
mart_churn_labels.sql). This module only reads what dbt already computed, per cutoff.
"""

from __future__ import annotations

import duckdb
import pandas as pd

# All numeric columns in mart_customer_features usable as model inputs. "country" is
# intentionally excluded -- see docs/design.md, Phase 2 implementation decisions.
FEATURE_COLUMNS = [
    "recency_days",
    "frequency",
    "monetary_net",
    "monetary_gross",
    "tenure_days",
    "avg_basket_value",
    "distinct_products",
    "mean_days_between_purchases",
    "cancellation_rate",
    "total_quantity_purchased",
    "is_wholesaler",
]

# The brief's own wording for the logistic regression baseline: RFM only.
RFM_COLUMNS = ["recency_days", "frequency", "monetary_net"]


def connect(db_path: str = "data/warehouse.duckdb") -> duckdb.DuckDBPyConnection:
    return duckdb.connect(db_path, read_only=True)


def load_cutoff(con: duckdb.DuckDBPyConnection, cutoff_date: str) -> pd.DataFrame:
    """
    Returns one row per customer in mart_customer_features for the given cutoff_date,
    joined to its churn label from mart_churn_labels. Raises if nothing is found for that
    cutoff, rather than silently returning an empty frame a caller might not notice --
    an empty result means `dbt build --vars '{cutoff_date: "..."}'` hasn't been run yet for
    that cutoff, which is a setup error, not a legitimate zero-row result.
    """
    query = """
        select
            f.customer_id,
            f.cutoff_date,
            f.recency_days,
            f.frequency,
            f.monetary_net,
            f.monetary_gross,
            f.tenure_days,
            f.avg_basket_value,
            f.distinct_products,
            f.mean_days_between_purchases,
            f.cancellation_rate,
            f.country,
            f.total_quantity_purchased,
            f.is_wholesaler,
            l.churned
        from mart_customer_features f
        inner join mart_churn_labels l
            on f.customer_id = l.customer_id
            and f.cutoff_date = l.cutoff_date
        where f.cutoff_date = cast(? as timestamp)
    """
    df = con.execute(query, [cutoff_date]).df()
    if df.empty:
        raise ValueError(
            f"No rows found for cutoff_date={cutoff_date} in mart_customer_features / "
            f"mart_churn_labels. Run `dbt build --profiles-dir . --vars "
            f"'{{cutoff_date: \"{cutoff_date}\"}}'` for this cutoff first."
        )
    df["is_wholesaler"] = df["is_wholesaler"].astype(int)
    df["churned"] = df["churned"].astype(int)
    return df
