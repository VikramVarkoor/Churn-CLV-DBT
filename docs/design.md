# Phase 0 design lock

Written and committed before any dbt model file exists, based on the real counts in
`docs/audit.md`. These decisions are fixed for Phases 1-3. A later phase can only change them by
adding a new commit that explains why, never by quietly editing the behavior.

## Cutoffs

Data covers 2009-12-01 07:45:00 to 2011-12-09 12:50:00 (confirmed in the audit, not assumed).

- **Train cutoff A: 2011-03-01**
- **Test cutoff B: 2011-09-01**

Check against the real end date: B + 90 days = 2011-11-30, which is 9 days before the actual last
row (2011-12-09 12:50:00). The 90-day post-cutoff label window for the test cutoff is fully inside
observed data, with margin, not flush against the edge. A + 90 days = 2011-05-30, also fully inside
the data with over a year of data remaining after it for B's features to use.

A time-aware validation cutoff for Phase 2's tuning (an earlier point used only during training,
never touching B) is deferred to Phase 2 itself rather than fixed here, since it only affects model
tuning, not the warehouse or the label definition. Candidate: 2010-12-01, which gives roughly a
year of pre-period data and keeps its own 90-day window well clear of cutoff A.

## Population

A customer is in the population as of a given cutoff_date if they have at least one valid purchase
line (see exclusion rules below) with `InvoiceDate < cutoff_date` and a non-null Customer ID.
"Valid purchase line" excludes cancellations for the purpose of population membership, i.e. a
customer whose only history before the cutoff is a cancellation is not in the population as of
that cutoff (there's no original purchase on record to have churned from).

## Churn label

Churned = no valid purchase line with `cutoff_date <= InvoiceDate < cutoff_date + 90 days`.
"Valid purchase line" again excludes cancellations: a customer who only returns something in the
90-day window (no new purchase) still counts as churned.

## Features

Computed only from line items with `InvoiceDate < cutoff_date`. No feature may reference anything
on or after the cutoff; this is exactly what the pytest leakage tests in Phase 2 check for
programmatically, not just by convention.

## Exclusion rules (every one logged here, none silent)

Applied at the staging layer, in this order:

1. **Exact duplicate rows** (identical Invoice, StockCode, Description, Quantity, InvoiceDate,
   Price, CustomerID, Country) — drop all but the first occurrence. 34,335 rows affected per the
   audit. Reason: this dataset does not have sub-second timestamps, and two completely identical
   values across all 8 fields including the same minute is far more consistent with an export
   duplication artifact than two genuinely separate transactions.

2. **Price <= 0** — drop entirely. 6,207 rows affected (6,202 at exactly 0, 5 negative). Reason,
   confirmed directly in the audit: every one of the 3,457 anomalous negative-quantity rows that
   aren't flagged as cancellations has Price = 0 and no Customer ID, i.e. these are warehouse
   write-offs (example: "printing smudges/thrown away", -9,600 units), not customer activity. The
   5 rows with Price < 0 are also administrative, not real pricing. This single rule removes the
   entire anomaly class with zero loss of real customer signal (confirmed: 0 of those rows had a
   real price or a real customer attached).

3. **Non-product StockCode** — a StockCode is treated as a product code only if it matches
   `^[0-9]+[A-Za-z]*$` (purely numeric, with an optional trailing letter suffix); this is the same
   pattern the audit's catch-all scan used, so it already covers every non-product code actually
   found in the file, not just a hardcoded list. Matched codes are routed to a separate
   `stg_non_product_lines` model instead of being silently dropped, with the StockCode and its
   row count preserved as the reason. Known codes and what they are: POST/DOT/C2 (postage/carriage),
   M (manual line), BANK CHARGES, ADJUST, AMAZONFEE, CRUK (donation), D (discount line), S
   (samples), gift_0001_10/20/30 (gift cards), TEST001 (literal QA test rows, 15 of them).
   DCGS* and PADS codes matched the non-product pattern too but their Description text hasn't
   been reviewed yet; they're routed to `stg_non_product_lines` under the same rule for now, and
   get a one-line note in BUGLOG.md once reviewed, rather than blocking Phase 1 on it.

4. **Cancellations are kept, not dropped.** Invoice numbers starting with `C` are real reversals
   of real purchases and stay in the data as negative line items. They affect monetary features
   (net of cancellations) and factor into the churn label and population definitions above, but
   are never excluded as "dirty data."

## Wholesaler rule

A customer is flagged as a wholesaler if their total purchased quantity (purchase invoices only,
post-exclusion) is at or above the 99th percentile of per-invoice quantity observed in the audit
(2,232 units) **on a single invoice**, or their total quantity across all invoices places them in
the top 1% of customers by volume. Audit evidence: the top 6 customers by quantity (14646, 13902,
13694, 18102, 14156, 14911) are an order of magnitude above the 99th percentile single-invoice
figure, with customer 14646 alone at 367,833 units across 152 invoices. The flag does not exclude
these customers from churn modeling (a wholesaler can still churn and that's a real signal worth
keeping), but Phase 3 segmentation is run both with and without them, per the brief, since a
clustering or CLV fit is far more sensitive to a few extreme-volume accounts than a classification
model is.

## Metrics, baselines, and what counts as success

- **Baselines (Phase 2):** (1) a recency rule tuned only on the training period; (2) logistic
  regression on RFM features.
- **Model:** gradient boosting, tuned only within the training period using the 2010-12-01
  validation cutoff, evaluated once on cutoff B.
- **Metrics:** PR-AUC and ROC-AUC as the primary comparison, plus lift/capture in the top decile
  and calibration, all with bootstrap confidence intervals over customers (not over rows).
- **Success is relative, not absolute:** the model needs to clearly beat the recency baseline with
  non-overlapping confidence intervals. If it doesn't, the README reports that plainly, per the
  brief's ground rules, rather than reporting the model's raw number alone.

## Phase 2 implementation decisions (locked here, before model code exists)

- **Validation cutoff:** 2010-12-01, as proposed above. Its 90-day label window is
  [2010-12-01, 2011-03-01), which touches cutoff A's date but not A's data -- the validation
  cutoff's features and labels are computed independently, straight from history before
  2010-12-01, the same way cutoff A and B are. This needs its own `dbt build --vars
  '{cutoff_date: "2010-12-01"}'` run against the real warehouse before Phase 2 can tune anything
  for real.
- **Gradient boosting library: LightGBM.** Checked before committing (not assumed): LightGBM
  4.7.0 ships a pure-wheel (`py3-none`) build for macOS arm64, so no C compiler is needed on
  Vikram's Mac, which matters given the Xcode Command Line Tools license wall already hit once in
  Phase 1 (BUGLOG.md). scikit-learn and scipy also have cp314 arm64 wheels, confirmed directly
  against PyPI before adding them to requirements.txt.
- **Recency rule, used two ways, not one:** the brief's metrics (PR-AUC, ROC-AUC, lift/capture at
  decile, calibration) are ranking/probabilistic metrics; a bare threshold rule only produces a
  hard yes/no. So `recency_days` itself is used directly as a continuous ranking score for the
  ranking metrics (directly comparable to the other two models on the same footing), and
  separately, a threshold X is tuned on the validation cutoff (grid search over observed
  recency_days values, maximizing Youden's J = TPR - FPR) to report an interpretable
  precision/recall operating point. Originally this maximized F1 instead; changed after Vikram's
  real first run showed F1-argmax collapsing to a near-trivial threshold (X=1 day) because the
  real validation population turned out to be majority-churned (66.8%) under this label
  definition -- see BUGLOG.md entry 5. Calibration is not reported for the recency rule -- a raw
  day count is not a probability, and forcing one through an arbitrary transform just to fill in
  a number would be exactly the kind of invented precision the brief's ground rules rule out.
- **Logistic regression baseline features:** recency_days, frequency, monetary_net only (RFM,
  per the brief's own wording), standardized before fitting.
- **Gradient boosting features:** the full mart_customer_features set (recency, frequency,
  monetary_net, monetary_gross, tenure, avg_basket_value, distinct_products,
  mean_days_between_purchases, cancellation_rate, total_quantity_purchased, is_wholesaler).
  `country` is left out of modeling for now (high-cardinality categorical, no encoding scheme
  decided yet) -- noted here rather than silently dropped. `mean_days_between_purchases` is null
  for single-purchase customers; LightGBM handles missing values natively (verified in sandbox
  testing, not assumed from documentation), so this is left as a real null, not imputed.
- **Tuning procedure:** a small fixed grid of LightGBM hyperparameters (num_leaves, learning_rate,
  min_child_samples), each fit on cutoff A's population with early stopping evaluated on the
  validation cutoff's population, selecting by validation PR-AUC (`average_precision`, confirmed
  as a native LightGBM eval metric in sandbox testing). The winning params and early-stopped
  iteration count are then used to refit one final model on cutoff A alone (never on B) before
  the single, final evaluation on cutoff B.

## Phase 3 implementation decisions (locked here, before segmentation/CLV code exists)

- **Segmentation snapshot:** cutoff B (2011-09-01), reusing the already-built `mart_customer_features`
  for that cutoff rather than introducing a fourth cutoff. Segmentation is a description of the
  customer base as of a point in time, not a leakage-sensitive prediction, so it does not need its
  own train/test split -- it needs one defensible, already-audited snapshot, and cutoff B has the
  longest feature-building history of the three.
- **RFM quintile scoring:** recency_days, frequency, monetary_net from `mart_customer_features` at
  cutoff B, each independently ranked into quintiles 1-5 (`pd.qcut`, duplicates dropped where the
  data has ties at a bin edge, which is noted in p3_segments.md if it reduces the quintile count
  below 5 for any dimension). Recency is scored in reverse (low recency_days = good = quintile 5)
  so that higher is better on all three axes, matching standard RFM convention.
- **K-means:** fit on log1p-transformed, standardized (StandardScaler) recency_days, frequency,
  monetary_net. Log transform first because all three are heavily right-skewed (confirmed in
  docs/audit.md's order-size distribution and in Phase 1/2's real class-balance and feature
  output) and k-means uses Euclidean distance, which is dominated by the raw monetary_net scale
  otherwise. k chosen from a grid (k=3..8) by silhouette score, then checked for interpretability
  (a k that produces a segment under 1% of customers is flagged, not automatically rejected --
  small-but-real segments like wholesalers are a legitimate finding, not noise).
- **Stability:** bootstrap-ARI -- refit k-means on B bootstrap resamples (customers, with
  replacement) of the same population, compute the adjusted Rand index between each resample's
  labels and the full-population labels (restricted to the resample's own customers), report the
  mean and a percentile interval. This checks whether the chosen k produces the same partition
  under resampling, not just a locally good silhouette score.
- **Wholesaler with/without:** the full pipeline above (RFM quintiles, k selection, k-means,
  bootstrap-ARI) is run twice: once on all of cutoff B's population, once excluding customers
  flagged `is_wholesaler` by the Phase 0 rule. Both k choices, silhouette scores, and stability
  numbers are reported side by side in p3_segments.md; segment names are assigned from each run's
  own statistics only (e.g. "high-value repeat buyers"), never a fixed label list.
- **CLV library: PyMC-Marketing.** Checked before committing, not assumed, per the brief:
  `lifetimes` (PyPI) last released 0.11.3 on 2020-07-06 -- over five years stale, confirms the
  brief's own note that it is no longer actively developed. `pymc-marketing` latest release is
  1.2.0 (2026-09-29, actively maintained) and its full dependency chain installs from wheels on
  macOS arm64 with no C compiler needed: `pymc-marketing` itself and `pymc` 6.3.2 both ship
  `py3-none-any` wheels, `arviz` 1.3.0 is pure Python, and `pytensor` 3.3.3 (pymc's compute
  backend) ships `cp312`/`cp313`/`cp314` `macosx_11_0_arm64` wheels -- checked directly against
  PyPI's JSON API, not assumed. This matters because the Xcode Command Line Tools license wall
  already blocked a compiler-dependent step once in this project (BUGLOG.md entry about `make`);
  a pure-wheel install chain avoids that risk entirely. `lifetimes`'s own data-prep utilities
  (e.g. `summary_data_from_transaction_data`) are not used either way, since the project's own
  design rule is that features come from parameterized dbt SQL, not ad hoc Python.
- **CLV feature convention (BG/NBD/Gamma-Gamma), a new mart, not a reuse of mart_customer_features:**
  BG/NBD needs frequency defined as *repeat* purchase count (first purchase excluded), `T` =
  calibration-period customer age (first purchase to the calibration cutoff), and `recency` =
  time from first to *last* purchase within the calibration period -- all different from
  `mart_customer_features`'s own recency/frequency definitions (days-since-last-purchase,
  total purchase count), which were built for the churn label, not for BG/NBD. Rather than
  overload one mart with two incompatible conventions, Phase 3 adds `mart_clv_features`
  (parameterized by `cutoff_date`, same pattern as the existing marts) computing frequency_repeat,
  T, recency_cal, and monetary_value (average order value of repeat orders only, net of
  cancellations) from history strictly before the cutoff.
- **Calibration cutoff and holdout window:** calibration cutoff = 2011-03-01 (cutoff A, reused --
  it already has about 15 months of pre-period history for BG/NBD to fit on, versus cutoff B's
  leftover runway for a holdout). Holdout window ends 2011-11-01 (245 days after the calibration
  cutoff). Checked against the real last row (2011-12-09 12:50:00, confirmed in docs/audit.md):
  this leaves 38 days of margin, so the holdout window is fully inside observed data, not flush
  against the edge, the same discipline Phase 0 applied to the churn cutoffs. A new
  `mart_clv_holdout_actuals` (also parameterized by `cutoff_date`, using a fixed 245-day window)
  computes each customer's actual transaction count and actual net spend in
  `[cutoff_date, cutoff_date + 245 days)`, for validation only -- never fed into fitting.
- **Gamma-Gamma assumption check:** Gamma-Gamma assumes frequency and average monetary value are
  uncorrelated among repeat customers. This is checked, not assumed: Pearson correlation between
  frequency_repeat and monetary_value, computed over customers with frequency_repeat >= 1 in the
  calibration population, is reported in p3_clv_validation.md whatever its value turns out to be.
- **Validation:** fit BG/NBD on frequency_repeat/T/recency_cal, fit Gamma-Gamma on
  frequency_repeat/monetary_value (repeat customers only, per the model's own requirement),
  predict expected transactions and expected monetary value over the 245-day holdout window, and
  compare against `mart_clv_holdout_actuals` with MAE (both transaction count and spend) and
  Spearman rank correlation (predicted CLV rank vs actual spend rank), plus a predicted-vs-actual
  table by decile of predicted CLV. Fit quality alone (e.g. in-sample log-likelihood) is not
  reported as validation, per the brief's explicit instruction that fit alone is not validation.
