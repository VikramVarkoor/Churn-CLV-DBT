"""
Phase 0 data audit for the UCI Online Retail II dataset.

Run from the repo root:
    python3 python/audit.py

Reads data/raw/online_retail_II.xlsx (both sheets), combines them, writes a
combined parquet copy to data/raw/ for later use, and prints every count
listed in section 3 of the project brief. Also writes the same output to
docs/audit_raw_output.txt so it can be pasted or attached elsewhere.

No numbers are invented here. If a step cannot run (missing file, missing
column), the script stops with a clear error instead of guessing.
"""

import sys
from pathlib import Path

import duckdb
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_XLSX = REPO_ROOT / "data" / "raw" / "online_retail_II.xlsx"
COMBINED_PARQUET = REPO_ROOT / "data" / "raw" / "online_retail_ii_combined.parquet"
OUTPUT_LOG = REPO_ROOT / "docs" / "audit_raw_output.txt"

# Known non-product StockCodes seen in this dataset in public documentation.
# Logged explicitly so every exclusion is visible, per the brief's rule that
# no exclusion is silent.
KNOWN_NON_PRODUCT_CODES = ["POST", "DOT", "M", "BANK CHARGES", "ADJUST", "C2", "AMAZONFEE", "CRUK"]


def log(lines, text):
    print(text)
    lines.append(text)


def normalize_columns(df):
    """Map the two known UCI column-naming variants onto one schema."""
    rename_map = {}
    cols = {c.strip().lower(): c for c in df.columns}

    def pick(*candidates):
        for cand in candidates:
            if cand in cols:
                return cols[cand]
        return None

    invoice_col = pick("invoice", "invoiceno")
    stockcode_col = pick("stockcode")
    description_col = pick("description")
    quantity_col = pick("quantity")
    invoicedate_col = pick("invoicedate")
    price_col = pick("price", "unitprice")
    customerid_col = pick("customer id", "customerid")
    country_col = pick("country")

    required = {
        "Invoice": invoice_col,
        "StockCode": stockcode_col,
        "Description": description_col,
        "Quantity": quantity_col,
        "InvoiceDate": invoicedate_col,
        "Price": price_col,
        "CustomerID": customerid_col,
        "Country": country_col,
    }
    missing = [k for k, v in required.items() if v is None]
    if missing:
        raise SystemExit(
            f"ERROR: could not find expected columns in the source file: {missing}. "
            f"Columns found were: {list(df.columns)}. Fix the column mapping in "
            f"normalize_columns() before re-running."
        )

    for target, source in required.items():
        rename_map[source] = target

    return df.rename(columns=rename_map)[list(required.keys())]


def main():
    lines = []

    if not RAW_XLSX.exists():
        raise SystemExit(
            f"ERROR: {RAW_XLSX} not found. See data/raw/README.md for how to get the file "
            f"there before running this script."
        )

    log(lines, f"Reading {RAW_XLSX} ...")
    sheets = pd.read_excel(RAW_XLSX, sheet_name=None)
    log(lines, f"Sheets found: {list(sheets.keys())}")

    frames = []
    for name, df in sheets.items():
        df = normalize_columns(df)
        df["SourceSheet"] = name
        frames.append(df)
    data = pd.concat(frames, ignore_index=True)

    # Force consistent dtypes. Each sheet can get read with a different inferred
    # dtype for the same column (e.g. Invoice as int64 in one sheet because it
    # happens to contain no 'C' prefixed values, object in the other), which
    # breaks the later parquet write. Pin types explicitly instead of trusting
    # per-sheet inference.
    data["Invoice"] = data["Invoice"].astype(str)
    data["StockCode"] = data["StockCode"].astype(str)
    data["Description"] = data["Description"].astype(str)
    data["Country"] = data["Country"].astype(str)
    data["Quantity"] = pd.to_numeric(data["Quantity"], errors="coerce")
    data["Price"] = pd.to_numeric(data["Price"], errors="coerce")
    data["CustomerID"] = pd.to_numeric(data["CustomerID"], errors="coerce").astype("Int64")
    data["InvoiceDate"] = pd.to_datetime(data["InvoiceDate"])

    COMBINED_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    data.to_parquet(COMBINED_PARQUET, index=False)
    log(lines, f"Combined {len(data):,} rows across {len(sheets)} sheet(s) -> {COMBINED_PARQUET}")

    con = duckdb.connect()
    con.register("retail", data)

    log(lines, "\n=== 1. Totals ===")
    total_rows = con.sql("SELECT COUNT(*) FROM retail").fetchone()[0]
    date_range = con.sql("SELECT MIN(InvoiceDate), MAX(InvoiceDate) FROM retail").fetchone()
    distinct_customers = con.sql(
        "SELECT COUNT(DISTINCT CustomerID) FROM retail WHERE CustomerID IS NOT NULL"
    ).fetchone()[0]
    log(lines, f"Total rows: {total_rows:,}")
    log(lines, f"Date range: {date_range[0]} to {date_range[1]}")
    log(lines, f"Distinct customers (non-null Customer ID): {distinct_customers:,}")

    log(lines, "\n=== 2. Missing Customer ID ===")
    missing_cust = con.sql("SELECT COUNT(*) FROM retail WHERE CustomerID IS NULL").fetchone()[0]
    pct_missing = missing_cust / total_rows * 100
    log(lines, f"Rows with missing Customer ID: {missing_cust:,} ({pct_missing:.2f}% of all rows)")

    log(lines, "\n=== 3. Cancellation invoices ===")
    cancel_rows = con.sql(
        "SELECT COUNT(*) FROM retail WHERE Invoice LIKE 'C%'"
    ).fetchone()[0]
    cancel_invoices = con.sql(
        "SELECT COUNT(DISTINCT Invoice) FROM retail WHERE Invoice LIKE 'C%'"
    ).fetchone()[0]
    purchase_qty_value = con.sql(
        "SELECT SUM(Quantity), SUM(Quantity * Price) FROM retail WHERE Invoice NOT LIKE 'C%'"
    ).fetchone()
    cancel_qty_value = con.sql(
        "SELECT SUM(Quantity), SUM(Quantity * Price) FROM retail WHERE Invoice LIKE 'C%'"
    ).fetchone()
    log(lines, f"Cancellation rows (Invoice starts with 'C'): {cancel_rows:,}")
    log(lines, f"Distinct cancellation invoices: {cancel_invoices:,}")
    log(lines, f"Purchase rows: total quantity {purchase_qty_value[0]:,.0f}, total value {purchase_qty_value[1]:,.2f}")
    log(lines, f"Cancellation rows: total quantity {cancel_qty_value[0]:,.0f}, total value {cancel_qty_value[1]:,.2f}")
    net_qty = (purchase_qty_value[0] or 0) + (cancel_qty_value[0] or 0)
    net_value = (purchase_qty_value[1] or 0) + (cancel_qty_value[1] or 0)
    log(lines, f"Net quantity after cancellations: {net_qty:,.0f}")
    log(lines, f"Net value after cancellations: {net_value:,.2f}")

    log(lines, "\n=== 4. Exclusion candidates (each counted independently, not cumulatively) ===")
    nonpos_qty = con.sql("SELECT COUNT(*) FROM retail WHERE Quantity <= 0").fetchone()[0]
    nonpos_price = con.sql("SELECT COUNT(*) FROM retail WHERE Price <= 0").fetchone()[0]
    dupe_rows = con.sql(
        "SELECT COUNT(*) - COUNT(DISTINCT (Invoice, StockCode, Description, Quantity, InvoiceDate, Price, CustomerID, Country)) FROM retail"
    ).fetchone()[0]
    log(lines, f"Rows with Quantity <= 0: {nonpos_qty:,}")
    log(lines, f"Rows with Price <= 0: {nonpos_price:,}")
    log(lines, f"Exact duplicate rows (beyond the first occurrence): {dupe_rows:,}")

    log(lines, "\nNon-product StockCode counts (checked against the known list; report any others seen):")
    codes_placeholder = ",".join(f"'{c}'" for c in KNOWN_NON_PRODUCT_CODES)
    known_code_counts = con.sql(
        f"SELECT StockCode, COUNT(*) AS n FROM retail WHERE StockCode IN ({codes_placeholder}) "
        f"GROUP BY StockCode ORDER BY n DESC"
    ).fetchdf()
    if known_code_counts.empty:
        log(lines, "  (none of the known non-product codes appear in this file)")
    else:
        for _, row in known_code_counts.iterrows():
            log(lines, f"  {row['StockCode']}: {row['n']:,}")

    log(lines, "\nTop 20 StockCodes that are non-numeric (candidates for codes not in the known list above):")
    nonnumeric = con.sql(
        "SELECT StockCode, COUNT(*) AS n FROM retail "
        "WHERE StockCode NOT SIMILAR TO '[0-9]+[A-Za-z]*' "
        "GROUP BY StockCode ORDER BY n DESC LIMIT 20"
    ).fetchdf()
    for _, row in nonnumeric.iterrows():
        log(lines, f"  {row['StockCode']}: {row['n']:,}")

    log(lines, "\n=== 5. Order-size distribution and wholesaler candidates ===")
    basket_stats = con.sql(
        "SELECT Invoice, SUM(Quantity) AS total_qty, SUM(Quantity * Price) AS total_value "
        "FROM retail WHERE Invoice NOT LIKE 'C%' GROUP BY Invoice"
    ).fetchdf()
    log(lines, "Order quantity distribution (per invoice, purchases only):")
    log(lines, basket_stats["total_qty"].describe(percentiles=[0.5, 0.9, 0.95, 0.99]).to_string())
    log(lines, "\nOrder value distribution (per invoice, purchases only):")
    log(lines, basket_stats["total_value"].describe(percentiles=[0.5, 0.9, 0.95, 0.99]).to_string())

    customer_qty = con.sql(
        "SELECT CustomerID, SUM(Quantity) AS total_qty, COUNT(DISTINCT Invoice) AS n_invoices "
        "FROM retail WHERE Invoice NOT LIKE 'C%' AND CustomerID IS NOT NULL "
        "GROUP BY CustomerID ORDER BY total_qty DESC LIMIT 20"
    ).fetchdf()
    log(lines, "\nTop 20 customers by total purchased quantity (wholesaler candidates, eyeball these):")
    log(lines, customer_qty.to_string(index=False))

    OUTPUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_LOG.write_text("\n".join(lines) + "\n")
    print(f"\nFull output written to {OUTPUT_LOG}")


if __name__ == "__main__":
    sys.exit(main())
