# Bug log

Every entry here is a real bug that actually happened during development, not a hypothetical.
Format: symptom, how it was found, root cause, fix.

## 1. Missing pyarrow dependency

**Symptom:** `python/audit.py` crashed with `ImportError: Unable to find a usable engine; tried
using: 'pyarrow', 'fastparquet'` when Vikram ran it for real, immediately after the pandas/duckdb
install succeeded.

**How found:** Vikram's first real run of `audit.py` against the full dataset, after the script
had already been tested against a small synthetic fixture in the build sandbox.

**Root cause:** The sandbox environment used to develop and test the script already had pyarrow
installed from an earlier, unrelated step, so the missing dependency never surfaced during
development testing. `requirements.txt` only listed pandas, duckdb, and openpyxl.

**Fix:** Added `pyarrow` to `python/requirements.txt`. Caught on the very next real run; no data
or results were affected since the script fails fast on import, before computing anything.

## 2. Unquoted cutoff_date cast compiled into arithmetic, not a timestamp cast

**Symptom:** `dbt build` for `mart_customer_features` failed with:
```
Binder Error: No function matches the given name and argument types '-(INTEGER, TIMESTAMP)'.
LINE 28:     where invoice_date < 2011-03-01::timestamp
```

**How found:** Testing the Phase 1 dbt project against a synthetic fixture in the build sandbox,
before shipping it to Vikram. Two different Jinja patterns were used for the same cutoff_date
cast across the file: most of the model used `cast('{{ var("cutoff_date") }}' as timestamp)`
(with quotes around the interpolated value), but the `history` CTE used
`{{ var('cutoff_date') }}::timestamp` (no quotes). Jinja renders the var as a bare string, so the
unquoted version compiled to `2011-03-01::timestamp` -- DuckDB parsed that as `2011 - 03 - 01`
(integer subtraction) and then tried to cast the result to timestamp, which has no matching
function.

**Root cause:** Inconsistent templating pattern for the same value in the same file. The quoted
version happened to be used everywhere it mattered for output correctness; the one unquoted spot
was in a `WHERE` filter, where the bug was loud (a build error) rather than silent.

**Fix:** Standardized on `cast('{{ var("cutoff_date") }}' as timestamp)` everywhere cutoff_date is
used in SQL. Caught before this was ever shipped or run against real data, by testing the full
project end to end against a synthetic fixture (including hand-computed expected values per
customer) before sending it to Vikram.

## 3. Real duplicate-row count from stg_online_retail_raw's first real run, and a wrong claim about what "downstream still passes" meant

**Symptom:** `tests/_staging_raw.yml`'s `unique` test on `row_key` failed on the first real
`dbt build` against the real dataset, as expected: `Got 32907 results, configured to fail if != 0`.
That number is close to but not identical to the 34,335 exact-duplicate rows found by the Phase 0
pandas audit (docs/audit.md section 4) -- not yet reconciled, see "Open question" below.

What was NOT expected: `dbt build` SKIPPED every downstream node (stg_online_retail,
stg_non_product_lines, int_customer_orders, both marts, and all 23 remaining data tests -- 23 of
31 total nodes). I had told Vikram beforehand "everything downstream should still build and pass."
That was wrong. `dbt build` treats a failing test at default (error) severity as blocking: any
node downstream of the tested resource is skipped, not just the test itself. Running this test at
error severity on the raw layer, as originally designed, made the first real run structurally
unable to reach Phase 1's actual acceptance criteria (marts built, leakage tests passing for both
cutoffs), since nothing past the raw layer ran at all.

**How found:** Vikram's first real `dbt build --vars '{cutoff_date: "2011-03-01"}'` run against
the real dataset. Full output is in docs/evidence/p1_dbt_build.txt.

**Root cause (duplicate rows):** Real export/logging duplication in the source file, already
identified in Phase 0 and the exclusion rule already implemented (`stg_online_retail.sql`
deduplicates on this same `row_key`). **Root cause (skip cascade):** my own incorrect assumption
about `dbt build` semantics when I planned the test's severity and told Vikram what to expect --
I did not account for its default fail-blocks-downstream behavior for `build` (as opposed to
`dbt test`, which does not block anything since nothing runs after it).

**Fix:** Downgraded `unique_stg_online_retail_raw_row_key` to `severity: warn` in
`models/staging/_staging_raw.yml`, immediately after this first real run, not in a later follow-up
as originally planned -- the pipeline cannot reach Phase 1's acceptance criteria otherwise. The
real failure count (32,907) is recorded here and in docs/evidence/ before the severity change, so
the downgrade is documented as a response to a real, witnessed failure, not a pre-suppression.
Vikram needs to re-run `dbt build` for cutoff A after pulling this fix to get the actual marts
built and the leakage/reconciliation tests actually executed.

**Reconciled, confirmed with a query, not assumed:** 32,907 vs 34,335 are both correct, measuring
different things on the same duplicate rows. dbt's `unique` test counts distinct `row_key` values
that have more than one row (one result row per duplicated group) -- 32,907 groups. The Phase 0
audit's `COUNT(*) - COUNT(DISTINCT ...)` counts total excess rows (sum of `count - 1` across every
group) -- 34,335. They only diverge because some duplicate groups have 3+ copies, not just 2.
Confirmed directly against the real warehouse:
```sql
with dupes as (
    select row_key, count(*) as n from stg_online_retail_raw group by row_key having count(*) > 1
)
select count(*) as duplicate_groups, sum(n - 1) as excess_rows from dupes
-- (32907, 34335)
```
Exact match on both numbers. No remaining discrepancy.

## 4. `dbt build --full-refresh --select <model>` on one cutoff silently deletes every OTHER
   cutoff's rows from that incremental table

**Symptom:** While sandbox-testing Phase 2's pytest leakage check, I deliberately planted a
one-line leak in `mart_customer_features.sql`, ran
`dbt build --vars '{cutoff_date: "2011-09-01"}' --select mart_customer_features --full-refresh`
to force a rebuild without needing to wait for incremental merge logic, confirmed the test caught
it, reverted the SQL, and re-ran the same `--full-refresh` command to restore a clean state.
Querying the warehouse afterward: `mart_customer_features` only had rows for `cutoff_date =
2011-09-01` -- the validation cutoff (2010-12-01) and train cutoff A (2011-03-01) rows, built in
earlier runs, were gone.

**How found:** Sandbox testing against a synthetic fixture for Phase 2, before shipping anything
to Vikram. Caught by a row-count sanity check I ran out of habit after the revert, not because
anything else flagged it.

**Root cause:** `--full-refresh` drops and recreates the entire physical table for the selected
model(s), not just the current invocation's slice of it. The incremental `delete+insert` strategy
only protects accumulation across normal incremental runs (matching rows by `unique_key`); a full
refresh bypasses that entirely and rebuilds from scratch using only whatever `--vars` were passed
to that one invocation. This is standard, documented dbt behavior, not a bug in this project's
SQL -- but it is a real operational trap for a multi-cutoff incremental design like this one,
worth knowing before using `--full-refresh` for anything other than a full `make build` across
all cutoffs.

**Fix:** Not a code fix -- an operational rule, now documented here and in the Makefile/README:
never run `--full-refresh` against a single cutoff on the marts once more than one cutoff's data
exists in them. If a full refresh is ever needed (e.g. a schema change), rebuild ALL cutoffs
immediately afterward (`make build` runs validation, A, and B in sequence) before trusting the
warehouse again. Recovered in the sandbox by re-running all three `dbt build --vars ...`
invocations in cutoff order.

## 5. Recency rule's tuned threshold collapsed to a near-trivial value (F1-argmax under class
   imbalance)

**Symptom:** Vikram's real Phase 2 run (`python3 python/run_phase2.py` against the real
warehouse) tuned the recency rule's threshold to X = 1 day on the validation cutoff
(2010-12-01), then reported precision=0.574, recall=0.996 on test cutoff B -- essentially
"predict almost everyone churns." The ranking metrics (PR-AUC 0.801, ROC-AUC 0.760 for the
recency rule) were still valid and sane, since those use `recency_days` directly as a continuous
score and never touch the threshold; only the threshold-based operating point was degenerate.

**How found:** Reviewing Vikram's real `p2_results.md` output. The real validation and train
populations turned out to be majority-churned under this project's 90-day label definition
(66.8% churned at the validation cutoff, 64.9% at cutoff A) -- much higher than I'd assumed when
designing the tuning procedure in docs/design.md, and higher than the synthetic sandbox fixture
happened to produce (56-59% churned there), which is why this was never caught in sandbox
testing before shipping.

**Root cause:** `tune_recency_threshold` picked the threshold that maximizes F1. F1-argmax is a
known-pathological choice under a majority-positive class: since recall dominates F1 when
precision is already high at low thresholds, the search keeps lowering the threshold toward
"flag everyone" because each step trades a small precision loss for a recall gain that F1 weighs
favorably, with no term in F1 to penalize false positives against the (large) true negative
population. This is a property of F1 itself, not a coding error.

**Fix:** Changed the selection criterion to Youden's J statistic (max of TPR − FPR) in
`python/churn/baselines.py`. Youden's J is the point on the ROC curve farthest from the
diagonal and does not have this majority-class collapse: it penalizes false positives by their
rate against the true negative population directly, rather than letting overall precision mask
it. Verified in the sandbox against the synthetic fixture (produces a sane, non-degenerate
threshold there too, just as the old F1 version did -- the bug only showed up on real data
because of its more extreme class balance). Vikram needs to re-run `python3 python/run_phase2.py`
(dbt build does not need to be re-run) to get the corrected real threshold and operating-point
numbers before `docs/evidence/p2_results.md` is finalized.

**Confirmed fixed on real data:** Vikram re-ran `python3 python/run_phase2.py` against the real
warehouse after pulling the fix. The threshold is now X = 49 days (validation J = 0.303, TPR =
0.591, FPR = 0.289), giving precision=0.673, recall=0.885 on test cutoff B -- a sane operating
point, not "flag almost everyone." Every other number in the report (class balance, LightGBM
tuning trials, the PR-AUC/ROC-AUC/lift/capture/Brier results table, both calibration tables, and
the success-criterion check) is byte-identical to the pre-fix real run, confirming the bug was
isolated to the threshold-based operating point exactly as predicted -- the ranking metrics never
used the threshold. Real, final output is in `docs/evidence/p2_results.md`.

## 6. pymc-marketing's `GammaGammaModel.expected_new_customer_spend()` returned a negative
   value on real-shaped data

**Symptom:** While sandbox-testing Phase 3's CLV code against the synthetic fixture, the
planned fallback for predicting monetary value for frequency_repeat=0 (single-purchase)
customers -- `GammaGammaModel.expected_new_customer_spend()`, the library's own "population
average for an unseen customer" method -- returned a negative posterior mean (-3050.94) on a
small repeat-customer population (224 customers) where frequency and monetary_value are
correlated (0.57, see docs/design.md and p3_clv_validation.md). A negative predicted average
transaction value is nonsensical.

**How found:** A smoke test run directly in the sandbox before writing it into
`python/clv/model.py`, specifically because the Gamma-Gamma assumption (frequency and
monetary_value uncorrelated) looked likely to be violated on this dataset and I wanted to check
the fallback path before trusting it, not after.

**Root cause:** Not confirmed from the library's source in detail, but consistent with
Gamma-Gamma's own math: `expected_new_customer_spend()` extrapolates from the fitted p/q/v
parameters to a customer with no observed repeat purchases at all, and that extrapolation is
not guaranteed to stay positive when the fitted parameters are already a poor fit to the data
(which a strong assumption violation would cause).

**Fix:** Don't use that method. `python/clv/model.py`'s `fit_gamma_gamma()` instead returns the
plain empirical mean of `monetary_value` over the repeat customers actually used to fit the
model, and `predict_clv()` uses that empirical mean as the monetary-value plug-in for
frequency_repeat=0 customers, documented inline in the code rather than silently swapped. This
is a simpler, always-positive estimate, at the cost of not being a model-based prediction for
that subgroup -- an honest tradeoff, not a hidden one.

## 7. Groq's default model (`llama-3.3-70b-versatile`) was already retired, despite Groq's own
   docs page listing it as a current production model

**Symptom:** Vikram's first real `python3 python/run_phase4.py` call, right after getting a
real `GROQ_API_KEY`, failed immediately with `groq.NotFoundError: Error code: 404 - ... 'The
model `llama-3.3-70b-versatile` does not exist or you do not have access to it.'`

**How found:** Not caught in sandbox testing -- `StubClient` never calls the real API, so this
could only surface on a real Groq call, which requires a real key Vikram didn't have until
Phase 4's live-run step. This is a real gap in what sandbox testing with a stub client can
catch, not a process failure: the whole point of a stub/real split is that the stub can't
exercise the live API's own behavior.

**Root cause:** Groq retired `llama-3.3-70b-versatile` on 2026-08-16. The model was picked as
Phase 4's default on 2026-10-10 (almost two months after the retirement) after checking Groq's
own docs page (console.groq.com/docs/models), which, re-checked after this failure, still lists
`llama-3.3-70b-versatile` under "Production Models" -- Groq's docs page itself is stale or
wrong, not just the design-time check. The deprecations page
(console.groq.com/docs/deprecations) has the real shutdown date and names
`openai/gpt-oss-120b` as the recommended replacement.

**Fix:** Default model in `python/llm/client.py` (`DEFAULT_GROQ_MODEL`) changed to
`openai/gpt-oss-120b`. Vikram unblocked immediately without waiting for a new zip by setting
the `GROQ_MODEL` environment variable, which `GroqClient.__init__` already read as an override
-- this is exactly the scenario that env-var configurability (locked in docs/design.md's Phase
4 decisions) was for. No code or prompt logic needed to change, only which model name is sent.
Lesson for anyone extending this: do not trust a vendor's own "current models" docs page at
face value for whether a specific model ID is actually callable; the deprecations/changelog
page is the one that had the accurate, dated answer here.
