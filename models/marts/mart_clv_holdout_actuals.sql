-- Actual holdout-period outcomes for CLV validation, as of {{ var('cutoff_date') }}: real
-- transaction count and real net spend in [cutoff_date, cutoff_date + {{ var('clv_holdout_days') }}
-- days). This is evidence for validation, never an input to fitting -- the CLV models in
-- python/clv/ never see this mart. See docs/design.md's "Calibration cutoff and holdout window"
-- section for why 245 days and why it stays inside the real observed date range.
--
-- Population is the same customers present in mart_clv_features for this cutoff, so every
-- predicted customer has a (possibly zero) actual outcome to compare against -- a customer who
-- churns outright in the holdout window is a real, valid data point (0 transactions, 0 spend),
-- not something to exclude.

{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key=['customer_id', 'cutoff_date']) }}

with population as (
    select customer_id
    from {{ ref('mart_clv_features') }}
    where cutoff_date = cast('{{ var("cutoff_date") }}' as timestamp)
),

holdout_orders as (
    select
        customer_id,
        invoice,
        order_value
    from {{ ref('int_customer_orders') }}
    where not is_cancellation
      and customer_id is not null
      and invoice_date >= cast('{{ var("cutoff_date") }}' as timestamp)
      and invoice_date <  cast('{{ var("cutoff_date") }}' as timestamp) + interval '{{ var("clv_holdout_days") }} days'
),

agg as (
    select
        customer_id,
        count(distinct invoice) as actual_transactions,
        sum(order_value)        as actual_spend
    from holdout_orders
    group by customer_id
)

select
    p.customer_id,
    cast('{{ var("cutoff_date") }}' as timestamp) as cutoff_date,
    coalesce(a.actual_transactions, 0) as actual_transactions,
    coalesce(a.actual_spend, 0.0)      as actual_spend
from population p
left join agg a on p.customer_id = a.customer_id
