.PHONY: audit build build-validation build-train build-test docs phase2 test

# Phase 0: run the data audit against data/raw/online_retail_II.xlsx
audit:
	python3 python/audit.py

# Phase 1/2: build the warehouse for all three cutoffs (validation, train, test), same SQL,
# different --vars. Cutoffs are fixed in docs/design.md, not here.
#
# WARNING (BUGLOG.md entry 4): `dbt build --full-refresh` on a single cutoff wipes every OTHER
# cutoff's rows from the incremental marts. If you ever need --full-refresh, run `make build`
# (all three, in order) again immediately afterward before trusting the warehouse.
build-validation:
	dbt build --profiles-dir . --vars '{cutoff_date: "2010-12-01"}'

build-train:
	dbt build --profiles-dir . --vars '{cutoff_date: "2011-03-01"}'

build-test:
	dbt build --profiles-dir . --vars '{cutoff_date: "2011-09-01"}'

build: build-validation build-train build-test

# Phase 2: baselines + LightGBM, tuned on validation/train, evaluated once on test.
# Requires `make build` (all three cutoffs) to have been run first.
phase2:
	python3 python/run_phase2.py

test:
	python3 -m pytest tests/ -v

docs:
	dbt docs generate --profiles-dir .
	dbt docs serve --profiles-dir .
