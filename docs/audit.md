# Phase 0 data audit

Source: UCI Online Retail II (`data/raw/online_retail_II.xlsx`, downloaded by Vikram from
https://archive.ics.uci.edu/dataset/502/online+retail+ii, CC BY 4.0). All numbers below come from
a real run of `python/audit.py` against the full file on Vikram's machine (arm64 Mac, Python
3.14.7) on 2026-10-05. Nothing here is estimated.

## 1. Totals

- Total rows: **1,067,371**
- Date range: **2009-12-01 07:45:00** to **2011-12-09 12:50:00**
- Distinct customers (non-null Customer ID): **5,942**

## 2. Missing Customer ID

- Rows with missing Customer ID: **243,007 (22.77% of all rows)**

This matches the brief's own recollection ("somewhere near a fifth of rows"), slightly higher in
practice. These rows cannot be attributed to a customer and are excluded from customer-level
features by definition (no Customer ID to key on), but stay in the staging layer so revenue
reconciles against the raw file.

## 3. Cancellations

- Cancellation rows (Invoice starts with `C`): **19,494**
- Distinct cancellation invoices: **8,292**
- Purchase rows: total quantity 11,099,484, total value 20,813,918.43
- Cancellation rows: total quantity -490,992, total value -1,526,667.86
- Net quantity after cancellations: **10,608,492**
- Net value after cancellations: **19,287,250.57**

Cancellations are real customer behavior (a return), not data quality noise. The design treats
them as negative line items that net against a customer's purchases rather than dropping them.

## 4. Exclusion candidates (each counted independently, not cumulatively)

| Check | Row count |
|---|---|
| Quantity <= 0 | 22,950 |
| Price <= 0 | 6,207 |
| Exact duplicate rows (beyond the first occurrence) | 34,335 |

Breakdown:
- Quantity = 0: 0 rows. Quantity < 0: 22,950 rows (all of them; there are no exact-zero quantity rows in this file).
- Price = 0: 6,202 rows. Price < 0: 5 rows.

### Known non-product StockCodes found

| StockCode | Row count | What it is |
|---|---|---|
| POST | 2,122 | Postage |
| DOT | 1,446 | Dotcom postage |
| M | 1,421 | Manual line item |
| C2 | 282 | Carriage |
| BANK CHARGES | 102 | Bank charges |
| ADJUST | 67 | Manual adjustment |
| AMAZONFEE | 43 | Amazon selling fee |
| CRUK | 16 | Cancer Research UK donation |

### Other non-numeric StockCodes found (not on the original known list, scanned for separately)

| StockCode | Row count | Note |
|---|---|---|
| D | 177 | Discount line |
| S | 104 | Samples |
| DCGS0058, DCGS0076, DCGS0003 (+ more under DCGS*) | 31 / 15 / 14 | Unclear from code alone, needs a Description check before Phase 1 |
| gift_0001_10/20/30 | 16/29/29 | Gift card codes |
| PADS | 19 | Needs a Description check |
| **TEST001** | 15 | Literal test/QA entries in the raw data |

None of this list was invented; it's the output of a catch-all "non-numeric StockCode" scan, so
anything not already in the known list above surfaced on its own. DCGS* and PADS need their
Description text checked before Phase 1 decides whether they're real merchandise or more
admin codes; everything else above is unambiguous.

### Duplicate rows

34,335 rows (3.2% of the file) are exact duplicates (identical Invoice, StockCode, Description,
Quantity, InvoiceDate, Price, CustomerID, Country) beyond the first occurrence. Given how unlikely
it is for two genuinely separate transactions to match on every one of those fields including the
same timestamp, these are treated as export/logging duplication, not real repeat events.

## 5. Order-size distribution and wholesaler candidates

Per-invoice totals, purchase invoices only (`Invoice NOT LIKE 'C%'`), n = 45,336 invoices:

| Percentile | Quantity | Value |
|---|---|---|
| min | -9,600 | -53,594.36 |
| 50% | 127 | 263.54 |
| 90% | 496 | 871.37 |
| 95% | 758 | 1,410.69 |
| 99% | 2,232 | 4,232.23 |
| max | 87,167 | 168,469.60 |

Top customers by total purchased quantity (purchase invoices only):

| CustomerID | Total quantity | Invoices |
|---|---|---|
| 14646 | 367,833 | 152 |
| 13902 | 220,600 | 5 |
| 13694 | 189,205 | 143 |
| 18102 | 188,340 | 145 |
| 14156 | 165,992 | 156 |
| 14911 | 150,237 | 398 |

These customers sit far outside the rest of the distribution (99th percentile single-invoice
quantity is 2,232; customer 14646 alone moved 367,833 units) and are the wholesaler candidates
referenced in design.md.

## 6. Anomaly found during the audit: unflagged write-off entries

The negative minimum in the order-size distribution above (-9,600 quantity, -53,594.36 value) led
to a direct check. Finding:

- **3,393 non-cancellation invoices (3,457 rows)** have a negative total quantity despite not
  being flagged as cancellations (no `C` prefix on the invoice number).
- Example (the single worst row): Invoice 556691, StockCode 23005, Description
  *"printing smudges/thrown away"*, Quantity -9,600, Price 0.00, CustomerID null.
- Of those 3,457 rows: **0 have Price > 0**, and **0 have a non-null CustomerID**.

Conclusion: these are warehouse stock write-offs (damaged/lost inventory), not customer returns,
and the UK retailer's data entry process didn't give them a `C`-prefixed invoice number the way
real cancellations get. Because Price is always 0 on these rows, they don't distort revenue
totals, but they would badly distort any quantity-based feature (units purchased, order size) if
left in. Because every one of them has no Customer ID attached, a `Price <= 0` exclusion rule
removes all of them without touching any real customer signal, confirmed directly rather than
assumed.

This is the kind of thing Phase 0 audits exist to catch before it quietly inflates or corrupts a
model result later. Logged here and in BUGLOG.md will get the full writeup once Phase 1 is done.
