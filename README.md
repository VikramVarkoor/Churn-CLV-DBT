# Customer Churn, Segmentation, and CLV on a dbt + DuckDB Warehouse

Status: Phases 0-2 done (data audit, design lock, dbt + DuckDB warehouse, leakage-safe churn
model with an out-of-time test). This README will be filled in properly during Phase 5 per the
project plan; until then it just orients anyone opening the repo early.

## Phase 2 headline result

Neither LightGBM nor logistic regression clearly beats a simple recency-threshold rule at
predicting 90-day churn on this dataset. On test cutoff B, PR-AUC is 0.801 [0.785, 0.816] for the
recency rule, 0.813 [0.798, 0.829] for logistic regression on RFM features, and 0.814 [0.799,
0.830] for LightGBM (95% bootstrap CIs over customers). LightGBM's CI lower bound (0.799) is below
the recency rule's CI upper bound (0.816), so the overlap means this is not a statistically clear
win, and logistic regression and LightGBM are indistinguishable from each other. This is reported
plainly rather than leading with the raw point estimates, per this project's own ground rules. Full
numbers, calibration tables, and the tuning trace are in `docs/evidence/p2_results.md`; a real bug
in the threshold-tuning code (and its fix) is logged in `BUGLOG.md` entry 5.

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
