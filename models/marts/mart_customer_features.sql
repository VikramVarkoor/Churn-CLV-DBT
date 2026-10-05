-- Customer-level features as of {{ var('cutoff_date') }}. Incremental,
-- keyed on (customer_id, cutoff_date): running this with a different
-- --vars cutoff_date adds that cutoff's rows alongside whatever is already
-- persisted for other cutoffs, rather than overwriting them. This is what
-- "features exist for both cutoffs from the same SQL" (Phase 1 acceptance
-- criterion) means in practice -- run this file twice, with cutoff A then
-- cutoff B, and both sets of rows end up in the same table.
--
-- Every feature below is computed only from int_customer_orders rows with
-- invoice_date < cutoff_date. No feature may reference anything on or
-- after the cutoff (see tests/no_feature_leakage.sql, which checks this
-- independently rather than trusting this comment).

{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key=['customer_id', 'cutoff_date']) }}

with history as (
    select *
    from {{ ref('int_customer_orders') }}
    where invoice_date < cast('{{ var("cutoff_date") }}' as timestamp)
      and customer_id is not null
),

population as (
    -- Design.md population rule: at least one valid (non-cancellation)
    -- purchase before the cutoff.
    select distinct customer_id
    from history
    where not is_cancellation
),

agg as (
    select
        customer_id,
        min(invoice_date) filter (where not is_cancellation) as first_purchase_date,
        max(invoice_date) filter (where not is_cancellation) as last_purchase_date,
        count(distinct invoice) filter (where not is_cancellation) as frequency,
        count(distinct invoice) filter (where is_cancellation) as cancel_order_count,
        sum(order_value) as monetary_net,
        sum(order_value) filter (where not is_cancellation) as monetary_gross,
        sum(order_quantity) filter (where not is_cancellation) as total_quantity_purchased
    from history
    group by customer_id
),

distinct_products as (
    select
        customer_id,
        count(distinct stock_code) as distinct_products
    from {{ ref('stg_online_retail') }}
    where invoice_date < cast('{{ var("cutoff_date") }}' as timestamp)
      and customer_id is not null
    group by customer_id
),

purchase_gaps as (
    select
        customer_id,
        date_diff('day', lag(invoice_date) over (partition by customer_id order by invoice_date), invoice_date) as gap_days
    from (
        select distinct customer_id, invoice_date
        from history
        where not is_cancellation
    ) distinct_dates
),

mean_gaps as (
    select
        customer_id,
        avg(gap_days) as mean_days_between_purchases
    from purchase_gaps
    where gap_days is not null
    group by customer_id
),

current_country as (
    select
        customer_id,
        arg_max(country, invoice_date) as country
    from history
    group by customer_id
),

wholesaler_threshold as (
    -- design.md wholesaler rule: top 1% of this cutoff's population by
    -- total purchased quantity. Recomputed per cutoff rather than hardcoded
    -- from the one-time audit figure, so it stays correct as the
    -- population changes between cutoff A and cutoff B.
    select percentile_cont(0.99) within group (order by a.total_quantity_purchased) as p99_quantity
    from agg a
    inner join population p on a.customer_id = p.customer_id
)

select
    a.customer_id,
    cast('{{ var("cutoff_date") }}' as timestamp)                                   as cutoff_date,
    date_diff('day', a.last_purchase_date, cast('{{ var("cutoff_date") }}' as timestamp)) as recency_days,
    a.frequency,
    a.monetary_net,
    a.monetary_gross,
    date_diff('day', a.first_purchase_date, cast('{{ var("cutoff_date") }}' as timestamp)) as tenure_days,
    (a.monetary_gross / nullif(a.frequency, 0))                                     as avg_basket_value,
    coalesce(dp.distinct_products, 0)                                                as distinct_products,
    mg.mean_days_between_purchases,
    (a.cancel_order_count / nullif(a.frequency, 0)::double)                          as cancellation_rate,
    cc.country,
    a.total_quantity_purchased,
    (a.total_quantity_purchased >= wt.p99_quantity)                                  as is_wholesaler
from agg a
inner join population p on a.customer_id = p.customer_id
left join distinct_products dp on a.customer_id = dp.customer_id
left join mean_gaps mg on a.customer_id = mg.customer_id
left join current_country cc on a.customer_id = cc.customer_id
cross join wholesaler_threshold wt
