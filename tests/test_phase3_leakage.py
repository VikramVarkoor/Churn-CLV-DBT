"""
Phase 3's own pytest leakage checks, same discipline as test_phase2_leakage.py: Python-side,
independent of dbt entirely, recomputing mart_clv_features and mart_clv_holdout_actuals
straight from stg_online_retail and comparing. Mirrors tests/no_clv_feature_leakage.sql and
tests/no_clv_holdout_leakage.sql as a second, independent implementation, not a restatement.

Also checks that the k-means segmentation pipeline (python/segment/kmeans.py) is deterministic
given a fixed random_state -- a real requirement for Phase 3's evidence files to be
reproducible, not just a nice-to-have.

Requires a built warehouse (data/warehouse.duckdb) with at least one cutoff already run via
`dbt build --vars '{cutoff_date: "..."}'`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from segment import data as segment_data  # noqa: E402
from segment import kmeans  # noqa: E402

DB_PATH = "data/warehouse.duckdb"


@pytest.fixture(scope="module")
def con():
    connection = duckdb.connect(DB_PATH, read_only=True)
    yield connection
    connection.close()


def _clv_cutoffs(con) -> list:
    return [row[0] for row in con.execute(
        "select distinct cutoff_date from mart_clv_features order by 1"
    ).fetchall()]


def test_clv_cutoffs_exist(con):
    cutoffs = _clv_cutoffs(con)
    assert cutoffs, (
        "No cutoffs found in mart_clv_features. Run `dbt build --profiles-dir . "
        "--vars '{cutoff_date: \"2011-03-01\"}'` before running these tests."
    )


def test_clv_features_match_independent_recomputation(con):
    """For every cutoff present in mart_clv_features, recomputes frequency_repeat, t_days,
    and recency_cal_days directly from stg_online_retail and checks exact matches."""
    for cutoff in _clv_cutoffs(con):
        mismatches = con.execute(
            """
            with valid_lines as (
                select *
                from stg_online_retail
                where invoice_date < cast(? as timestamp)
                  and invoice not like 'C%'
                  and customer_id is not null
            ),
            valid_orders as (
                select customer_id, invoice, min(invoice_date) as invoice_date
                from valid_lines
                group by customer_id, invoice
            ),
            ranked as (
                select
                    customer_id,
                    invoice_date,
                    row_number() over (partition by customer_id order by invoice_date, invoice) as order_rank
                from valid_orders
            ),
            independent as (
                select
                    customer_id,
                    count(*) - 1 as frequency_repeat_independent,
                    date_diff('day', min(invoice_date), cast(? as timestamp)) as t_days_independent,
                    date_diff('day', min(invoice_date), max(invoice_date)) as recency_cal_days_independent
                from ranked
                group by customer_id
            )
            select count(*)
            from mart_clv_features f
            inner join independent i on f.customer_id = i.customer_id
            where f.cutoff_date = cast(? as timestamp)
              and (
                f.frequency_repeat != i.frequency_repeat_independent
                or f.t_days != i.t_days_independent
                or f.recency_cal_days != i.recency_cal_days_independent
              )
            """,
            [cutoff, cutoff, cutoff],
        ).fetchone()[0]
        assert mismatches == 0, (
            f"mart_clv_features mismatch (possible leakage) at cutoff={cutoff}: {mismatches} rows"
        )


def test_clv_holdout_matches_independent_recomputation(con):
    """For every cutoff present, recomputes actual_transactions/actual_spend over the exact
    [cutoff, cutoff + clv_holdout_days) window directly from stg_online_retail."""
    for cutoff in _clv_cutoffs(con):
        # 245 is Phase 3's fixed holdout window, locked in dbt_project.yml's clv_holdout_days
        # var and docs/design.md. Hardcoded here deliberately -- this test independently
        # re-derives the number from the design doc's own stated value, not from the dbt var,
        # so a change to one without the other is caught rather than silently matched.
        mismatches = con.execute(
            """
            with valid_lines as (
                select *
                from stg_online_retail
                where invoice_date >= cast(? as timestamp)
                  and invoice_date < cast(? as timestamp) + interval '245 days'
                  and invoice not like 'C%'
                  and customer_id is not null
            ),
            valid_orders as (
                select customer_id, invoice, sum(quantity * price) as order_value
                from valid_lines
                group by customer_id, invoice
            ),
            independent as (
                select
                    customer_id,
                    count(distinct invoice) as transactions_independent,
                    sum(order_value) as spend_independent
                from valid_orders
                group by customer_id
            )
            select count(*)
            from mart_clv_holdout_actuals h
            inner join independent i on h.customer_id = i.customer_id
            where h.cutoff_date = cast(? as timestamp)
              and (
                h.actual_transactions != i.transactions_independent
                or abs(h.actual_spend - i.spend_independent) > 0.01
              )
            """,
            [cutoff, cutoff, cutoff],
        ).fetchone()[0]
        assert mismatches == 0, (
            f"mart_clv_holdout_actuals mismatch (possible leakage) at cutoff={cutoff}: "
            f"{mismatches} rows"
        )


def test_no_unexpected_nulls_in_clv_inputs(con):
    checks = [
        ("mart_clv_features", ["customer_id", "cutoff_date", "frequency_repeat", "t_days",
                                "recency_cal_days"]),
        ("mart_clv_holdout_actuals", ["customer_id", "cutoff_date", "actual_transactions",
                                       "actual_spend"]),
    ]
    for table, cols in checks:
        for col in cols:
            n_null = con.execute(f"select count(*) from {table} where {col} is null").fetchone()[0]
            assert n_null == 0, f"{table}.{col} has {n_null} unexpected nulls"


def test_kmeans_pipeline_is_deterministic(con):
    """Same random_state must produce the same cluster assignments and silhouette score --
    Phase 3's evidence files are only trustworthy if the reported numbers are reproducible,
    not an artifact of an unseeded run."""
    cutoffs = [row[0] for row in con.execute(
        "select distinct cutoff_date from mart_customer_features order by 1"
    ).fetchall()]
    assert cutoffs, "No cutoffs found in mart_customer_features."
    df = segment_data.load_snapshot(con, str(cutoffs[-1].date()))
    prep = kmeans.prepare_matrix(df)
    run1 = kmeans.fit_final(prep["X"], k=3, random_state=42)
    run2 = kmeans.fit_final(prep["X"], k=3, random_state=42)
    assert np.array_equal(run1["labels"], run2["labels"])
    assert run1["silhouette"] == run2["silhouette"]
