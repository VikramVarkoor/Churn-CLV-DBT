.PHONY: all audit build build-validation build-train build-test docs phase2 phase3-segments phase3-clv phase4-stats phase4-stub phase4 test

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

# Phase 3: RFM + k-means segmentation on cutoff B's snapshot. Requires `make build-test`
# (cutoff B) to have been run first.
phase3-segments:
	python3 python/run_phase3_segments.py

# Phase 3: BG/NBD + Gamma-Gamma CLV, fit on cutoff A, validated on the 245-day holdout.
# Requires `make build-train` (cutoff A) to have been run first -- that single `dbt build`
# invocation builds both mart_clv_features and mart_clv_holdout_actuals for cutoff A together.
phase3-clv:
	python3 python/run_phase3_clv.py

# Phase 4: segment stats JSON (reuses Phase 2's churn model and Phase 3's CLV/segmentation
# models, no new tuning). Requires `make build` (all three cutoffs) to have been run first.
phase4-stats:
	python3 python/build_segment_stats.py

# Phase 4: LLM summaries + verification, offline/deterministic (no API key needed). Requires
# `make phase4-stats` to have been run first. Good for checking the pipeline works before
# spending a real Groq call.
phase4-stub:
	python3 python/run_phase4.py --stub

# Phase 4: LLM summaries + verification, real Groq call. Requires GROQ_API_KEY to be set --
# see README.md for how to get one -- and `make phase4-stats` to have been run first.
phase4:
	python3 python/run_phase4.py

test:
	python3 -m pytest tests/ -v

docs:
	dbt docs generate --profiles-dir .
	dbt docs serve --profiles-dir .

# Everything that doesn't need a Groq API key: build the warehouse, run the full pytest
# suite, and produce Phase 2/3/4's evidence (segment stats, not the LLM summaries -- that one
# costs a real API call and needs GROQ_API_KEY, so it's deliberately left out of `all`; run
# `make phase4` for that once you have a key). Requires `data/raw/online_retail_ii_combined.parquet`
# to already exist -- see data/raw/README.md if it doesn't, or `make audit` after placing the
# raw .xlsx file there.
all: build test phase2 phase3-segments phase3-clv phase4-stats
	@echo ""
	@echo "Done. Everything above is reproducible with no API key. For Phase 4's real LLM"
	@echo "summaries: get a key at https://console.groq.com/keys, then"
	@echo "  export GROQ_API_KEY=... && make phase4"
