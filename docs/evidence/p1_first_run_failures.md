# Phase 1 first-run failures

TBD -- waiting on Vikram's first real `dbt build` run against the real dataset.

What's expected to fail, and why that's correct (not a bug to silently fix):

- `unique_stg_online_retail_raw_row_key` -- expected to fail with roughly 34,335 duplicate rows,
  per docs/audit.md section 4. This is the raw, undeduplicated layer; `stg_online_retail.sql`
  already deduplicates downstream of it. The test exists at the raw layer specifically so this
  failure is visible and recorded once, with real numbers, rather than skipped past.

Once Vikram runs `dbt build` for real, this file gets updated with:
- The actual row count dbt reports for the duplicate test (replacing "roughly 34,335" above).
- Whether anything else failed that wasn't anticipated here.
- A note in BUGLOG.md entry 3 with the confirmed real number, and the test's severity downgraded
  from error to warn in a follow-up commit (the issue is already understood and already handled
  downstream, so failing the build on it forever isn't useful after this first documented run).
