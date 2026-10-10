TBD.

This file must hold the real output of `python3 python/run_phase3_clv.py`, run on Vikram's
machine against the real warehouse (data/warehouse.duckdb), after `dbt build` has been run for
the calibration cutoff (2011-03-01) -- this builds mart_clv_features and
mart_clv_holdout_actuals together. Per the project's ground rules, no invented numbers: this
stays TBD until that real run happens and its output is pasted in here.

See docs/evidence/p3_sandbox_test_log.txt for the sandbox's own verification run against a
synthetic fixture (used only to confirm the Phase 3 code -- BG/NBD and Gamma-Gamma fitting via
pymc-marketing, the Gamma-Gamma correlation check, and the holdout validation metrics -- is
mechanically correct before shipping it; not a substitute for this file).
