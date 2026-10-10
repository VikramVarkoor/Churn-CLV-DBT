-- Independently recomputes mart_clv_features' three numeric columns (frequency_repeat, t_days,
-- recency_cal_days) straight from stg_online_retail, bypassing int_customer_orders and the
-- mart's own CTEs entirely, and compares them to what the mart actually stored for this run's
-- cutoff. A mismatch means a CLV feature used data on or after the cutoff, or the as-of-cutoff
-- filter was removed/broken. Passes when it returns zero rows.

with valid_lines as (
    select *
    from {{ ref('stg_online_retail') }}
    where invoice_date < cast('{{ var("cutoff_date") }}' as timestamp)
      and invoice not like 'C%'
      and customer_id is not null
),

valid_orders as (
    select
        customer_id,
        invoice,
        min(invoice_date) as invoice_date
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

recomputed as (
    select
        customer_id,
        count(*) - 1 as recomputed_frequency_repeat,
        date_diff('day', min(invoice_date), cast('{{ var("cutoff_date") }}' as timestamp)) as recomputed_t_days,
        date_diff('day', min(invoice_date), max(invoice_date)) as recomputed_recency_cal_days
    from ranked
    group by customer_id
)

select
    m.customer_id,
    m.frequency_repeat,
    r.recomputed_frequency_repeat,
    m.t_days,
    r.recomputed_t_days,
    m.recency_cal_days,
    r.recomputed_recency_cal_days
from {{ ref('mart_clv_features') }} m
inner join recomputed r on m.customer_id = r.customer_id
where m.cutoff_date = cast('{{ var("cutoff_date") }}' as timestamp)
  and (
    m.frequency_repeat != r.recomputed_frequency_repeat
    or m.t_days != r.recomputed_t_days
    or m.recency_cal_days != r.recomputed_recency_cal_days
  )
