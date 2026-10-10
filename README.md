# Customer Churn, Segmentation, and CLV on a dbt + DuckDB Warehouse

Status: Phases 0-4 done with real results (data audit, design lock, dbt + DuckDB warehouse,
leakage-safe churn model with an out-of-time test, RFM/k-means segmentation, BG/NBD + Gamma-Gamma
CLV with holdout validation, and an LLM summary layer over the segment/churn/CLV numbers with
deterministic verification). This is milestone M1 per the project plan. This README will be
filled in properly during Phase 5; until then it just orients anyone opening the repo early.

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

## Phase 3 headline results

Segmentation (cutoff B, 5224 customers): k-means on log-scaled, standardized RFM lands on 4
segments either way, with or without the 53 flagged wholesalers (silhouette ~0.376, bootstrap-ARI
stability ~0.955, a tight 95% interval). Wholesalers don't change the cluster structure, but they
concentrate revenue: the top segment holds 68.1% of revenue from 16.5% of customers with
wholesalers included, versus 59.9% from 17.9% with them excluded. Full tables in
`docs/evidence/p3_segments.md`.

CLV (BG/NBD + Gamma-Gamma, fit on cutoff A, validated on a real 245-day holdout never used in
fitting): the Gamma-Gamma uncorrelated-frequency-and-spend assumption was checked, not assumed,
and holds on the real data (Pearson correlation 0.061 among repeat customers). The model ranks
customers correctly (predicted and actual both rise monotonically by decile, and the top decile
is close: predicted 10,015 vs actual 9,615 transactions), but is not precise in the middle of the
distribution, and the rank correlations are moderate rather than strong (0.593 transactions, 0.597
spend). This is reported as a usable ranking signal, not a precise forecast. Full numbers in
`docs/evidence/p3_clv_validation.md`.

## Phase 4 headline result

A short, plain-language LLM summary was generated per customer segment (cutoff B, the same
four real segments from Phase 3) from `docs/evidence/segment_stats.json`'s real numbers --
segment size, revenue share, recency, frequency, predicted churn rate, predicted CLV -- with no
new modeling: the churn rate reuses Phase 2's exact LightGBM model and the CLV figure reuses
Phase 3's exact BG/NBD + Gamma-Gamma models, both scored on cutoff B. Every summary was checked
by `python/llm/verify.py` for numbers it shouldn't have, segments it shouldn't mention, and
causal language it shouldn't use (the real run used Groq's `openai/gpt-oss-120b`, after the
originally-planned `llama-3.3-70b-versatile` turned out to already be retired -- see
`BUGLOG.md` entry 7). All 4 of 4 real summaries passed: no unsupported numbers, no unsupported
segment references, no causal language.

That said, passing verification is not the same as being well-written: two of the four
summaries describe `mean_monetary_net` (each customer's total net spend over their observed
history) as "average purchase value," which reads like a single order's size rather than a
lifetime total -- a real, numerically-correct-but-misleadingly-described result, not a verifier
miss, since describing what a number means isn't one of the three things the verifier checks.
Full summaries and this finding's full writeup are in `docs/evidence/p4_llm_summaries.md`;
real segment numbers are in `docs/evidence/segment_stats.json`; the sandbox testing (synthetic
fixture) that proved the pipeline and the verifier before this real run is in
`docs/evidence/p4_sandbox_test_log.txt`.

To reproduce this phase yourself: build the warehouse for all three cutoffs
(`dbt build --profiles-dir . --vars '{cutoff_date: "..."}'` for `2010-12-01`, `2011-03-01`,
`2011-09-01`, or `make build`), run `python3 python/build_segment_stats.py`, get a Groq API key
at [console.groq.com/keys](https://console.groq.com/keys) and `export GROQ_API_KEY=...`, then
run `python3 python/run_phase4.py`. `python3 python/run_phase4.py --stub` runs the same
pipeline offline with no API key and deliberately templated/broken output, for testing the
pipeline itself rather than producing real evidence.

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
