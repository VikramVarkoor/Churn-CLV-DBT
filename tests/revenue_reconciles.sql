-- Total net revenue in mart_customer_features for this cutoff must match
-- the independently-computed total from stg_online_retail for the exact
-- same population and time window. Passes when it returns zero rows
-- (difference under 1 cent, to allow for floating point rounding).

with mart_total as (
    select sum(monetary_net) as total
    from {{ ref('mart_customer_features') }}
    where cutoff_date = cast('{{ var("cutoff_date") }}' as timestamp)
),

source_total as (
    select sum(quantity * price) as total
    from {{ ref('stg_online_retail') }}
    where invoice_date < cast('{{ var("cutoff_date") }}' as timestamp)
      and customer_id in (
          select customer_id
          from {{ ref('mart_customer_features') }}
          where cutoff_date = cast('{{ var("cutoff_date") }}' as timestamp)
      )
)

select
    m.total as mart_total,
    s.total as source_total,
    abs(m.total - s.total) as difference
from mart_total m, source_total s
where abs(m.total - s.total) > 0.01
