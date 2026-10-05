-- Churn label as of {{ var('cutoff_date') }}: 1 if the customer has no
-- valid (non-cancellation) purchase in the {{ var('label_window_days') }}
-- days starting at the cutoff, 0 otherwise. Population is whoever is in
-- mart_customer_features for this same cutoff (defined once, in design.md,
-- not redefined here).
--
-- Incremental on (customer_id, cutoff_date), same as mart_customer_features,
-- so both cutoffs' labels persist in the same table across separate runs.

{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key=['customer_id', 'cutoff_date']) }}

with population as (
    select customer_id
    from {{ ref('mart_customer_features') }}
    where cutoff_date = cast('{{ var("cutoff_date") }}' as timestamp)
),

window_activity as (
    select distinct customer_id
    from {{ ref('int_customer_orders') }}
    where not is_cancellation
      and customer_id is not null
      and invoice_date >= cast('{{ var("cutoff_date") }}' as timestamp)
      and invoice_date <  cast('{{ var("cutoff_date") }}' as timestamp) + interval '{{ var("label_window_days") }} days'
)

select
    p.customer_id,
    cast('{{ var("cutoff_date") }}' as timestamp) as cutoff_date,
    case when w.customer_id is null then 1 else 0 end as churned
from population p
left join window_activity w on p.customer_id = w.customer_id
