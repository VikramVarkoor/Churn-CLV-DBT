-- Independently recomputes recency_days straight from stg_online_retail
-- (bypassing int_customer_orders and the mart's own CTEs entirely) and
-- compares it to what mart_customer_features actually stored for this
-- run's cutoff. A mismatch means a feature used data it shouldn't have, or
-- the as-of-cutoff filter was removed/broken somewhere in the chain.
-- A dbt singular test passes when it returns zero rows.

with recomputed as (
    select
        customer_id,
        date_diff(
            'day',
            max(invoice_date),
            cast('{{ var("cutoff_date") }}' as timestamp)
        ) as recomputed_recency_days
    from {{ ref('stg_online_retail') }}
    where invoice_date < cast('{{ var("cutoff_date") }}' as timestamp)
      and invoice not like 'C%'
      and customer_id is not null
    group by customer_id
)

select
    m.customer_id,
    m.recency_days,
    r.recomputed_recency_days
from {{ ref('mart_customer_features') }} m
inner join recomputed r on m.customer_id = r.customer_id
where m.cutoff_date = cast('{{ var("cutoff_date") }}' as timestamp)
  and m.recency_days != r.recomputed_recency_days
