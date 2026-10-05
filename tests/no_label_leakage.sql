-- Independently recomputes the churn label straight from stg_online_retail,
-- restricted to exactly the [cutoff, cutoff + label_window_days) window,
-- and compares it to what mart_churn_labels actually stored. A mismatch
-- means the label window in mart_churn_labels.sql doesn't match what it's
-- supposed to compute. Passes when it returns zero rows.

with recomputed as (
    select
        customer_id,
        case
            when count(*) filter (
                where invoice_date >= cast('{{ var("cutoff_date") }}' as timestamp)
                  and invoice_date <  cast('{{ var("cutoff_date") }}' as timestamp) + interval '{{ var("label_window_days") }} days'
                  and invoice not like 'C%'
            ) = 0 then 1
            else 0
        end as recomputed_churned
    from {{ ref('stg_online_retail') }}
    where customer_id in (
        select customer_id
        from {{ ref('mart_churn_labels') }}
        where cutoff_date = cast('{{ var("cutoff_date") }}' as timestamp)
    )
    group by customer_id
)

select
    l.customer_id,
    l.churned,
    r.recomputed_churned
from {{ ref('mart_churn_labels') }} l
inner join recomputed r on l.customer_id = r.customer_id
where l.cutoff_date = cast('{{ var("cutoff_date") }}' as timestamp)
  and l.churned != r.recomputed_churned
