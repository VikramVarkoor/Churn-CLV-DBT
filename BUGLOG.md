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

## 3. [TBD] Real duplicate-row count from stg_online_retail_raw's first real run

**Symptom:** `tests/stg_online_retail_raw.yml`'s `unique` test on `row_key` is expected to fail
the first time `dbt build` runs against the real dataset, per docs/audit.md section 4 (34,335
exact-duplicate rows found in the raw file during the Phase 0 audit).

**How found:** TBD -- waiting on Vikram's first real `dbt build` run. The severity on this test is
intentionally left at the default (error) for that first run so the failure is real and visible,
not pre-suppressed.

**Root cause:** Real export/logging duplication in the source file, already identified and the
exclusion rule already designed and implemented (`stg_online_retail.sql` deduplicates on this
same key). This entry exists to record the real failure count from the real run, then the test's
severity gets downgraded to `warn` in a follow-up commit, since the issue is already understood
and already handled downstream.

**Fix:** Pending the real run. Will be filled in with the actual row count dbt reports, not
estimated.
