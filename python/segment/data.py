"""
Loads Phase 3 segmentation data straight from the dbt warehouse (data/warehouse.duckdb).
No feature engineering happens here -- that is mart_customer_features' job. This module only
reads what dbt already computed, for the segmentation snapshot cutoff (see docs/design.md:
cutoff B, 2011-09-01).
"""

from __future__ import annotations

import duckdb
import pandas as pd

RFM_COLUMNS = ["recency_days", "frequency", "monetary_net"]


def connect(db_path: str = "data/warehouse.duckdb") -> duckdb.DuckDBPyConnection:
    return duckdb.connect(db_path, read_only=True)


def load_snapshot(con: duckdb.DuckDBPyConnection, cutoff_date: str) -> pd.DataFrame:
    """One row per customer in mart_customer_features for cutoff_date, RFM columns plus
    is_wholesaler. Raises if nothing is found, rather than silently returning empty."""
    df = con.execute(
        """
        select customer_id, recency_days, frequency, monetary_net, is_wholesaler
        from mart_customer_features
        where cutoff_date = cast(? as timestamp)
        """,
        [cutoff_date],
    ).df()
    if df.empty:
        raise ValueError(
            f"segment.data.load_snapshot: no rows in mart_customer_features for "
            f"cutoff_date={cutoff_date}. Run `dbt build --vars '{{cutoff_date: \"{cutoff_date}\"}}'` "
            "first."
        )
    return df
