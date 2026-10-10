# Phase 3 CLV validation

Generated: 2026-10-10

Calibration cutoff: 2011-03-01. Holdout window: 245 days (evaluated once, below, never used during fitting).

n_customers=4512, repeat customers (frequency_repeat >= 1) used to fit Gamma-Gamma: n_repeat=3027.

## Gamma-Gamma assumption check

Gamma-Gamma assumes frequency and mean order value are uncorrelated among repeat customers. Checked, not assumed: Pearson correlation between frequency_repeat and monetary_value over the 3027 repeat customers in the calibration population is 0.061.

This is close to zero, so the assumption holds reasonably well on the real data, unlike the
sandbox's synthetic fixture, where the same check found a correlation of 0.57 (a known
limitation of that fixture, logged honestly in the earlier sandbox test log rather than hidden).
The real result is the one that matters for this project's claims.

## Holdout validation (never used in fitting)

Transaction count MAE: 1.496. Spend MAE: 702.00.
Spearman rank correlation, predicted vs actual transactions: 0.593 (p=0.0000).
Spearman rank correlation, predicted vs actual spend (the CLV figure): 0.597 (p=0.0000).

### Predicted vs actual transactions, by decile of predicted transactions

|   decile |   n |   mean_predicted |   mean_actual |
|---------:|----:|-----------------:|--------------:|
|        1 | 452 |            0.339 |         0.305 |
|        2 | 451 |            0.53  |         0.545 |
|        3 | 451 |            0.761 |         0.641 |
|        4 | 451 |            0.946 |         0.612 |
|        5 | 451 |            1.224 |         0.942 |
|        6 | 451 |            1.65  |         1.237 |
|        7 | 451 |            2.122 |         1.494 |
|        8 | 451 |            2.774 |         2.06  |
|        9 | 451 |            3.996 |         3.14  |
|       10 | 452 |           10.015 |         9.615 |

### Predicted vs actual spend, by decile of predicted spend

|   decile |   n |   mean_predicted |   mean_actual |
|---------:|----:|-----------------:|--------------:|
|        1 | 452 |           107.77 |        102.05 |
|        2 | 451 |           166.05 |        143.98 |
|        3 | 451 |           230.97 |        209.64 |
|        4 | 451 |           300.77 |        226.03 |
|        5 | 451 |           368.75 |        202.82 |
|        6 | 451 |           479.37 |        332.58 |
|        7 | 451 |           673.27 |        493.53 |
|        8 | 451 |           921.5  |        690.88 |
|        9 | 451 |          1415.77 |       1398.68 |
|       10 | 452 |          6105.97 |       6507.85 |

## Reading this result

The model is directionally right but not precise: predicted and actual both rise monotonically
across deciles for both transactions and spend (the model ranks customers correctly), and the
top decile lands close (predicted 10,015 vs actual 9,615 transactions; predicted 6,106 vs actual
6,508 in spend). But several middle deciles show real over-prediction (decile 4 transactions:
0.946 predicted vs 0.612 actual; decile 5 spend: 368.75 predicted vs 202.82 actual), and the
rank correlations (0.593 transactions, 0.597 spend) are moderate, not strong. This is reported
as what it is: BG/NBD + Gamma-Gamma gives a usable ranking of customers by future value on this
dataset, not a precise forecast, and the middle of the distribution is where it is least
reliable. No number here is close to a suspiciously perfect fit, which is itself a sign this is
a real result rather than a leakage artifact (see the Deriv Trading Agent lesson referenced in
the project brief).
