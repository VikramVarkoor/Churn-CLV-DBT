"""
K-means segmentation on log-scaled, standardized RFM. See docs/design.md, Phase 3
implementation decisions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

RFM_COLUMNS = ["recency_days", "frequency", "monetary_net"]


def prepare_matrix(df: pd.DataFrame) -> dict:
    """Log1p-transforms and standardizes recency_days/frequency/monetary_net. monetary_net
    is clipped to >= 0 first (see docs/design.md) since log1p is undefined below -1; the
    clip count is returned so it's reported, not silently applied.

    Returns {"X": ndarray, "n_clipped_monetary": int}.
    """
    raw = df[RFM_COLUMNS].to_numpy(dtype=float).copy()
    monetary_col = RFM_COLUMNS.index("monetary_net")
    n_clipped = int((raw[:, monetary_col] < 0).sum())
    raw[:, monetary_col] = np.clip(raw[:, monetary_col], 0, None)
    logged = np.log1p(raw)
    X = StandardScaler().fit_transform(logged)
    return {"X": X, "n_clipped_monetary": n_clipped}


def choose_k(X: np.ndarray, k_grid: range = range(3, 9), random_state: int = 42) -> dict:
    """Fits k-means for each k in k_grid, scores each by silhouette, returns all trials
    plus the winning k (highest silhouette). Each fit uses n_init=10 for stability of the
    fit itself (separate from the bootstrap-ARI stability check across resamples)."""
    trials = []
    for k in k_grid:
        km = KMeans(n_clusters=k, n_init=10, random_state=random_state)
        labels = km.fit_predict(X)
        sil = silhouette_score(X, labels)
        sizes = pd.Series(labels).value_counts().sort_index()
        trials.append({
            "k": k,
            "silhouette": float(sil),
            "cluster_sizes": sizes.to_dict(),
            "min_cluster_share": float(sizes.min() / len(labels)),
        })
    best = max(trials, key=lambda t: t["silhouette"])
    return {"trials": trials, "best_k": best["k"]}


def fit_final(X: np.ndarray, k: int, random_state: int = 42) -> dict:
    km = KMeans(n_clusters=k, n_init=10, random_state=random_state)
    labels = km.fit_predict(X)
    sil = silhouette_score(X, labels)
    return {"model": km, "labels": labels, "silhouette": float(sil)}


def bootstrap_ari(
    X: np.ndarray,
    full_labels: np.ndarray,
    k: int,
    n_boot: int = 200,
    random_state: int = 42,
) -> dict:
    """Refits k-means on n_boot bootstrap resamples (rows, with replacement) of X, computes
    the adjusted Rand index between each resample's own labels and the full-population
    labels restricted to that resample's rows. Measures whether the chosen k produces the
    same partition under resampling, not just a locally good silhouette score."""
    rng = np.random.RandomState(random_state)
    n = X.shape[0]
    aris = []
    for i in range(n_boot):
        idx = rng.randint(0, n, size=n)
        X_boot = X[idx]
        km = KMeans(n_clusters=k, n_init=5, random_state=random_state + i)
        boot_labels = km.fit_predict(X_boot)
        reference_labels = full_labels[idx]
        aris.append(adjusted_rand_score(reference_labels, boot_labels))
    aris = np.array(aris)
    return {
        "mean_ari": float(aris.mean()),
        "ci_lower": float(np.percentile(aris, 2.5)),
        "ci_upper": float(np.percentile(aris, 97.5)),
        "n_boot": n_boot,
    }


def segment_profile(df: pd.DataFrame, labels: np.ndarray) -> pd.DataFrame:
    """Per-segment summary stats used to NAME segments from their own numbers (never a fixed
    label list, per docs/design.md)."""
    out = df.copy()
    out["segment"] = labels
    profile = out.groupby("segment").agg(
        n_customers=("recency_days", "size"),
        mean_recency_days=("recency_days", "mean"),
        mean_frequency=("frequency", "mean"),
        mean_monetary_net=("monetary_net", "mean"),
        total_monetary_net=("monetary_net", "sum"),
        share_wholesaler=("is_wholesaler", "mean"),
    )
    profile["share_of_customers"] = profile["n_customers"] / profile["n_customers"].sum()
    profile["share_of_revenue"] = profile["total_monetary_net"] / profile["total_monetary_net"].sum()
    return profile.sort_values("mean_monetary_net", ascending=False)
