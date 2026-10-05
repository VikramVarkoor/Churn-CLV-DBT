-- Order-level (one row per Invoice) rollup of the cleaned merchandise
-- lines. Not filtered by any cutoff -- that happens downstream in the
-- marts, which is what lets the same SQL serve every cutoff.

select
    invoice,
    customer_id,
    -- An invoice can in principle have more than one Country value logged
    -- across its lines (data entry inconsistency); take the first seen
    -- rather than silently picking an arbitrary one via a bare MAX/MIN.
    arg_min(country, stock_code) as country,
    min(invoice_date) as invoice_date,
    invoice like 'C%' as is_cancellation,
    sum(quantity) as order_quantity,
    sum(quantity * price) as order_value,
    count(distinct stock_code) as distinct_products
from {{ ref('stg_online_retail') }}
group by invoice, customer_id, invoice like 'C%'
