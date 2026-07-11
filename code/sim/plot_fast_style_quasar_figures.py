#!/usr/bin/env python3
"""Generate FAST-style paper figures for the QUASAR draft.

These plots are intentionally different from the raw artifact plots.  Each
figure answers one reviewer question, following the structure used by DOGI and
the previous local paper drafts: main failure, workload breadth, component
attribution, sensitivity, overhead, and robustness.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt


plt.rcParams.update(
    {
        "font.size": 8,
        "axes.titlesize": 9,
        "axes.labelsize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)


POLICY_LABELS = {
    "fifo": "FIFO",
    "sepbit-style": "SepBIT",
    "midas-style": "MiDAS",
    "dogi-history": "DOGI-style",
    "quasar": "QUASAR",
    "quasar-dogi-hybrid": "QUASAR-DOGI",
}

COLORS = {
    "fifo": "#8E8E8E",
    "sepbit-style": "#9C755F",
    "midas-style": "#B279A2",
    "dogi-history": "#4C78A8",
    "quasar": "#F58518",
    "quasar-dogi-hybrid": "#54A24B",
    "stale": "#E45756",
    "reset": "#72B7B2",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rect = getattr(fig, "_tight_layout_rect", None)
    if rect is None:
        fig.tight_layout()
    else:
        fig.tight_layout(rect=rect)
    fig.savefig(path)
    if path.suffix == ".pdf":
        fig.savefig(path.with_suffix(".png"), dpi=220)
    plt.close(fig)
    print(f"wrote {path}")


def short_ycsb_label(row: dict[str, Any]) -> str:
    names = row.get("workloads", [])
    level = row.get("pqc_level", 0)
    if len(names) == 2:
        return f"A/F\n{level // 1000}K"
    name = names[0] if names else "ycsb"
    flavor = "A" if "ycsb-a" in name else "F"
    return f"{flavor}\n{level // 1000}K"


def plot_intro_failure(curve: dict[str, Any], out: Path) -> None:
    rows = curve["rows"]
    selected = [row for row in rows if short_ycsb_label(row) in {"A/F\n2K", "A\n4K", "F\n8K", "F\n10K"}]
    if len(selected) != 4:
        selected = rows

    policies = ["fifo", "sepbit-style", "midas-style", "dogi-history", "quasar-dogi-hybrid"]
    labels = [short_ycsb_label(row) for row in selected]
    xs = list(range(len(selected)))
    width = 0.14
    offsets = [(idx - (len(policies) - 1) / 2) * width for idx in range(len(policies))]

    def row_value(row: dict[str, Any], policy: str, metric: str) -> int:
        if policy == "quasar-dogi-hybrid":
            return row["hybrid_gc_blocks" if metric == "gc" else "hybrid_stale_secret_blocks"]
        baseline = row["baseline_semantic_failures"][policy]
        return baseline["gc_blocks" if metric == "gc" else "stale_secret_blocks"]

    fig, axes = plt.subplots(1, 2, figsize=(6.9, 2.55), sharey=False)
    for ax, metric, ylabel, title in [
        (axes[0], "gc", "GC blocks", "GC pressure"),
        (axes[1], "stale", "Stale secret blocks", "Expired-secret exposure"),
    ]:
        for offset, policy in zip(offsets, policies):
            values = [row_value(row, policy, metric) for row in selected]
            bar_x = [x + offset for x in xs]
            ax.bar(
                bar_x,
                values,
                width,
                label=POLICY_LABELS[policy],
                color=COLORS[policy],
            )
            if policy == "quasar-dogi-hybrid":
                ax.scatter(bar_x, values, s=12, marker="v", color=COLORS[policy], zorder=3)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_xticks(xs)
        ax.set_xticklabels(labels)
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_xlabel("YCSB + PQC overlay")
    axes[1].set_xlabel("YCSB + PQC overlay")
    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="upper center", ncol=5, frameon=False, bbox_to_anchor=(0.5, 0.99))
    setattr(fig, "_tight_layout_rect", (0.0, 0.0, 1.0, 0.90))
    save(fig, out)


def dynamic_rows(dynamic: dict[str, Any], sysbench: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    sys_policies = {}
    for key, value in sysbench["physical"]["by_policy_packing"].items():
        policy, packing = key.split("::", 1)
        if packing == "secret-group":
            sys_policies[policy] = {
                "physical_waf": value["sim_waf"],
                "sim_gc_blocks": value["sim_gc_blocks"],
                "sim_stale_secret_blocks": value["sim_stale_secret_blocks"],
                "secret_blocks_waiting_for_physical_reset": value[
                    "secret_blocks_waiting_for_physical_reset"
                ],
                "physical_reset_commands": value["physical_reset_commands"],
                "avg_space_utilization": value["avg_space_utilization"],
            }
    rows.append(("Sysbench", sys_policies))
    for item in dynamic["physical"]:
        trace = Path(item["traces"][0]).stem
        if trace.startswith("exchange"):
            label = "Exchange"
        elif trace.startswith("varmail"):
            label = "Varmail"
        elif trace.startswith("alibaba"):
            label = "Alibaba"
        else:
            label = trace
        rows.append((label, item["policies"]))
    return rows


def plot_pressure_breadth(dynamic: dict[str, Any], sysbench: dict[str, Any], out: Path) -> None:
    rows = dynamic_rows(dynamic, sysbench)
    policies = ["dogi-history", "midas-style", "sepbit-style", "quasar-dogi-hybrid"]
    xs = list(range(len(rows)))
    width = 0.18
    offsets = [(-1.5 + i) * width for i in range(len(policies))]

    fig, axes = plt.subplots(2, 1, figsize=(7.1, 4.6), sharex=True)
    for offset, policy in zip(offsets, policies):
        axes[0].bar(
            [x + offset for x in xs],
            [entry[1][policy]["sim_gc_blocks"] for entry in rows],
            width,
            label=POLICY_LABELS[policy],
            color=COLORS[policy],
        )
        axes[1].bar(
            [x + offset for x in xs],
            [entry[1][policy]["sim_stale_secret_blocks"] for entry in rows],
            width,
            label=POLICY_LABELS[policy],
            color=COLORS[policy],
        )
    axes[0].set_ylabel("GC blocks")
    axes[0].set_title("FAST-style pressure workloads: GC and exposure move together")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend(ncol=4, fontsize=7, frameon=False)
    axes[1].set_ylabel("Stale secret blocks")
    axes[1].set_xticks(xs)
    axes[1].set_xticklabels([label for label, _ in rows])
    axes[1].grid(axis="y", alpha=0.25)
    save(fig, out)


def plot_component_ablation(ablation: dict[str, Any], out: Path) -> None:
    rows = [row for row in ablation["main_components"] if row["policy"] != "component delta"]
    workloads = []
    for row in rows:
        if row["workload"] not in workloads:
            workloads.append(row["workload"])
    policies = [
        "history-only DOGI-style",
        "lifecycle hints only",
        "hints + DOGI payload fallback",
    ]
    labels = ["DOGI-style", "Hints only", "Hints + DOGI payload"]
    colors = ["#4C78A8", "#F58518", "#54A24B"]
    xs = list(range(len(workloads)))
    width = 0.24

    by_key = {(row["workload"], row["policy"]): row for row in rows}
    fig, axes = plt.subplots(2, 1, figsize=(7.1, 4.6), sharex=True)
    for i, (policy, label, color) in enumerate(zip(policies, labels, colors)):
        offset = (i - 1) * width
        axes[0].bar(
            [x + offset for x in xs],
            [by_key[(workload, policy)]["gc_blocks"] for workload in workloads],
            width,
            label=label,
            color=color,
        )
        axes[1].bar(
            [x + offset for x in xs],
            [by_key[(workload, policy)]["stale_secret_blocks"] for workload in workloads],
            width,
            label=label,
            color=color,
        )
    axes[0].set_ylabel("GC blocks")
    axes[0].set_title("Component ablation: hints remove exposure, payload fallback removes GC")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend(ncol=3, fontsize=7, frameon=False)
    axes[1].set_ylabel("Stale secret blocks")
    axes[1].set_xticks(xs)
    axes[1].set_xticklabels(["YCSB-A", "Sysbench", "Exchange"])
    axes[1].grid(axis="y", alpha=0.25)
    save(fig, out)


def plot_space_sensitivity(rows: list[dict[str, Any]], out: Path) -> None:
    dogi = next(row for row in rows if row.get("policy") == "dogi-history" and not row.get("failed"))
    hybrids = [row for row in rows if row.get("policy") == "quasar-dogi-hybrid" and not row.get("failed")]

    fig, ax = plt.subplots(figsize=(4.9, 3.4))
    x = [row["closed_zone_fill_avg"] for row in hybrids]
    y = [row["waf"] for row in hybrids]
    open_budget = [row.get("quasar_open_zone_budget") or 0 for row in hybrids]
    sc = ax.scatter(x, y, c=open_budget, s=46, cmap="viridis", edgecolor="white", linewidth=0.5)
    ax.scatter(
        [dogi["closed_zone_fill_avg"]],
        [dogi["waf"]],
        marker="X",
        s=130,
        color=COLORS["stale"],
        label=f"DOGI-style stale={dogi['stale_secret_blocks_remaining']:,}",
        zorder=3,
    )
    ax.set_xlabel("Closed-zone fill")
    ax.set_ylabel("WAF")
    ax.set_title("Space tradeoff is bounded, not hidden")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7, loc="upper left", frameon=False)
    cbar = fig.colorbar(sc, ax=ax, pad=0.02)
    cbar.set_label("Open-zone budget", fontsize=8)
    cbar.ax.tick_params(labelsize=7)
    save(fig, out)


def plot_overhead(overhead: dict[str, Any], xnvme: dict[str, Any], out: Path) -> None:
    policies = ["dogi-history", "quasar-dogi-hybrid", "quasar"]
    labels = ["DOGI-style\nMLP", "Hybrid", "QUASAR\nhint"]
    cpu = [
        overhead["by_policy"][policy]["cpu_policy"]["median_ns_per_write"]
        for policy in policies
    ]
    resets = [
        overhead["by_policy"][policy]["semantic_physical_reset_commands"]
        for policy in policies
    ]
    x = list(range(len(policies)))

    fig, axes = plt.subplots(1, 2, figsize=(7.05, 2.65))
    axes[0].bar(x, cpu, color=[COLORS["dogi-history"], COLORS["quasar-dogi-hybrid"], COLORS["quasar"]])
    axes[0].set_yscale("log")
    axes[0].set_ylabel("Policy cost (ns/write, log)")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels)
    axes[0].set_title("Policy decision cost")
    axes[0].grid(axis="y", alpha=0.25)

    reset_x = [0, 1]
    axes[1].bar(reset_x, [xnvme["append_p50_ns"] / 1000.0, xnvme["append_p99_ns"] / 1000.0], color="#4C78A8")
    axes[1].set_xticks(reset_x)
    axes[1].set_xticklabels(["append\np50", "append\np99"])
    axes[1].set_ylabel("xNVMe append latency (us)")
    axes[1].set_title("xNVMe append latency")
    axes[1].grid(axis="y", alpha=0.25)
    save(fig, out)


def plot_resource_overhead(
    rows: list[dict[str, Any]],
    overhead: dict[str, Any],
    xnvme: dict[str, Any],
    out: Path,
) -> None:
    dogi = next(row for row in rows if row.get("policy") == "dogi-history" and not row.get("failed"))
    hybrids = [row for row in rows if row.get("policy") == "quasar-dogi-hybrid" and not row.get("failed")]
    policies = ["dogi-history", "quasar-dogi-hybrid", "quasar"]
    labels = ["DOGI-style\nMLP", "Hybrid", "QUASAR\nhint"]
    cpu = [
        overhead["by_policy"][policy]["cpu_policy"]["median_ns_per_write"]
        for policy in policies
    ]

    fig, axes = plt.subplots(1, 3, figsize=(7.15, 2.45))

    ax = axes[0]
    ax.scatter(
        [row["closed_zone_fill_avg"] for row in hybrids],
        [row["waf"] for row in hybrids],
        s=28,
        color=COLORS["quasar-dogi-hybrid"],
        alpha=0.85,
        edgecolor="white",
        linewidth=0.4,
        label="QUASAR-DOGI",
    )
    ax.scatter(
        [dogi["closed_zone_fill_avg"]],
        [dogi["waf"]],
        marker="X",
        s=90,
        color=COLORS["stale"],
        label="DOGI-style",
        zorder=3,
    )
    ax.set_xlabel("Closed-zone fill")
    ax.set_ylabel("WAF")
    ax.set_title("Space tradeoff")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=6, frameon=False, loc="upper left")

    ax = axes[1]
    ax.bar(range(len(policies)), cpu, color=[COLORS["dogi-history"], COLORS["quasar-dogi-hybrid"], COLORS["quasar"]])
    ax.set_yscale("log")
    ax.set_xticks(range(len(policies)))
    ax.set_xticklabels(labels)
    ax.set_ylabel("ns/write, log")
    ax.set_title("Decision cost")
    ax.grid(axis="y", alpha=0.25)

    ax = axes[2]
    ax.bar(
        [0, 1],
        [xnvme["append_p50_ns"] / 1000.0, xnvme["append_p99_ns"] / 1000.0],
        color="#4C78A8",
    )
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["append\np50", "append\np99"])
    ax.set_ylabel("us")
    ax.set_title("xNVMe append")
    ax.grid(axis="y", alpha=0.25)
    save(fig, out)


def plot_robustness(ablation: dict[str, Any], out: Path) -> None:
    residual = ablation["residual_fallback"]
    cases = [
        ("Exact", residual["exact_secret_group"], None),
        ("Bin", residual["epoch_bin_no_residual"], None),
        ("Bin+copy", residual["epoch_bin_with_residual"], residual["epoch_bin_with_residual"]["physical_waf"]),
        ("Strict", residual["strict_ycsb_f_boundary"], residual["strict_ycsb_f_boundary"]["physical_waf"]),
    ]
    waiting = [case[1].get("secret_waiting_end", 0) for case in cases]
    waf = [case[2] if case[2] is not None else 0 for case in cases]
    copied = [case[1].get("residual_migrated_blocks", 0) for case in cases]
    x = list(range(len(cases)))

    fig, axes = plt.subplots(1, 3, figsize=(7.15, 2.65))
    axes[0].bar(x, waiting, color=COLORS["stale"])
    axes[0].set_ylabel("Waiting secret blocks")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels([case[0] for case in cases])
    axes[0].set_title("Exposure fallback")
    axes[0].grid(axis="y", alpha=0.25)

    axes[1].bar(x, waf, color="#F58518")
    axes[1].set_ylabel("Physical WAF")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([case[0] for case in cases])
    axes[1].set_title("Strict mode cost")
    axes[1].grid(axis="y", alpha=0.25)

    axes[2].bar(x, copied, color="#4C78A8")
    axes[2].set_ylabel("Residual copied blocks")
    axes[2].set_xticks(x)
    axes[2].set_xticklabels([case[0] for case in cases])
    axes[2].set_title("Copy cost exposed")
    axes[2].grid(axis="y", alpha=0.25)
    save(fig, out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/figures/fast-style"))
    parser.add_argument("--ycsb", type=Path, default=Path("artifacts/results/fast-ycsb-pressure/ycsb-actual-zns-pressure-curve.json"))
    parser.add_argument("--dynamic", type=Path, default=Path("artifacts/results/fast-dynamic-pressure/dynamic-pressure-summary.json"))
    parser.add_argument("--sysbench", type=Path, default=Path("artifacts/results/fast-db-pressure/sysbench-pressure-summary.json"))
    parser.add_argument("--ablation", type=Path, default=Path("artifacts/results/component-ablation.json"))
    parser.add_argument("--space", type=Path, default=Path("artifacts/results/dogi-paper-workloads-smoke/space-sensitivity-tight-open.json"))
    parser.add_argument("--overhead", type=Path, default=Path("artifacts/results/actual-zns-overhead-summary.json"))
    parser.add_argument("--xnvme", type=Path, default=Path("artifacts/results/xnvme-zns-latency/summary.json"))
    args = parser.parse_args()

    plot_intro_failure(load_json(args.ycsb), args.out_dir / "fig1-intro-pressure.pdf")
    plot_pressure_breadth(load_json(args.dynamic), load_json(args.sysbench), args.out_dir / "fig2-pressure-breadth.pdf")
    plot_component_ablation(load_json(args.ablation), args.out_dir / "fig3-component-ablation.pdf")
    plot_space_sensitivity(load_json(args.space), args.out_dir / "fig4-space-sensitivity.pdf")
    plot_overhead(load_json(args.overhead), load_json(args.xnvme), args.out_dir / "fig5-overhead.pdf")
    plot_resource_overhead(
        load_json(args.space),
        load_json(args.overhead),
        load_json(args.xnvme),
        args.out_dir / "fig4-resource-overhead.pdf",
    )
    plot_robustness(load_json(args.ablation), args.out_dir / "fig6-robustness.pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
