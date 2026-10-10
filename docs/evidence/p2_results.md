TBD.

This file must hold the real output of `python3 python/run_phase2.py`, run on Vikram's machine
against the real warehouse (data/warehouse.duckdb), after `dbt build` has been run for all three
of Phase 2's cutoffs: the validation cutoff (2010-12-01), train cutoff A (2011-03-01), and test
cutoff B (2011-09-01). Per the project's ground rules, no invented numbers: this stays TBD until
that real run happens and its output is pasted in here.

See docs/evidence/p2_sandbox_test_log.txt for the sandbox's own verification run against a
synthetic fixture (used only to confirm the Phase 2 code -- data loading, baselines, LightGBM
tuning, metrics, bootstrap CIs, and the pytest leakage checks -- is mechanically correct before
shipping it; not a substitute for this file). That log also shows the pytest leakage check
genuinely catching a deliberately planted leak, not just passing trivially.
