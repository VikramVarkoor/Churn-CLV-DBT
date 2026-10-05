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

## Fix applied, and what's still pending

`unique_stg_online_retail_raw_row_key` has been downgraded to `severity: warn` in
`models/staging/_staging_raw.yml`, now, in response to this real documented failure, not
pre-emptively. Still pending, real:

- Re-run `dbt build` for cutoff A with the fix applied, to get the marts actually built and
  `no_feature_leakage` / `no_label_leakage` / `revenue_reconciles` actually executed. TBD.
- `dbt build` for cutoff B (`make build-test` or the direct `dbt build --vars ...` command), to
  confirm both cutoffs accumulate in the same incremental table as designed. TBD.
- The 32,907 vs 34,335 reconciliation above. TBD.
