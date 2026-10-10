# Customer Churn, Segmentation, and CLV on a dbt + DuckDB Warehouse

Status: Phases 0-3 done with real results (data audit, design lock, dbt + DuckDB warehouse,
leakage-safe churn model with an out-of-time test, RFM/k-means segmentation, BG/NBD + Gamma-Gamma
CLV with holdout validation) -- this is milestone M1 per the project plan. Phase 4 (an LLM
summary layer over the segment/churn/CLV numbers, with deterministic verification) is built and
sandbox-tested against a synthetic fixture, but its real run -- against the real warehouse and a
real Groq API call -- hasn't happened yet; see "Phase 4: live run instructions" below. This README
will be filled in properly during Phase 5; until then it just orients anyone opening the repo
early.

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

## Phase 4: live run instructions

Phase 4 adds a short, plain-language LLM summary per customer segment, built strictly from the
real numbers in `docs/evidence/segment_stats.json` (segment size, revenue share, recency,
frequency, predicted churn rate, predicted CLV -- no new modeling; this reuses Phase 2's churn
model and Phase 3's CLV/segmentation models exactly as already reported). Every summary is then
checked by `python/llm/verify.py` for numbers it shouldn't have, segments it shouldn't mention,
and causal language it shouldn't use. The code is built and proven against a synthetic fixture
(`docs/evidence/p4_sandbox_test_log.txt`), but the real numbers and the real LLM calls are still
pending. To run it for real:

1. Build the warehouse for all three cutoffs if you haven't already (same requirement as Phases
   2 and 3): the three `dbt build --profiles-dir . --vars '{cutoff_date: "..."}'` calls (use
   `2010-12-01`, `2011-03-01`, `2011-09-01`), or `make build` if `make` isn't hitting the Xcode
   license wall for you.
2. Run `python3 python/build_segment_stats.py`. This writes
   `docs/evidence/segment_stats.json` with real per-segment numbers (takes a minute or two --
   it refits the BG/NBD + Gamma-Gamma models, same as Phase 3).
3. Get a Groq API key:
   - Go to [console.groq.com](https://console.groq.com) and sign up or log in.
   - Go to [console.groq.com/keys](https://console.groq.com/keys) and click "Create API Key".
     Groq's free tier is generally usable without a credit card, but confirm that at sign-up
     since terms can change.
   - Copy the key immediately -- you only see the full value once.
4. In your terminal: `export GROQ_API_KEY=gsk_...` (your real key). This only lasts for the
   current terminal session; export it again in a new terminal, or add it to your shell
   profile (`~/.zshrc` on macOS) if you want it to persist.
5. Run `python3 python/run_phase4.py` (no `--stub`). This calls the real Groq API once per
   segment, writes `docs/evidence/p4_llm_summaries.md` (the readable report) and
   `docs/evidence/p4_llm_raw.json` (model name, exact prompt, and date for every call), and
   prints how many summaries passed verification.
6. Send me the terminal output (or the two files) so it gets logged as real evidence and
   committed.

Optional: `python3 python/run_phase4.py --stub` runs the identical pipeline offline with no API
key, in case you want to see it work before spending a real call. Its output uses templated
placeholder text and is built to deliberately fail one segment on purpose (to prove the
verifier's failure path actually fires) -- it is not real evidence and shouldn't be committed.

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
