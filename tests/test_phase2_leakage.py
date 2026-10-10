"""
Phase 2's own pytest leakage checks, per the brief: "pytest checks that no feature uses data
on or after the cutoff and that labels are built from the correct window." These are Python-side,
independent of dbt entirely -- they open the real warehouse directly and recompute recency and
the churn label straight from stg_online_retail, bypassing int_customer_orders and the marts'
own CTEs, then compare. This mirrors tests/no_feature_leakage.sql and tests/no_label_leakage.sql,
but as a second, independent implementation in a different language/tool, not a restatement of
the same SQL -- the point is defense in depth, not duplicate coverage.

Requires a built warehouse (data/warehouse.duckdb) with at least one cutoff already run via
`dbt build --vars '{cutoff_date: "..."}'`. Runs against whatever cutoffs are actually present,
so it checks real data when pointed at the real warehouse, and the sandbox's synthetic fixture
when run there (see docs/evidence/p2_sandbox_test_log.txt).
"""

from __future__ import annotations

import duckdb
import pytest

DB_PATH = "data/warehouse.duckdb"


@pytest.fixture(scope="module")
def con():
    connection = duckdb.connect(DB_PATH, read_only=True)
    yield connection
    connection.close()


def _cutoffs(con) -> list:
    return [row[0] for row in con.execute(
        "select distinct cutoff_date from mart_customer_features order by 1"
    ).fetchall()]


def test_cutoffs_exist(con):
    cutoffs = _cutoffs(con)
    assert cutoffs, (
        "No cutoffs found in mart_customer_features. Run `dbt build --profiles-dir . "
        "--vars '{cutoff_date: \"...\"}'` for at least one cutoff before running these tests."
    )


def test_recency_matches_independent_recomputation(con):
    """
    For every cutoff present, recomputes recency_days directly from stg_online_retail
    (max non-cancellation invoice_date before the cutoff, independent of
    int_customer_orders / mart_customer_features' own CTEs) and checks it matches exactly
    what the mart stored.
    """
    for cutoff in _cutoffs(con):
        mismatches = con.execute(
            """
            with independent as (
                select
                    customer_id,
                    date_diff('day', max(invoice_date), cast(? as timestamp)) as recency_days_independent
                from stg_online_retail
                where invoice_date < cast(? as timestamp)
                  and customer_id is not null
                  and invoice not like 'C%'
                group by customer_id
            )
            select count(*)
            from mart_customer_features f
            inner join independent i on f.customer_id = i.customer_id
            where f.cutoff_date = cast(? as timestamp)
              and f.recency_days != i.recency_days_independent
            """,
            [cutoff, cutoff, cutoff],
        ).fetchone()[0]
        assert mismatches == 0, (
            f"recency_days mismatch (possible leakage) at cutoff={cutoff}: {mismatches} rows"
        )


def test_churn_label_matches_independent_recomputation(con):
    """
    For every cutoff present, recomputes the churned label directly from stg_online_retail
    using the exact [cutoff, cutoff + 90 days) window, independent of mart_churn_labels'
    own logic, and checks it matches exactly.
    """
    for cutoff in _cutoffs(con):
        mismatches = con.execute(
            """
            with window_activity as (
                select distinct customer_id
                from stg_online_retail
                where invoice_date >= cast(? as timestamp)
                  and invoice_date < cast(? as timestamp) + interval '90 days'
                  and customer_id is not null
                  and invoice not like 'C%'
            ),
            independent as (
                select
                    f.customer_id,
                    case when w.customer_id is null then 1 else 0 end as churned_independent
                from mart_customer_features f
                left join window_activity w on f.customer_id = w.customer_id
                where f.cutoff_date = cast(? as timestamp)
            )
            select count(*)
            from mart_churn_labels l
            inner join independent i on l.customer_id = i.customer_id
            where l.cutoff_date = cast(? as timestamp)
              and l.churned != i.churned_independent
            """,
            [cutoff, cutoff, cutoff, cutoff],
        ).fetchone()[0]
        assert mismatches == 0, (
            f"churned label mismatch (possible leakage) at cutoff={cutoff}: {mismatches} rows"
        )


def test_no_unexpected_nulls_in_model_inputs(con):
    """Sanity check, not a leakage test: columns the Phase 2 models read directly must
    never be null for a population member."""
    checks = [
        ("mart_customer_features", ["customer_id", "cutoff_date", "recency_days", "frequency",
                                     "monetary_net", "is_wholesaler"]),
        ("mart_churn_labels", ["customer_id", "cutoff_date", "churned"]),
    ]
    for table, cols in checks:
        for col in cols:
            n_null = con.execute(f"select count(*) from {table} where {col} is null").fetchone()[0]
            assert n_null == 0, f"{table}.{col} has {n_null} unexpected nulls"
