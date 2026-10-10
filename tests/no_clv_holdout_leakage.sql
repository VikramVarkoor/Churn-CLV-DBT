-- Independently recomputes mart_clv_holdout_actuals' transaction count and spend straight from
-- stg_online_retail, restricted to exactly [cutoff, cutoff + clv_holdout_days), and compares to
-- what the mart actually stored. A mismatch means the holdout window doesn't match what it's
-- supposed to compute, which would make the Phase 3 validation numbers meaningless. Passes when
-- it returns zero rows.

with valid_lines as (
    select *
    from {{ ref('stg_online_retail') }}
    where invoice_date >= cast('{{ var("cutoff_date") }}' as timestamp)
      and invoice_date <  cast('{{ var("cutoff_date") }}' as timestamp) + interval '{{ var("clv_holdout_days") }} days'
      and invoice not like 'C%'
      and customer_id is not null
),

valid_orders as (
    select
        customer_id,
        invoice,
        sum(quantity * price) as order_value
    from valid_lines
    group by customer_id, invoice
),

recomputed as (
    select
        customer_id,
        count(distinct invoice) as recomputed_transactions,
        sum(order_value)        as recomputed_spend
    from valid_orders
    group by customer_id
)

select
    h.customer_id,
    h.actual_transactions,
    r.recomputed_transactions,
    h.actual_spend,
    r.recomputed_spend
from {{ ref('mart_clv_holdout_actuals') }} h
inner join recomputed r on h.customer_id = r.customer_id
where h.cutoff_date = cast('{{ var("cutoff_date") }}' as timestamp)
  and (
    h.actual_transactions != r.recomputed_transactions
    or abs(h.actual_spend - r.recomputed_spend) > 0.01
  )
