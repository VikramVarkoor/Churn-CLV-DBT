"""
Phase 3 segmentation: RFM quintile scoring and k-means on cutoff B's snapshot
(mart_customer_features, 2011-09-01), run twice (all customers, and excluding flagged
wholesalers), with silhouette-based k selection and bootstrap-ARI stability. Writes
docs/evidence/p3_segments.md.

Usage (from the project root, inside the venv):
    python3 python/run_phase3_segments.py

Requires `dbt build --vars '{cutoff_date: "2011-09-01"}'` to have already been run.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from segment import data, kmeans, rfm  # noqa: E402

SNAPSHOT_CUTOFF = "2011-09-01"
N_BOOT = 200


def run_pipeline(df, label: str) -> dict:
    rfm_result = rfm.score(df)
    prep = kmeans.prepare_matrix(df)
    k_result = kmeans.choose_k(prep["X"])
    final = kmeans.fit_final(prep["X"], k_result["best_k"])
    stability = kmeans.bootstrap_ari(prep["X"], final["labels"], k_result["best_k"], n_boot=N_BOOT)
    profile = kmeans.segment_profile(df, final["labels"])
    return {
        "label": label,
        "n_customers": len(df),
        "n_clipped_monetary": prep["n_clipped_monetary"],
        "rfm_bins_used": rfm_result["bins_used"],
        "k_trials": k_result["trials"],
        "best_k": k_result["best_k"],
        "final_silhouette": final["silhouette"],
        "stability": stability,
        "profile": profile,
    }


def format_run(run: dict) -> list[str]:
    lines = []
    lines.append(f"### {run['label']}\n")
    lines.append(f"n_customers={run['n_customers']}, monetary_net values clipped to 0 before "
                  f"log transform: {run['n_clipped_monetary']}.")
    lines.append(f"RFM quintile bins actually used (5 = no ties collapsed any bin edge): "
                 f"recency={run['rfm_bins_used']['r']}, frequency={run['rfm_bins_used']['f']}, "
                 f"monetary={run['rfm_bins_used']['m']}.")
    lines.append("")
    lines.append("K-means model selection (k=3..8, by silhouette score):\n")
    lines.append("| k | silhouette | min cluster share | cluster sizes |")
    lines.append("|---|---|---|---|")
    for t in run["k_trials"]:
        lines.append(f"| {t['k']} | {t['silhouette']:.3f} | {t['min_cluster_share']:.3f} | "
                      f"{t['cluster_sizes']} |")
    lines.append("")
    lines.append(f"Chosen k = {run['best_k']} (highest silhouette, {run['final_silhouette']:.3f}).")
    s = run["stability"]
    lines.append(
        f"Bootstrap-ARI stability (n_boot={s['n_boot']}): mean={s['mean_ari']:.3f}, "
        f"95% interval [{s['ci_lower']:.3f}, {s['ci_upper']:.3f}]."
    )
    lines.append("")
    lines.append("Segment profile (sorted by mean monetary_net, highest first; segment IDs are "
                  "arbitrary k-means labels, not ranked names):\n")
    lines.append(run["profile"].round(3).to_markdown())
    lines.append("")
    return lines


def main() -> None:
    con = data.connect()
    df_all = data.load_snapshot(con, SNAPSHOT_CUTOFF)
    con.close()

    df_no_wholesale = df_all[~df_all["is_wholesaler"]].reset_index(drop=True)
    n_wholesalers = int(df_all["is_wholesaler"].sum())

    run_all = run_pipeline(df_all, "All customers")
    run_excl = run_pipeline(df_no_wholesale, "Excluding flagged wholesalers")

    lines = []
    lines.append("# Phase 3 segmentation results\n")
    lines.append(f"Generated: {dt.date.today().isoformat()}\n")
    lines.append(f"Snapshot cutoff: {SNAPSHOT_CUTOFF} (mart_customer_features). {n_wholesalers} "
                  f"of {len(df_all)} customers are flagged wholesalers under the design.md rule "
                  f"({n_wholesalers / len(df_all):.3f} of the population).\n")
    lines.append("## Wholesaler comparison\n")
    lines.append(f"With wholesalers: chosen k={run_all['best_k']}, silhouette="
                  f"{run_all['final_silhouette']:.3f}, stability mean ARI="
                  f"{run_all['stability']['mean_ari']:.3f}.")
    lines.append(f"Without wholesalers: chosen k={run_excl['best_k']}, silhouette="
                  f"{run_excl['final_silhouette']:.3f}, stability mean ARI="
                  f"{run_excl['stability']['mean_ari']:.3f}.")
    lines.append("")
    lines.extend(format_run(run_all))
    lines.extend(format_run(run_excl))

    report = "\n".join(lines) + "\n"
    out_path = Path("docs/evidence/p3_segments.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    print(report)
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
