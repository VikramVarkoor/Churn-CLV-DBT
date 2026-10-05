-- Raw, lightly-typed pass-through from the combined parquet file written by
-- python/audit.py. Deliberately NOT deduplicated and NOT filtered here: this
-- model and its tests in _staging_raw.yml exist to show what the real data
-- looks like before any cleaning decision is applied. Per the brief's Phase 1
-- ground rule, the tests on THIS model are run first and their failures are
-- recorded in BUGLOG.md, not fixed by editing this model.

with source as (
    select *
    from read_parquet('{{ var("raw_parquet_path") }}')
)

select
    cast(Invoice as varchar)                       as invoice,
    cast(StockCode as varchar)                     as stock_code,
    cast(Description as varchar)                   as description,
    cast(Quantity as bigint)                       as quantity,
    cast(InvoiceDate as timestamp)                 as invoice_date,
    cast(Price as double)                          as price,
    cast(CustomerID as bigint)                     as customer_id,
    cast(Country as varchar)                       as country,
    -- Surrogate key over every raw column, used only to test exact-duplicate
    -- rows (see docs/audit.md section 4: 34,335 rows are exact duplicates).
    -- A real repeat of all 8 fields including the same minute-level
    -- timestamp is treated as export duplication, not two real events.
    md5(
        concat_ws('|',
            cast(Invoice as varchar),
            cast(StockCode as varchar),
            cast(Description as varchar),
            cast(Quantity as varchar),
            cast(InvoiceDate as varchar),
            cast(Price as varchar),
            cast(CustomerID as varchar),
            cast(Country as varchar)
        )
    ) as row_key
from source
