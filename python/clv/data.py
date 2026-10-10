"""
Loads Phase 3 CLV data straight from the dbt warehouse (data/warehouse.duckdb).
No feature engineering happens here -- that is mart_clv_features/mart_clv_holdout_actuals'
job (models/marts/mart_clv_features.sql, mart_clv_holdout_actuals.sql).
"""

from __future__ import annotations

import duckdb
import pandas as pd


def connect(db_path: str = "data/warehouse.duckdb") -> duckdb.DuckDBPyConnection:
    return duckdb.connect(db_path, read_only=True)


def load_calibration(con: duckdb.DuckDBPyConnection, cutoff_date: str) -> pd.DataFrame:
    df = con.execute(
        """
        select customer_id, frequency_repeat, t_days, recency_cal_days, monetary_value
        from mart_clv_features
        where cutoff_date = cast(? as timestamp)
        """,
        [cutoff_date],
    ).df()
    if df.empty:
        raise ValueError(
            f"clv.data.load_calibration: no rows in mart_clv_features for "
            f"cutoff_date={cutoff_date}. Run `dbt build --vars '{{cutoff_date: \"{cutoff_date}\"}}'` "
            "first."
        )
    return df


def load_holdout_actuals(con: duckdb.DuckDBPyConnection, cutoff_date: str) -> pd.DataFrame:
    df = con.execute(
        """
        select customer_id, actual_transactions, actual_spend
        from mart_clv_holdout_actuals
        where cutoff_date = cast(? as timestamp)
        """,
        [cutoff_date],
    ).df()
    if df.empty:
        raise ValueError(
            f"clv.data.load_holdout_actuals: no rows in mart_clv_holdout_actuals for "
            f"cutoff_date={cutoff_date}. Run `dbt build --vars '{{cutoff_date: \"{cutoff_date}\"}}'` "
            "first."
        )
    return df
