# Phase 2 results

Generated: 2026-10-10

Validation cutoff: 2010-12-01. Train cutoff A: 2011-03-01. Test cutoff B: 2011-09-01 (evaluated once, below).

## Class balance

- validation (2010-12-01): n=4239, churned=2832, churn_rate=0.668
- train_A (2011-03-01): n=4512, churned=2927, churn_rate=0.649
- test_B (2011-09-01): n=5224, churned=2988, churn_rate=0.572

## Recency rule

Threshold tuned on validation cutoff (2010-12-01) only, maximizing Youden's J (TPR - FPR), not F1 -- F1-argmax degenerates under this population's class balance, see BUGLOG.md entry 5: X = 49 days (validation J = 0.303, TPR = 0.591, FPR = 0.289).
At this threshold on test cutoff B: precision=0.673, recall=0.885, tp=2643, fp=1284, fn=345.
Calibration: not reported for the recency rule -- a raw day count is not a probability (see docs/design.md).

## LightGBM tuning (validation cutoff only, never touches B)

- params={'num_leaves': 7, 'learning_rate': 0.1, 'min_child_samples': 20}, best_iteration=14, val_pr_auc=0.863
- params={'num_leaves': 15, 'learning_rate': 0.05, 'min_child_samples': 20}, best_iteration=46, val_pr_auc=0.864
- params={'num_leaves': 31, 'learning_rate': 0.05, 'min_child_samples': 10}, best_iteration=23, val_pr_auc=0.862
- params={'num_leaves': 15, 'learning_rate': 0.1, 'min_child_samples': 10}, best_iteration=20, val_pr_auc=0.863
Winner: params={'num_leaves': 15, 'learning_rate': 0.05, 'min_child_samples': 20}, iterations=46, val_pr_auc=0.864

## Results on test cutoff B (evaluated once)

| Model | PR-AUC (95% CI) | ROC-AUC (95% CI) | Lift @ top decile | Capture @ top decile | Brier score |
|---|---|---|---|---|---|
| recency_rule | 0.801 [0.785, 0.816] (n_boot_used=1000) | 0.760 [0.748, 0.774] (n_boot_used=1000) | 1.59x | 0.159 | N/A |
| logistic_rfm | 0.813 [0.798, 0.829] (n_boot_used=1000) | 0.787 [0.775, 0.799] (n_boot_used=1000) | 1.59x | 0.159 | 0.196 |
| lightgbm | 0.814 [0.799, 0.830] (n_boot_used=1000) | 0.794 [0.782, 0.806] (n_boot_used=1000) | 1.60x | 0.160 | 0.191 |

## Calibration tables

### Logistic regression (RFM)

| bin        |    n |   mean_predicted |   observed_churn_rate |
|:-----------|-----:|-----------------:|----------------------:|
| [0.0, 0.1) |  312 |        0.0332369 |             0.0929487 |
| [0.1, 0.2) |  155 |        0.148926  |             0.129032  |
| [0.2, 0.3) |  192 |        0.254746  |             0.21875   |
| [0.3, 0.4) |  220 |        0.348948  |             0.231818  |
| [0.4, 0.5) |  326 |        0.452663  |             0.328221  |
| [0.5, 0.6) |  429 |        0.554818  |             0.426573  |
| [0.6, 0.7) |  715 |        0.653628  |             0.495105  |
| [0.7, 0.8) |  686 |        0.750162  |             0.637026  |
| [0.8, 0.9) | 1106 |        0.858669  |             0.748644  |
| [0.9, 1.0) | 1083 |        0.941783  |             0.865189  |

### LightGBM

| bin        |    n |   mean_predicted |   observed_churn_rate |
|:-----------|-----:|-----------------:|----------------------:|
| [0.1, 0.2) |  387 |         0.135401 |             0.0542636 |
| [0.2, 0.3) |  221 |         0.254538 |             0.19457   |
| [0.3, 0.4) |  280 |         0.352317 |             0.160714  |
| [0.4, 0.5) |  230 |         0.452895 |             0.321739  |
| [0.5, 0.6) |  363 |         0.55821  |             0.415978  |
| [0.6, 0.7) |  594 |         0.656772 |             0.506734  |
| [0.7, 0.8) |  972 |         0.750812 |             0.623457  |
| [0.8, 0.9) | 1584 |         0.84065  |             0.76452   |
| [0.9, 1.0) |  593 |         0.912283 |             0.903879  |

## Success criterion (docs/design.md)

LightGBM PR-AUC CI lower bound (0.799) vs recency rule PR-AUC CI upper bound (0.816): overlapping or not clearly ahead -- per the brief's ground rules, this is reported plainly, not glossed over.

## Reading this result

PR-AUC confidence intervals overlap across all three models (recency rule, logistic regression on
RFM, and LightGBM). LightGBM's point estimate is highest (0.814 vs 0.801 for the recency rule),
but its CI lower bound (0.799) sits below the recency rule's CI upper bound (0.816), so this is not
a statistically clear win. Logistic regression and LightGBM are also indistinguishable from each
other (0.813 vs 0.814, fully overlapping). Per docs/design.md's own success criterion, this is
reported as what it is: neither the gradient boosting model nor the logistic regression baseline
clearly beats the simple recency rule on this dataset and label definition. See README.md for the
plain statement of this result.
