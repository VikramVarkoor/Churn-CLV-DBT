# Phase 3 segmentation results

Generated: 2026-10-10

Snapshot cutoff: 2011-09-01 (mart_customer_features). 53 of 5224 customers are flagged wholesalers under the design.md rule (0.010 of the population).

## Wholesaler comparison

With wholesalers: chosen k=4, silhouette=0.376, stability mean ARI=0.955.
Without wholesalers: chosen k=4, silhouette=0.377, stability mean ARI=0.955.

### All customers

n_customers=5224, monetary_net values clipped to 0 before log transform: 3.
RFM quintile bins actually used (5 = no ties collapsed any bin edge): recency=5, frequency=4, monetary=5.

K-means model selection (k=3..8, by silhouette score):

| k | silhouette | min cluster share | cluster sizes |
|---|---|---|---|
| 3 | 0.353 | 0.183 | {0: 2032, 1: 2238, 2: 954} |
| 4 | 0.376 | 0.148 | {0: 2068, 1: 774, 2: 860, 3: 1522} |
| 5 | 0.327 | 0.102 | {0: 692, 1: 1023, 2: 1566, 3: 534, 4: 1409} |
| 6 | 0.313 | 0.074 | {0: 938, 1: 1290, 2: 577, 3: 385, 4: 641, 5: 1393} |
| 7 | 0.284 | 0.065 | {0: 1096, 1: 341, 2: 581, 3: 808, 4: 607, 5: 502, 6: 1289} |
| 8 | 0.286 | 0.063 | {0: 687, 1: 329, 2: 660, 3: 624, 4: 1312, 5: 425, 6: 364, 7: 823} |

Chosen k = 4 (highest silhouette, 0.376).
Bootstrap-ARI stability (n_boot=200): mean=0.955, 95% interval [0.890, 0.991].

Segment profile (sorted by mean monetary_net, highest first; segment IDs are arbitrary k-means labels, not ranked names):

|   segment |   n_customers |   mean_recency_days |   mean_frequency |   mean_monetary_net |   total_monetary_net |   share_wholesaler |   share_of_customers |   share_of_revenue |
|----------:|--------------:|--------------------:|------------------:|--------------------:|---------------------:|-------------------:|---------------------:|-------------------:|
|         2 |           860 |              33.198 |            19.265 |           10314.8   |          8.87076e+06 |               0.053 |                0.165 |              0.681 |
|         3 |          1522 |             202.141 |             5.13  |            1864.95  |          2.83846e+06 |               0.004 |                0.291 |              0.218 |
|         1 |           774 |              35.655 |             2.948 |             826.246 |     639515           |               0     |                0.148 |              0.049 |
|         0 |          2068 |             339.621 |             1.391 |             327.465 |     677197           |               0     |                0.396 |              0.052 |

### Excluding flagged wholesalers

n_customers=5171, monetary_net values clipped to 0 before log transform: 3.
RFM quintile bins actually used (5 = no ties collapsed any bin edge): recency=5, frequency=4, monetary=5.

K-means model selection (k=3..8, by silhouette score):

| k | silhouette | min cluster share | cluster sizes |
|---|---|---|---|
| 3 | 0.352 | 0.193 | {0: 2190, 1: 1983, 2: 998} |
| 4 | 0.377 | 0.143 | {0: 742, 1: 1991, 2: 927, 3: 1511} |
| 5 | 0.324 | 0.119 | {0: 686, 1: 1351, 2: 1516, 3: 1002, 4: 616} |
| 6 | 0.316 | 0.079 | {0: 916, 1: 1393, 2: 409, 3: 540, 4: 1286, 5: 627} |
| 7 | 0.287 | 0.073 | {0: 1308, 1: 377, 2: 652, 3: 681, 4: 569, 5: 1092, 6: 492} |
| 8 | 0.288 | 0.067 | {0: 401, 1: 623, 2: 649, 3: 863, 4: 348, 5: 375, 6: 598, 7: 1314} |

Chosen k = 4 (highest silhouette, 0.377).
Bootstrap-ARI stability (n_boot=200): mean=0.955, 95% interval [0.891, 0.992].

Segment profile (sorted by mean monetary_net, highest first; segment IDs are arbitrary k-means labels, not ranked names):

|   segment |   n_customers |   mean_recency_days |   mean_frequency |   mean_monetary_net |   total_monetary_net |   share_wholesaler |   share_of_customers |   share_of_revenue |
|----------:|--------------:|--------------------:|------------------:|--------------------:|---------------------:|-------------------:|---------------------:|-------------------:|
|         2 |           927 |              35.419 |            15.173 |            5964.65  |          5.52923e+06 |                   0 |                0.179 |              0.599 |
|         3 |          1511 |             212.169 |             4.866 |            1673.73  |          2.52901e+06 |                   0 |                0.292 |              0.274 |
|         0 |           742 |              37.801 |             2.732 |             739.914 |     549016           |                   0 |                0.143 |              0.059 |
|         1 |          1991 |             341.842 |             1.355 |             312.333 |     621855           |                   0 |                0.385 |              0.067 |

## Reading this result

Excluding the 53 flagged wholesalers changes almost nothing about the cluster structure itself:
the same k=4 wins by silhouette either way, silhouette and stability (mean ARI ~0.955, a tight
95% interval) are essentially identical with or without them. What does change is the top
segment's economics: with wholesalers included, the top segment holds 68.1% of total revenue
from 16.5% of customers; excluding wholesalers, that drops to 59.9% of revenue from 17.9% of
customers, and the top segment's mean spend roughly halves (10,315 to 5,965). So wholesalers are
not reshaping the segmentation, they're concentrating revenue within whichever segment they fall
into -- a small number of extreme accounts inflating one segment's totals without changing how
many natural groups the broader population splits into. This matches the real duplicate/anomaly
pattern already seen in Phase 0's audit: a few extreme accounts, not a systemic data issue.

Across both runs, the same four-segment shape recurs: a small high-value, recently-active
segment (~16-18% of customers, driving roughly 60-68% of revenue), a mid-value lapsing segment
(~29% of customers, recency over 200 days), a smaller lower-value recent segment, and a large
dormant/one-time segment (~38-40% of customers, recency over 300 days, frequency near 1). This
is a standard, defensible Pareto-shaped customer base, not an unusual or suspicious split.

3 customers had monetary_net <= 0 in the real data and were clipped to 0 before the log
transform (see docs/design.md) -- this was flagged as a real possibility before seeing real data,
not discovered after the fact, and it did occur.
