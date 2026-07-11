#!/usr/bin/env python3
"""Plot DOGI-paper-shaped PQC ratio sweep results.

The ratio sweep is the main sanity check that keeps QUASAR from being
overclaimed: low PQC ratios should mostly match DOGI, while nontrivial PQC
metadata should show GC and exposure benefits.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def ratio_label(ratio: float) -> str:
    return f"{ratio * 100:.0f}%"


def percent_or_nan(value) -> float:
    if value is None:
        return math.nan
    return float(value) * 100.0


def save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    print(f"wrote {path}")


def plot_main(summary: dict, out: Path) -> None:
    rows = sorted(summary["ratio_summary"], key=lambda row: row["ratio"])
    ratios = [row["ratio"] for row in rows]
    xs = list(range(len(rows)))

    fig, axes = plt.subplots(3, 1, figsize=(9, 9), sharex=True)

    axes[0].plot(
        xs,
        [percent_or_nan(row["avg_waf_reduction_vs_dogi"]) for row in rows],
        marker="o",
        linewidth=2.0,
        label="WAF vs DOGI",
    )
    axes[0].plot(
        xs,
        [percent_or_nan(row["avg_waf_reduction_vs_best_history"]) for row in rows],
        marker="s",
        linewidth=1.8,
        label="WAF vs best history",
    )
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set_ylabel("WAF reduction (%)")
    axes[0].set_title("PQC ratio sweep: WAF benefit is workload-pressure dependent")
    axes[0].legend(fontsize=9)
    axes[0].grid(alpha=0.25)

    axes[1].plot(
        xs,
        [percent_or_nan(row["aggregate_gc_reduction_vs_dogi"]) for row in rows],
        marker="o",
        color="#4C78A8",
        linewidth=2.0,
    )
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_ylabel("Aggregate GC reduction (%)")
    axes[1].grid(alpha=0.25)

    axes[2].bar(xs, [row["stale_avoided"] for row in rows], color="#E45756", alpha=0.85)
    axes[2].set_ylabel("Stale secrets avoided")
    axes[2].set_xlabel("PQC metadata ratio")
    axes[2].set_xticks(xs)
    axes[2].set_xticklabels([ratio_label(ratio) for ratio in ratios])
    axes[2].grid(axis="y", alpha=0.25)

    save(fig, out)


def group_eval_by_ratio(eval_rows: list[dict]) -> dict[float, dict[str, list[dict]]]:
    grouped: dict[float, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in eval_rows:
        workload = row["workload"]
        if "-pqc" not in workload:
            continue
        ratio_token = workload.rsplit("-pqc", 1)[1]
        ratio = int(ratio_token) / 10000.0
        grouped[ratio][row["policy"]].append(row)
    return grouped


def avg(rows: list[dict], key: str) -> float:
    vals = [float(row.get(key, 0.0)) for row in rows]
    return sum(vals) / len(vals) if vals else 0.0


def plot_space(eval_rows: list[dict], out: Path) -> None:
    grouped = group_eval_by_ratio(eval_rows)
    ratios = sorted(grouped)
    xs = list(range(len(ratios)))

    dogi_waf = [avg(grouped[ratio].get("dogi-history", []), "waf") for ratio in ratios]
    hybrid_waf = [avg(grouped[ratio].get("quasar-dogi-hybrid", []), "waf") for ratio in ratios]
    dogi_util = [avg(grouped[ratio].get("dogi-history", []), "lifetime_zone_utilization") for ratio in ratios]
    hybrid_util = [avg(grouped[ratio].get("quasar-dogi-hybrid", []), "lifetime_zone_utilization") for ratio in ratios]
    dogi_fill = [avg(grouped[ratio].get("dogi-history", []), "closed_zone_fill_avg") for ratio in ratios]
    hybrid_fill = [avg(grouped[ratio].get("quasar-dogi-hybrid", []), "closed_zone_fill_avg") for ratio in ratios]

    fig, axes = plt.subplots(2, 1, figsize=(9, 6.8), sharex=True)
    axes[0].plot(xs, dogi_waf, marker="o", label="DOGI WAF", linewidth=2.0)
    axes[0].plot(xs, hybrid_waf, marker="s", label="Hybrid WAF", linewidth=2.0)
    axes[0].set_ylabel("Average WAF")
    axes[0].set_title("PQC ratio sweep: WAF vs space behavior")
    axes[0].legend(fontsize=9)
    axes[0].grid(alpha=0.25)

    axes[1].plot(xs, dogi_util, marker="o", label="DOGI lifetime zone utilization", linewidth=2.0)
    axes[1].plot(xs, hybrid_util, marker="s", label="Hybrid lifetime zone utilization", linewidth=2.0)
    axes[1].plot(xs, dogi_fill, marker="o", linestyle="--", label="DOGI closed-zone fill", alpha=0.7)
    axes[1].plot(xs, hybrid_fill, marker="s", linestyle="--", label="Hybrid closed-zone fill", alpha=0.7)
    axes[1].set_ylabel("Utilization / fill")
    axes[1].set_xlabel("PQC metadata ratio")
    axes[1].set_xticks(xs)
    axes[1].set_xticklabels([ratio_label(ratio) for ratio in ratios])
    axes[1].legend(fontsize=8, ncol=2)
    axes[1].grid(alpha=0.25)

    save(fig, out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--eval", type=Path, required=True)
    parser.add_argument("--main-figure", type=Path, required=True)
    parser.add_argument("--space-figure", type=Path, required=True)
    args = parser.parse_args()

    summary = load_json(args.summary)
    eval_rows = load_json(args.eval)
    plot_main(summary, args.main_figure)
    plot_space(eval_rows, args.space_figure)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
