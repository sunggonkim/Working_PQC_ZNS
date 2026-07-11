#!/usr/bin/env python3
"""Create first paper-style figures from QUASAR JSON result files."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


POLICY_LABELS = {
    "fifo": "FIFO",
    "sepbit-style": "SepBIT-style",
    "midas-style": "MiDAS-style",
    "dogi-history": "DOGI-style",
    "quasar": "QUASAR",
    "epoch-oracle": "Epoch oracle",
}


def load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    print(f"wrote {path}")


def plot_e1(rows: list[dict], out_dir: Path) -> None:
    if not rows:
        return
    by_workload: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        by_workload[row["workload"]][row["policy"]] = row
    workloads = sorted(by_workload)
    preferred = ["fifo", "sepbit-style", "midas-style", "dogi-history", "quasar", "epoch-oracle"]
    policies = [policy for policy in preferred if any(policy in by_workload[w] for w in workloads)]
    width = min(0.14, 0.78 / max(1, len(policies)))
    xs = list(range(len(workloads)))
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for idx, policy in enumerate(policies):
        vals = [by_workload[w].get(policy, {}).get("waf", 0.0) for w in workloads]
        offsets = [x + (idx - (len(policies) - 1) / 2) * width for x in xs]
        ax.bar(offsets, vals, width=width, label=POLICY_LABELS.get(policy, policy))
    ax.set_ylabel("WAF")
    ax.set_xticks(xs)
    ax.set_xticklabels(workloads, rotation=20, ha="right")
    ax.set_title("E1: WAF across PQC workloads")
    ax.legend(ncol=2, fontsize=9)
    ax.grid(axis="y", alpha=0.25)
    save(fig, out_dir / "e1-waf.png")

    fig, ax = plt.subplots(figsize=(10, 4.2))
    exposure_policies = [policy for policy in ["fifo", "sepbit-style", "midas-style", "dogi-history", "quasar"] if any(policy in by_workload[w] for w in workloads)]
    exposure_width = min(0.14, 0.78 / max(1, len(exposure_policies)))
    for idx, policy in enumerate(exposure_policies):
        vals = [by_workload[w].get(policy, {}).get("stale_secret_block_seconds", 0.0) for w in workloads]
        offsets = [x + (idx - (len(exposure_policies) - 1) / 2) * exposure_width for x in xs]
        ax.bar(offsets, vals, width=exposure_width, label=POLICY_LABELS.get(policy, policy))
    ax.set_ylabel("Stale secret block-seconds")
    ax.set_xticks(xs)
    ax.set_xticklabels(workloads, rotation=20, ha="right")
    ax.set_title("E4 proxy: stale-secret exposure by workload")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.25)
    save(fig, out_dir / "e4-exposure.png")


def plot_e2(rows: list[dict], out_dir: Path) -> None:
    if not rows:
        return
    grouped: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[int(row["quasar_bin_width"])].append(row)
    fig, ax1 = plt.subplots(figsize=(8, 4.2))
    ax2 = ax1.twinx()
    for bin_width, vals in sorted(grouped.items()):
        vals = sorted(vals, key=lambda r: r["quasar_min_epoch_fill"])
        x = [r["quasar_min_epoch_fill"] for r in vals]
        ax1.plot(x, [r["waf"] for r in vals], marker="o", label=f"WAF bin={bin_width}")
        ax2.plot(x, [r["zone_utilization"] for r in vals], marker="x", linestyle="--", alpha=0.65)
    ax1.set_xlabel("min_epoch_zone_fill")
    ax1.set_ylabel("WAF")
    ax2.set_ylabel("Zone utilization")
    ax1.set_title("E2: WAF vs zone utilization")
    ax1.grid(alpha=0.25)
    ax1.legend(fontsize=8)
    save(fig, out_dir / "e2-waf-vs-utilization.png")


def plot_e5(rows: list[dict], out_dir: Path) -> None:
    if not rows:
        return
    rows = sorted(rows, key=lambda r: (r["hint_missing_rate"], r["wrong_epoch_rate"], r["straggler_rate"]))
    labels = [
        f"m{r['hint_missing_rate']:.2f}\\nw{r['wrong_epoch_rate']:.2f}\\ns{r['straggler_rate']:.2f}"
        for r in rows
    ]
    xs = list(range(len(rows)))
    fig, ax1 = plt.subplots(figsize=(10, 4.2))
    ax2 = ax1.twinx()
    ax1.bar(xs, [r["waf"] for r in rows], color="#4C78A8", alpha=0.8, label="WAF")
    ax2.plot(xs, [r["stale_secret_blocks_remaining"] for r in rows], color="#E45756", marker="o", label="Stale secrets")
    ax1.set_ylabel("WAF")
    ax2.set_ylabel("Stale secret blocks")
    ax1.set_xticks(xs)
    ax1.set_xticklabels(labels, fontsize=8)
    ax1.set_title("E5: robustness to missing/wrong hints and stragglers")
    ax1.grid(axis="y", alpha=0.25)
    save(fig, out_dir / "e5-bad-hints.png")


def plot_e0(rows: list[dict], out_dir: Path) -> None:
    if not rows:
        return
    policies = [r["policy"] for r in rows]
    xs = list(range(len(rows)))
    fig, ax = plt.subplots(figsize=(7, 4.0))
    ax.bar(xs, [r["estimated_mean_write_service_ns"] for r in rows], color="#72B7B2")
    ax.set_xticks(xs)
    ax.set_xticklabels([POLICY_LABELS.get(p, p) for p in policies], rotation=15, ha="right")
    ax.set_ylabel("Estimated mean service time (ns)")
    ax.set_title("E3 proxy: policy and GC service cost")
    ax.grid(axis="y", alpha=0.25)
    save(fig, out_dir / "e3-service-cost.png")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--e0", type=Path, default=Path("artifacts/results/schema-test-runner/e0-sanity.json"))
    parser.add_argument("--e1", type=Path, default=Path("artifacts/results/e1-workloads.json"))
    parser.add_argument("--e2", type=Path, default=Path("artifacts/results/schema-test-runner/e2-waf-vs-utilization.json"))
    parser.add_argument("--e5", type=Path, default=Path("artifacts/results/schema-test-runner/e5-bad-hints.json"))
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/figures"))
    args = parser.parse_args()

    plot_e0(load_json(args.e0), args.out_dir)
    plot_e1(load_json(args.e1), args.out_dir)
    plot_e2(load_json(args.e2), args.out_dir)
    plot_e5(load_json(args.e5), args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
