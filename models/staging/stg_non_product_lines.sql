-- Everything routed out of stg_online_retail for having a non-product
-- StockCode (doesn't match ^[0-9]+[A-Za-z]*$), kept here instead of dropped
-- so no exclusion is silent. Price is NOT filtered here -- these are
-- non-merchandise lines (postage, fees, write-offs, test rows, etc.) and
-- their price, including 0, is part of what they are.

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

select
    *,
    case stock_code
        when 'POST' then 'Postage'
        when 'DOT' then 'Dotcom postage'
        when 'M' then 'Manual line item'
        when 'C2' then 'Carriage'
        when 'BANK CHARGES' then 'Bank charges'
        when 'ADJUST' then 'Manual adjustment'
        when 'AMAZONFEE' then 'Amazon selling fee'
        when 'CRUK' then 'Cancer Research UK donation'
        when 'D' then 'Discount line'
        when 'S' then 'Samples'
        when 'PADS' then 'Unconfirmed -- needs Description review, see docs/audit.md'
        when 'TEST001' then 'Literal QA test row'
        else
            case
                when stock_code like 'gift\_%' escape '\' then 'Gift card code'
                when stock_code like 'DCGS%' then 'Unconfirmed -- needs Description review, see docs/audit.md'
                else 'Other non-numeric StockCode, not yet catalogued -- see docs/audit.md'
            end
    end as non_product_reason
from deduped_once
where not regexp_matches(stock_code, '^[0-9]+[A-Za-z]*$')
