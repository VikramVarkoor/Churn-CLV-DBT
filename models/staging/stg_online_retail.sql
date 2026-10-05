-- Cleaned merchandise lines only. Every exclusion here is one of the three
-- rules fixed in docs/design.md, in the same order:
--   1. exact duplicate rows -> keep first occurrence
--   2. price <= 0 -> dropped (confirmed in the audit to be unpriced
--      write-offs/admin rows, not real customer activity)
--   3. non-product StockCode -> routed to stg_non_product_lines instead
--
-- Cancellations (Invoice starting with 'C') are kept here, not dropped --
-- they're real customer behavior per design.md, carried as negative
-- quantity/value line items.

with deduped as (
    select
        *,
        row_number() over (partition by row_key order by invoice) as rn
    from {{ ref('stg_online_retail_raw') }}
),

deduped_once as (
    select * exclude (rn, row_key)
    from deduped
    where rn = 1
)

select *
from deduped_once
where price > 0
  and regexp_matches(stock_code, '^[0-9]+[A-Za-z]*$')
