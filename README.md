# Customer Churn, Segmentation, and CLV on a dbt + DuckDB Warehouse

Status: Phases 0-1 done (data audit, design lock, dbt + DuckDB warehouse). Phase 2 (churn model)
in progress. This README will be filled in properly during Phase 5 per the project plan; until
then it just orients anyone opening the repo early.

## What this is

A portfolio project built on a public dataset (UCI Online Retail II, CC BY 4.0, a UK online
retailer, Dec 2009 to Dec 2011). It is not company data and not production work. The goal is to
demonstrate, with real evidence, a dbt + DuckDB warehouse, leakage-safe churn modeling with an
out-of-time test, customer segmentation, CLV estimation, and an LLM summary layer with
deterministic verification.

See `data/raw/README.md` for how the raw file is obtained (not committed to this repo), and
`docs/` for the audit and design documents as they are written.

## Reproduction

Not yet documented. This section is filled in during Phase 5 with the real `make all` steps.
