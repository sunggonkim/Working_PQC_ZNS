#!/usr/bin/env python3
"""Plot actual-ZNS comparison figures for the QUASAR paper path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    print(f"wrote {path}")


def plot_ycsb_pressure(curve: dict[str, Any], out: Path) -> None:
    rows = curve.get("rows", [])
    labels = ["+".join(name.replace("ycsb-", "") for name in row.get("workloads", [])) for row in rows]
    xs = list(range(len(rows)))
    dogi_waf = [row.get("dogi_waf", 0.0) for row in rows]
    hybrid_waf = [row.get("hybrid_waf", 0.0) for row in rows]
    dogi_stale = [row.get("dogi_stale_secret_blocks", 0) for row in rows]
    hybrid_stale = [row.get("hybrid_stale_secret_blocks", 0) for row in rows]

    fig, (ax0, ax1) = plt.subplots(2, 1, figsize=(9.2, 6.4), sharex=True)
    width = 0.34
    ax0.bar([x - width / 2 for x in xs], dogi_waf, width=width, label="DOGI-style", color="#4C78A8")
    ax0.bar([x + width / 2 for x in xs], hybrid_waf, width=width, label="QUASAR-DOGI", color="#54A24B")
    ax0.set_ylabel("WAF")
    ax0.set_title("Actual ZNS YCSB pressure: WAF is pressure-dependent")
    ax0.grid(axis="y", alpha=0.25)
    ax0.legend(fontsize=9)

    ax1.bar([x - width / 2 for x in xs], dogi_stale, width=width, label="DOGI-style", color="#E45756")
    ax1.bar([x + width / 2 for x in xs], hybrid_stale, width=width, label="QUASAR-DOGI", color="#72B7B2")
    ax1.set_ylabel("Stale secret blocks")
    ax1.set_xticks(xs)
    ax1.set_xticklabels(labels, rotation=18, ha="right")
    ax1.grid(axis="y", alpha=0.25)
    save(fig, out)


def plot_overhead(overhead: dict[str, Any], out: Path) -> None:
    policies = ["dogi-history", "quasar", "quasar-dogi-hybrid"]
    labels = ["DOGI-style", "QUASAR", "Hybrid"]
    rows = overhead.get("by_policy", {})
    throughput = [rows.get(policy, {}).get("throughput_mib_s", 0.0) for policy in policies]
    cpu_ns = [
        rows.get(policy, {}).get("cpu_policy", {}).get("median_ns_per_write", 0.0)
        for policy in policies
    ]
    resets = [rows.get(policy, {}).get("semantic_physical_reset_commands", 0) for policy in policies]
    xs = list(range(len(policies)))

    fig, axes = plt.subplots(3, 1, figsize=(7.8, 7.4), sharex=True)
    axes[0].bar(xs, throughput, color="#4C78A8")
    axes[0].set_ylabel("MiB/s")
    axes[0].set_title("Actual ZNS overhead accounting")
    axes[0].grid(axis="y", alpha=0.25)

    axes[1].bar(xs, cpu_ns, color="#F58518")
    axes[1].set_ylabel("CPU ns/write")
    axes[1].grid(axis="y", alpha=0.25)

    axes[2].bar(xs, resets, color="#54A24B")
    axes[2].set_ylabel("Semantic resets")
    axes[2].set_xticks(xs)
    axes[2].set_xticklabels(labels)
    axes[2].grid(axis="y", alpha=0.25)
    save(fig, out)


def plot_workload_hardness(hardness: dict[str, Any], out: Path) -> None:
    entries = hardness.get("entries", [])
    labels = [_hardness_label(entry.get("name", "")) for entry in entries]
    tiers = [entry.get("tier", "") for entry in entries]
    colors = {
        "fairness": "#4C78A8",
        "negative-control": "#B279A2",
        "pressure": "#E45756",
        "hostile-robustness": "#F58518",
    }
    xs = list(range(len(entries)))
    heights = [1 if entry.get("passed") else 0 for entry in entries]
    fig, ax = plt.subplots(figsize=(10.5, 4.6))
    ax.bar(xs, heights, color=[colors.get(tier, "#999999") for tier in tiers])
    ax.set_ylim(0, 1.2)
    ax.set_ylabel("Pass")
    ax.set_title("Workload hardness matrix: easy controls, pressure, and hostile cases")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=0, ha="center", fontsize=8)
    ax.grid(axis="y", alpha=0.25)
    save(fig, out)


def plot_space_sensitivity(rows: list[dict[str, Any]], out: Path) -> None:
    baseline = [row for row in rows if row.get("policy") == "dogi-history" and not row.get("failed")]
    hybrids = [row for row in rows if row.get("policy") == "quasar-dogi-hybrid" and not row.get("failed")]
    if not baseline or not hybrids:
        raise ValueError("space sensitivity plot requires one DOGI row and hybrid candidates")

    dogi = baseline[0]
    hybrid_x = [row.get("closed_zone_fill_avg", 0.0) for row in hybrids]
    hybrid_y = [row.get("waf", 0.0) for row in hybrids]
    hybrid_open = [row.get("quasar_open_zone_budget", 0) or 0 for row in hybrids]

    fig, ax = plt.subplots(figsize=(5.2, 3.25))
    scatter = ax.scatter(
        hybrid_x,
        hybrid_y,
        c=hybrid_open,
        cmap="viridis",
        s=42,
        alpha=0.85,
        edgecolor="white",
        linewidth=0.45,
        label="QUASAR-DOGI candidates (stale=0)",
    )
    ax.scatter(
        [dogi.get("closed_zone_fill_avg", 0.0)],
        [dogi.get("waf", 0.0)],
        color="#E45756",
        marker="X",
        s=120,
        label=f"DOGI-style (stale={dogi.get('stale_secret_blocks_remaining', 0):,})",
        zorder=5,
    )
    ax.set_xlabel("Closed-zone fill")
    ax.set_ylabel("WAF")
    ax.set_title("WAF vs. utilization under tight open-zone budget")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, loc="upper left")
    cbar = fig.colorbar(scatter, ax=ax, pad=0.015)
    cbar.set_label("Open-zone budget", fontsize=8)
    cbar.ax.tick_params(labelsize=8)
    save(fig, out)


def _hardness_label(name: str) -> str:
    """Return compact paper labels for the workload-hardness guardrail figure."""
    lowered = name.lower()
    if "fairness" in lowered:
        return "DOGI\nfairness"
    if "non-pqc" in lowered:
        return "non-PQC\ncontrol"
    if "p2000" in lowered:
        return "p2000\nnegative"
    if "ycsb" in lowered:
        return "YCSB\npressure"
    if "sysbench" in lowered:
        return "Sysbench\nDB"
    if "eligibility" in lowered:
        return "claim\ngate"
    if "multi-tenant" in lowered:
        return "tenant\npressure"
    if "bad-hint" in lowered or "straggler" in lowered:
        return "bad hints /\nstragglers"
    if "residual" in lowered:
        return "residual\nfrontier"
    words = name.split()
    return "\n".join(words[:2]) if words else "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ycsb-curve",
        type=Path,
        default=Path("artifacts/results/fast-ycsb-pressure/ycsb-actual-zns-pressure-curve.json"),
    )
    parser.add_argument("--overhead", type=Path, default=Path("artifacts/results/actual-zns-overhead-summary.json"))
    parser.add_argument("--hardness", type=Path, default=Path("artifacts/results/workload-hardness-matrix.json"))
    parser.add_argument(
        "--space-sensitivity",
        type=Path,
        default=Path("artifacts/results/dogi-paper-workloads-smoke/space-sensitivity-tight-open.json"),
    )
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/figures/actual-zns"))
    args = parser.parse_args()

    plot_ycsb_pressure(load_json(args.ycsb_curve), args.out_dir / "ycsb-pressure-waf-stale.png")
    plot_overhead(load_json(args.overhead), args.out_dir / "overhead-accounting.png")
    plot_workload_hardness(load_json(args.hardness), args.out_dir / "workload-hardness.png")
    plot_space_sensitivity(load_json(args.space_sensitivity), args.out_dir / "space-sensitivity.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
