# Customer Churn, Segmentation, and CLV on a dbt + DuckDB Warehouse

I built a dbt + DuckDB warehouse over a real ~1 million-row e-commerce dataset, with a
leakage-safe churn model evaluated out-of-time, RFM/k-means customer segmentation, BG/NBD +
Gamma-Gamma customer lifetime value, and an LLM summary layer with deterministic verification
on top of all three. Every number in this README comes from a real run I did against the real
dataset, logged in `docs/evidence/`; nothing here is simulated or estimated.

Status: I've finished Phases 0-5, all with real results. Phases 0-3 (data audit, warehouse
build, churn, segmentation, CLV) are milestone M1; Phase 4 adds the LLM summary layer; Phase 5
is this README and the final cleanup pass.

## What this is

This is a portfolio project I built on a public dataset (UCI Online Retail II, CC BY 4.0, a UK
online retailer, December 2009 to December 2011). It's not company data and not production
work. My goal was to demonstrate, with real evidence rather than claims, a dbt + DuckDB
warehouse, leakage-safe churn modeling with an out-of-time test, customer segmentation, CLV
estimation, and an LLM summary layer with deterministic verification -- skills that don't
otherwise show up on a CV built around hardware/embedded work.

Here's the real scale, from running `python/audit.py` against the full file
(`docs/audit.md`): 1,067,371 rows, 5,942 distinct customers, spanning 2009-12-01 to 2011-12-09.
22.77% of rows have no Customer ID, so I exclude them from every customer-level feature by
definition (no ID to key on) -- I keep them in the staging layer so revenue still reconciles
against the raw file, but they can't contribute to churn, segmentation, or CLV. I treat
cancellations (19,494 rows) as real customer behavior, not noise: I net them against a
customer's purchases rather than dropping them.

See `data/raw/README.md` for how I obtained the raw file (I don't commit it to this repo --
it's too large and under a license that doesn't permit redistribution here), and
`docs/design.md` for every implementation decision with my reasoning, written before I wrote
the corresponding code in every case.

## Architecture

```
staging (views)          intermediate (views)       marts (incremental, per cutoff_date)
stg_online_retail_raw -> int_customer_orders    ->  mart_customer_features
stg_non_product_lines                               mart_churn_labels
stg_online_retail                                   mart_clv_features
                                                     mart_clv_holdout_actuals
```

Staging parses the raw parquet and splits out non-product line items (postage, bank charges,
manual adjustments -- I found and listed these in the Phase 0 audit, not guessed at).
Intermediate rebuilds one row per customer order. I parameterized all the marts by a single
`cutoff_date` dbt var and materialized them incrementally (`delete+insert`, keyed on
`customer_id, cutoff_date`), so the same SQL produces a point-in-time-correct snapshot for any
cutoff without duplicating logic per cutoff. I compute every feature in `mart_customer_features`
and `mart_clv_features` only from history strictly before its `cutoff_date`
(`invoice_date < cutoff_date`, never `<=`), enforced by a dbt singular test per mart
(`tests/no_feature_leakage.sql`, `tests/no_clv_feature_leakage.sql`, etc.) and independently
re-checked in Python by recomputing the same features from raw data in
`tests/test_phase2_leakage.py` / `test_phase3_leakage.py` -- two independent implementations of
the same check, not one test trusting its own logic twice.

I use three cutoffs throughout, fixed once in `docs/design.md` rather than re-decided per
phase: a validation cutoff (2010-12-01, for model tuning only), a train cutoff A (2011-03-01,
for fitting), and a test cutoff B (2011-09-01, touched exactly once per model for final
evaluation). I checked this against the real data's actual last row (2011-12-09): cutoff B's
90-day churn label window ends 9 days before the data runs out, with margin, not flush against
the edge.

I flag a customer as a wholesaler if a single invoice or their total volume places them in the
top 1% by quantity (confirmed against the real audit's 99th-percentile figure, not an arbitrary
round number). I keep wholesalers in the churn model (a wholesaler churning is a real, useful
signal), but I run and compare Phase 3's segmentation and CLV both with and without them, since
a clustering or CLV fit is far more sensitive to a handful of extreme accounts than a
classification model is.

## Results

### Warehouse build (Phase 1)

My first real `dbt build` against the actual dataset didn't fully succeed: the raw staging
layer's `unique` test failed with 32,907 duplicate-row groups, and because `dbt build` (unlike
`dbt test`) blocks every downstream node when an upstream test fails at error severity, all 23
nodes below it, including the leakage tests that are the whole point of this phase, never ran
on that first attempt. That block was a mistake in my own assumptions going in: I'd expected
everything downstream to still build and pass alongside the one expected failure, which turned
out to be wrong. I fixed it by downgrading that one test to `warn` severity (duplicates are
expected and already handled by deduplication further downstream, so failing the whole build on
them was never the right severity), after which a second real run passed cleanly:
`no_feature_leakage`, `no_label_leakage`, and `revenue_reconciles` all passed against the real
dataset. I reconciled the 32,907-vs-34,335 gap against the Phase 0 pandas audit's duplicate
count with a query, rather than leaving it open: 32,907 is the number of distinct duplicated row
groups, 34,335 is the total excess-row count across those groups (some groups have 3+ copies,
not just 2). Full writeup in `docs/evidence/p1_first_run_failures.md`; the real build log is
`docs/evidence/p1_dbt_build.txt`; I logged the mistake itself as `BUGLOG.md` entry 3, and the
`--full-refresh` cross-cutoff deletion footgun I found while fixing it is entry 4.

### Churn prediction (Phase 2)

Neither LightGBM nor logistic regression clearly beats a simple recency-threshold rule at
predicting 90-day churn on this dataset, and I'm reporting that straight rather than dressing it
up. On test cutoff B, PR-AUC is 0.801 [0.785, 0.816] for the recency rule, 0.813 [0.798, 0.829]
for logistic regression on RFM features, and 0.814 [0.799, 0.830] for LightGBM (95% bootstrap
CIs over customers). LightGBM's CI lower bound (0.799) is below the recency rule's CI upper
bound (0.816), so the overlap means this isn't a statistically clear win, and logistic
regression and LightGBM are indistinguishable from each other. I'm reporting this plainly
rather than leading with the raw point estimates, per my own ground rules for this project.
Full numbers, calibration tables, and the tuning trace are in `docs/evidence/p2_results.md`; a
real bug I hit in the threshold-tuning code (and its fix) is logged in `BUGLOG.md` entry 5.

### Segmentation and CLV (Phase 3)

Segmentation (cutoff B, 5,224 customers): running k-means on log-scaled, standardized RFM
lands on 4 segments either way, with or without the 53 flagged wholesalers (silhouette ~0.376,
bootstrap-ARI stability ~0.955, a tight 95% interval). Wholesalers don't change the cluster
structure, but they do concentrate revenue: the top segment holds 68.1% of revenue from 16.5%
of customers with wholesalers included, versus 59.9% from 17.9% with them excluded. Full tables
in `docs/evidence/p3_segments.md`.

CLV (BG/NBD + Gamma-Gamma, fit on cutoff A, validated on a real 245-day holdout I never touched
during fitting): I checked the Gamma-Gamma uncorrelated-frequency-and-spend assumption rather
than just assuming it, and it holds on the real data (Pearson correlation 0.061 among repeat
customers). The model ranks customers correctly (predicted and actual both rise monotonically
by decile, and the top decile is close: predicted 10,015 vs actual 9,615 transactions), but
it's not precise in the middle of the distribution, and the rank correlations are moderate
rather than strong (0.593 transactions, 0.597 spend). I'm reporting this as a usable ranking
signal, not a precise forecast. Full numbers in `docs/evidence/p3_clv_validation.md`.

### LLM segment summaries (Phase 4)

I generated a short, plain-language LLM summary per customer segment (cutoff B, the same four
real segments from Phase 3) from `docs/evidence/segment_stats.json`'s real numbers -- segment
size, revenue share, recency, frequency, predicted churn rate, predicted CLV -- with no new
modeling: the churn rate reuses Phase 2's exact LightGBM model and the CLV figure reuses
Phase 3's exact BG/NBD + Gamma-Gamma models, both scored on cutoff B. I checked every summary
with `python/llm/verify.py` for numbers it shouldn't have, segments it shouldn't mention, and
causal language it shouldn't use (I ran this for real on Groq's `openai/gpt-oss-120b`, after
the model I'd originally planned on, `llama-3.3-70b-versatile`, turned out to already be
retired -- see `BUGLOG.md` entry 7). All 4 of 4 real summaries passed: no unsupported numbers,
no unsupported segment references, no causal language.

That said, passing verification isn't the same as being well-written: two of the four
summaries describe `mean_monetary_net` (each customer's total net spend over their observed
history) as "average purchase value," which reads like a single order's size rather than a
lifetime total -- a real, numerically-correct-but-misleadingly-described result, not a verifier
miss, since describing what a number means isn't one of the three things my verifier checks.
Full summaries and this finding's full writeup are in `docs/evidence/p4_llm_summaries.md`; the
sandbox testing (synthetic fixture) I used to prove the pipeline and the verifier before this
real run is in `docs/evidence/p4_sandbox_test_log.txt`.

## Known limitations

I'm listing these here, together, rather than leaving them scattered across evidence files,
because a portfolio piece that only shows wins isn't a credible one:

- My churn models (LightGBM, logistic regression) don't clearly beat a one-line
  recency-threshold rule on this dataset -- the confidence intervals overlap. More features or
  tuning might change this; I didn't pursue it further here because my own ground rules for
  this project call for reporting a weak result as weak, not chasing a win.
- My CLV model's rank correlations are moderate (0.59-0.60), not strong, and it over-predicts
  in the middle of the distribution specifically. I'm treating it as a usable ranking signal,
  not a precise per-customer forecast, and describing it that way everywhere I use it.
- My LLM verifier checks three specific things (unsupported numbers, unsupported segment
  references, causal language) and nothing else. It doesn't and can't catch a summary that
  uses real numbers but mischaracterizes what a field means, which is exactly what happened
  with `mean_monetary_net` in the real run (see above).
- I excluded `country` from the churn model's inputs (high-cardinality categorical, no
  encoding scheme decided) -- a real, named gap rather than a silently dropped feature.
- 22.77% of all rows have no Customer ID and are unusable for anything customer-level -- a
  property of the raw dataset, not something I can recover in this pipeline.

## Engineering practices

- **Design locked before code:** I write every phase's decisions (cutoffs, features, success
  criteria, evidence format) into `docs/design.md` before I write the corresponding code, to
  reduce the temptation to rationalize a convenient result after I've already seen one.
- **Leakage tests, proven to work:** each leakage-sensitive mart has both a dbt singular SQL
  test and an independent Python re-implementation (pytest) that recomputes the same values
  from raw data. I proved several of these actually catch a leak, not just pass trivially, by
  deliberately introducing one (an off-by-one date comparison), confirming both tests failed,
  and reverting -- documented in `docs/evidence/p3_sandbox_test_log.txt`. I gave the Phase 4
  LLM verifier the same treatment: `tests/test_phase4_verify.py` proves it catches one
  deliberately broken fixture per check before I trusted it on real LLM output.
- **Real bugs, logged, not hidden:** `BUGLOG.md` has 7 real bugs I found during development,
  each with symptom, how I found it, root cause, and fix -- including ones I only caught on
  real data or during a real live API call, which sandbox testing against synthetic fixtures
  couldn't have caught by construction.
- **Split build environment:** I built this in a sandboxed environment with no access to the
  real dataset (blocked outbound network to the dataset host) or any live API key. I wrote and
  tested the code there against small synthetic fixtures (`docs/evidence/*_sandbox_test_log.txt`),
  then ran it for real, once, against the actual dataset and a real Groq key, pasting the
  results back and logging them as the official evidence. That split is why several BUGLOG
  entries exist: real bugs that a synthetic fixture genuinely couldn't surface.

## Repository structure

Here's how I organized the repo:

- `models/staging`, `models/intermediate`, `models/marts` -- the dbt SQL (see Architecture).
- `python/churn`, `python/clv`, `python/segment`, `python/llm` -- modeling code, one
  subpackage per phase, each with its own `data.py` (reads the warehouse, no feature logic)
  and model code.
- `python/run_phase2.py`, `run_phase3_segments.py`, `run_phase3_clv.py`,
  `build_segment_stats.py`, `run_phase4.py` -- the orchestration entrypoint for each phase.
- `docs/design.md` -- every implementation decision, locked before the code, with reasoning.
- `docs/evidence/` -- every real result (`p*_results.md`, `p*_segments.md`, etc.) and every
  sandbox test log (`p*_sandbox_test_log.txt`), kept as clearly separate, clearly labeled files.
- `tests/` -- dbt singular SQL tests and pytest Python tests, including independent
  re-implementations of every leakage check.
- `BUGLOG.md` -- real bugs found during development.

## Reproduction

Tested on macOS, Apple Silicon, Python 3.14.7.

1. Clone the repo, then create and activate a virtualenv:
   ```
   python3 -m venv venv && source venv/bin/activate
   ```
2. Install dependencies:
   ```
   pip install -r python/requirements.txt
   ```
   This installs `pymc-marketing` (BG/NBD + Gamma-Gamma) and `groq`, both of which pull in a
   fair number of transitive dependencies; all of them installed from prebuilt wheels on
   Apple Silicon with no compiler needed, confirmed during my own setup for this project.
3. Get the raw data: follow `data/raw/README.md` (download from UCI, save as
   `data/raw/online_retail_II.xlsx`), then run `make audit` (or
   `python3 python/audit.py`), which also writes the combined parquet file dbt reads from.
4. Build the warehouse for all three cutoffs and run the full test suite:
   ```
   make build
   make test
   ```
   If `make` hits an Xcode Command Line Tools license prompt on macOS, Ctrl-C out and run the
   three `dbt build --profiles-dir . --vars '{cutoff_date: "..."}'` calls directly (see
   `Makefile` for the exact cutoffs) -- `dbt` itself doesn't need the license, `make` just
   happens to trigger the prompt as a side effect on some machines.
5. Produce each phase's evidence:
   ```
   make phase2
   make phase3-segments
   make phase3-clv
   make phase4-stats
   ```
6. For Phase 4's real LLM summaries: get a free API key at
   [console.groq.com/keys](https://console.groq.com/keys), then
   ```
   export GROQ_API_KEY=...
   make phase4
   ```
   `make phase4-stub` runs the identical pipeline offline with no key, for testing the pipeline
   itself; its output is deliberately templated/broken and isn't real evidence.

Steps 4-5 (everything that doesn't need an API key) are also available as a single
`make all`.

## License and attribution

Dataset: UCI Online Retail II, https://archive.ics.uci.edu/dataset/502/online+retail+ii,
CC BY 4.0. I haven't added a license file to my own code yet; treat it as all-rights-reserved
portfolio code until I do.
