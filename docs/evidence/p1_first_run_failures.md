# Phase 1 first-run failures

Real results from Vikram's first real `dbt build --vars '{cutoff_date: "2011-03-01"}'` run
against the real dataset, 2026-10-05. Full output in docs/evidence/p1_dbt_build.txt.

## What failed, and why that part was expected

- `unique_stg_online_retail_raw_row_key` failed with **32,907** duplicate rows (dbt's exact
  wording: "Got 32907 results, configured to fail if != 0"). This is the raw, undeduplicated
  layer; `stg_online_retail.sql` already deduplicates downstream of it on the same `row_key`. The
  test exists at the raw layer specifically so this failure is visible and recorded once, with a
  real number, rather than skipped past.
- This number is close to, but not identical to, the 34,335 exact-duplicate rows found by the
  Phase 0 pandas audit (docs/audit.md section 4). Not yet reconciled -- open question logged in
  BUGLOG.md entry 3. The two counts likely differ because dbt's `unique` test and pandas'
  `duplicated()` count duplicate groups differently (rows beyond the first vs. all flagged rows);
  this needs to be checked directly against the dedup query logic, not assumed.

## What was NOT expected, and is on me, not a data problem

`dbt build` skipped all 23 remaining nodes downstream of `stg_online_retail_raw`: both staging
models that ref it, `int_customer_orders`, both marts, and every test on those models, including
`no_feature_leakage`, `no_label_leakage`, and `revenue_reconciles` -- the tests that actually prove
Phase 1's leakage-safety claims. None of them ran on this first attempt.

I had told Vikram beforehand that "everything downstream should still build and pass" alongside
this one expected failure. That was wrong. `dbt build` (unlike `dbt test`) blocks downstream nodes
by default when an upstream test fails at error severity, regardless of whether the model itself
built successfully (it did -- `stg_online_retail_raw` shows `OK created`). I did not account for
that when I set this test's severity and when I described what to expect. Recorded in BUGLOG.md
entry 3.

## Fix applied, and confirmed

`unique_stg_online_retail_raw_row_key` was downgraded to `severity: warn` in
`models/staging/_staging_raw.yml`, in response to this real documented failure, not pre-emptively.
Re-run for cutoff A on 2026-10-05 confirms the fix: `PASS=30 WARN=1 ERROR=0 SKIP=0 NO-OP=0
REUSED=0 TOTAL=31`. The one WARN is the same 32,907-row duplicate finding, now non-blocking as
intended. `mart_customer_features` and `mart_churn_labels` built, and `no_feature_leakage`,
`no_label_leakage`, and `revenue_reconciles` all ran and PASSed against the real dataset for the
first time. Full output in docs/evidence/p1_dbt_build.txt.

Cutoff B (2011-09-01) re-run on 2026-10-05: identical shape, `PASS=30 WARN=1 ERROR=0 SKIP=0
NO-OP=0 REUSED=0 TOTAL=31`. Full output in docs/evidence/p1_dbt_build.txt.

A direct query confirmed both cutoffs persist together, not overwritten:
`mart_customer_features` and `mart_churn_labels` each hold 4,512 rows at `cutoff_date =
2011-03-01` and 5,224 rows at `cutoff_date = 2011-09-01` (query and full counts in
docs/evidence/p1_dbt_build.txt). The customer count growing from A to B is expected -- more
purchase history has accumulated by September than by March.

The 32,907 vs 34,335 gap is also resolved, with a query, not left open: 32,907 is the number of
distinct duplicated `row_key` groups; 34,335 is the total excess-row count across those groups
(some groups have 3+ copies, not just 2). Confirmed exactly against the real warehouse. See
BUGLOG.md entry 3 for the query and result.

## Status: Phase 1 acceptance criteria met

- Same SQL, two `--vars` runs, both cutoffs' rows coexist in the incremental marts: confirmed.
- `no_feature_leakage`, `no_label_leakage`, `revenue_reconciles` all pass against real data for
  both cutoffs: confirmed.
- The one real, documented failure (raw duplicate rows) is recorded with its real count before its
  severity was changed, not pre-suppressed: confirmed.
- All real numbers here came from Vikram's own runs on his machine, not invented or estimated.
