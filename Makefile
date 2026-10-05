.PHONY: audit build build-train build-test docs

# Phase 0: run the data audit against data/raw/online_retail_II.xlsx
audit:
	python3 python/audit.py

# Phase 1: build the warehouse for both cutoffs (train then test), same SQL,
# different --vars. Cutoffs are fixed in docs/design.md, not here.
build-train:
	dbt build --profiles-dir . --vars '{cutoff_date: "2011-03-01"}'

build-test:
	dbt build --profiles-dir . --vars '{cutoff_date: "2011-09-01"}'

build: build-train build-test

docs:
	dbt docs generate --profiles-dir .
	dbt docs serve --profiles-dir .
