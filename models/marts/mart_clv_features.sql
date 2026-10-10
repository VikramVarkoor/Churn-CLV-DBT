-- BG/NBD + Gamma-Gamma input features as of {{ var('cutoff_date') }}, using history strictly
-- before the cutoff (invoice_date < cutoff_date, never on or after it -- same leakage rule as
-- mart_customer_features, checked independently by tests/test_phase3_leakage.py).
--
-- This is deliberately a SEPARATE mart from mart_customer_features, not a reuse of its
-- recency/frequency columns. BG/NBD and Gamma-Gamma need a different convention (see
-- docs/design.md, "Phase 3 implementation decisions"):
--   * frequency_repeat: number of REPEAT valid purchase orders (the first order excluded).
--   * t_days: time from the customer's first purchase to the cutoff (their "age").
--   * recency_cal_days: time from the customer's first purchase to their LAST purchase within
--     the calibration history (not days-since-last-purchase, which is what mart_customer_
--     features' recency_days means).
--   * monetary_value: average order value of the repeat orders only (the first order excluded,
--     cancellations excluded entirely -- Gamma-Gamma needs strictly positive transaction
--     values, and a cancellation is a reversal, not a transaction being modeled).
--
-- Population is the same rule as mart_customer_features: at least one valid (non-cancellation)
-- purchase before the cutoff. A single-purchase customer has frequency_repeat = 0 and a null
-- monetary_value (undefined with no repeat orders) -- expected and handled downstream: BG/NBD
-- fits on everyone, Gamma-Gamma only fits on the frequency_repeat >= 1 subset, same as the
-- standard BG/NBD + Gamma-Gamma workflow.

{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key=['customer_id', 'cutoff_date']) }}

with history as (
    select *
    from {{ ref('int_customer_orders') }}
    where invoice_date < cast('{{ var("cutoff_date") }}' as timestamp)
      and customer_id is not null
),

valid_orders as (
    select *
    from history
    where not is_cancellation
),

population as (
    select distinct customer_id
    from valid_orders
),

order_ranks as (
    select
        customer_id,
        invoice,
        invoice_date,
        order_value,
        row_number() over (partition by customer_id order by invoice_date, invoice) as order_rank
    from valid_orders
),

agg as (
    select
        customer_id,
        min(invoice_date) as first_purchase_date,
        max(invoice_date) as last_purchase_date,
        count(*) - 1 as frequency_repeat
    from order_ranks
    group by customer_id
),

repeat_monetary as (
    -- Average order value of every order except the first one (order_rank > 1).
    select
        customer_id,
        avg(order_value) as monetary_value
    from order_ranks
    where order_rank > 1
    group by customer_id
)

select
    a.customer_id,
    cast('{{ var("cutoff_date") }}' as timestamp) as cutoff_date,
    a.frequency_repeat,
    date_diff('day', a.first_purchase_date, cast('{{ var("cutoff_date") }}' as timestamp)) as t_days,
    date_diff('day', a.first_purchase_date, a.last_purchase_date)                          as recency_cal_days,
    rm.monetary_value
from agg a
inner join population p on a.customer_id = p.customer_id
left join repeat_monetary rm on a.customer_id = rm.customer_id
