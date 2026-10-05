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

**Open question, not yet resolved:** 32,907 (dbt's `unique` test, counting rows beyond the first
per duplicate `row_key` group) vs 34,335 (Phase 0 pandas `duplicated()` count) are measuring
slightly different things and are not expected to match exactly, but the gap hasn't been checked
line-by-line yet. To close this out: confirm whether pandas' duplicate check was keyed on the same
8 columns as `row_key`'s md5, or on a different column set.
