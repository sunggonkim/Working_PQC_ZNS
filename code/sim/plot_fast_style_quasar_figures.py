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
from collections import Counter
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
        "figure.dpi": 120,
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
    "pqc-secret": "#E45756",
    "pqc-rotation": "#F58518",
    "pqc-log": "#72B7B2",
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
    fig.savefig(path, bbox_inches="tight", pad_inches=0.02)
    if path.suffix == ".pdf":
        fig.savefig(path.with_suffix(".png"), dpi=220, bbox_inches="tight", pad_inches=0.02)
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


def pqc_pressure_label(row: dict[str, Any]) -> str:
    names = row.get("workloads", [])
    level = row.get("pqc_level", 0) // 1000
    if len(names) == 2:
        carrier = "A/F carrier"
    else:
        name = names[0] if names else ""
        carrier = "A carrier" if "ycsb-a" in name else "F carrier"
    return f"PQC {level}K\n{carrier}"


def carrier_label(label: str) -> str:
    mapping = {
        "Sysbench": "PQC-DB",
        "Exchange": "PQC-mail",
        "Varmail": "PQC-files",
        "Alibaba": "PQC-tenant",
    }
    return mapping.get(label, f"PQC-{label}")


def component_workload_label(label: str) -> str:
    if "YCSB" in label:
        return "PQC-YCSB"
    if "Sysbench" in label:
        return "PQC-DB"
    if "Exchange" in label:
        return "PQC-mail"
    return label.replace(" pqc", "\npqc")


def overhead_trace_label(label: str) -> str:
    if "kms" in label:
        return "KMS"
    if "exchange" in label:
        return "PQC-mail"
    if "trace.jsonl" in label:
        return "TLS"
    return label.replace(".jsonl", "")


def row_trace_paths(row: dict[str, Any]) -> list[Path]:
    artifact = row.get("artifact")
    if not artifact:
        return []
    artifact_path = Path(artifact)
    if not artifact_path.exists():
        return []
    artifact_json = load_json(artifact_path)
    return [Path(path) for path in artifact_json.get("traces", [])]


def pqc_lifecycle_blocks(row: dict[str, Any]) -> Counter[str]:
    blocks: Counter[str] = Counter()
    for trace_path in row_trace_paths(row):
        if not trace_path.exists():
            continue
        with trace_path.open("r", encoding="utf-8") as src:
            for line in src:
                if not line.strip():
                    continue
                event = json.loads(line)
                intent = event.get("intent")
                size = int(event.get("size_blocks", 1))
                if intent in {"EPHEMERAL_SECRET", "KEM_ARTIFACT"}:
                    blocks["Epoch secrets"] += size
                elif intent == "CERT_METADATA":
                    blocks["Rotation metadata"] += size
                elif intent == "SIGNATURE_LOG":
                    blocks["Signature logs"] += size
    return blocks


def compact_count(value: float) -> str:
    value = float(value)
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000:
        return f"{sign}{value / 1_000_000:.1f}M"
    if value >= 100_000:
        return f"{sign}{value / 1000:.0f}K"
    if value >= 10_000:
        return f"{sign}{value / 1000:.1f}K"
    if value >= 1000:
        return f"{sign}{value / 1000:.1f}K"
    return f"{sign}{int(round(value))}"


def compact_value(value: float, kind: str = "count") -> str:
    if kind == "waf":
        return f"{value:.3f}"
    if kind == "latency":
        return f"{value:.1f}"
    if kind == "ratio":
        return f"{value:.2f}"
    return compact_count(value)


def annotate_bars(
    ax: plt.Axes,
    bars: Any,
    *,
    kind: str = "count",
    include_zero: bool = False,
    rotation: int = 90,
    fontsize: float = 5.2,
) -> None:
    # Paper figures should stay visually clean; exact values live in tables and text.
    return
    heights = [float(bar.get_height()) for bar in bars]
    positive = [height for height in heights if height > 0]
    max_height = max(positive or [1.0])
    if ax.get_yscale() == "log":
        bottom, top = ax.get_ylim()
        ax.set_ylim(bottom, max(top, max_height * 2.2))
        for bar, height in zip(bars, heights):
            if height <= 0 and not include_zero:
                continue
            y = max(height, bottom) * 1.18
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                y,
                compact_value(height, kind),
                ha="center",
                va="bottom",
                rotation=rotation,
                fontsize=fontsize,
                clip_on=False,
            )
        return

    bottom, top = ax.get_ylim()
    top = max(top, max_height * 1.26)
    ax.set_ylim(bottom, top)
    y_offset = top * 0.018
    for bar, height in zip(bars, heights):
        if height == 0 and not include_zero:
            continue
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            height + y_offset,
            compact_value(height, kind),
            ha="center",
            va="bottom",
            rotation=rotation,
            fontsize=fontsize,
            clip_on=False,
        )


def annotate_points(
    ax: plt.Axes,
    xs: list[float],
    ys: list[float],
    labels: list[str],
    *,
    fontsize: float = 5.4,
) -> None:
    # Paper figures should stay visually clean; exact values live in tables and text.
    return
    for x, y, label in zip(xs, ys, labels):
        ax.annotate(
            label,
            (x, y),
            xytext=(3, 3),
            textcoords="offset points",
            fontsize=fontsize,
            clip_on=False,
        )


def plot_intro_failure(curve: dict[str, Any], out: Path) -> None:
    rows = curve["rows"]
    selected = [row for row in rows if short_ycsb_label(row) in {"A/F\n2K", "A\n4K", "F\n8K", "F\n10K"}]
    if len(selected) != 4:
        selected = rows

    labels = [pqc_pressure_label(row) for row in selected]
    xs = list(range(len(selected)))

    fig, ax = plt.subplots(figsize=(3.55, 2.15))

    lifecycle_summaries = [pqc_lifecycle_blocks(row) for row in selected]
    lifecycle_groups = [
        ("Epoch secrets", COLORS["pqc-secret"]),
        ("Rotation metadata", COLORS["pqc-rotation"]),
        ("Signature logs", COLORS["pqc-log"]),
    ]
    bottoms = [0.0 for _ in selected]
    for group, color in lifecycle_groups:
        values = [summary[group] for summary in lifecycle_summaries]
        ax.bar(xs, values, 0.55, bottom=bottoms, label=group, color=color)
        bottoms = [bottom + value for bottom, value in zip(bottoms, values)]
    ax.set_title("PQC lifecycle side writes")
    ax.set_ylabel("PQC blocks written")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(ncol=1, fontsize=5.8, frameon=False, loc="upper left")
    save(fig, out)


def plot_fairness_matrix_subfigs(out_dir: Path) -> None:
    policies = ["fifo", "sepbit-style", "midas-style", "dogi-history", "quasar", "quasar-dogi-hybrid"]
    labels = [POLICY_LABELS[p] for p in policies]
    waf = {
        "fifo": 1.0040,
        "sepbit-style": 1.0023,
        "midas-style": 1.0006,
        "dogi-history": 1.0006,
        "quasar": 1.0011,
        "quasar-dogi-hybrid": 1.0001,
    }
    gc = {
        "fifo": 3903,
        "sepbit-style": 2241,
        "midas-style": 581,
        "dogi-history": 625,
        "quasar": 1121,
        "quasar-dogi-hybrid": 106,
    }
    stale = {
        "fifo": 99141,
        "sepbit-style": 99822,
        "midas-style": 99898,
        "dogi-history": 99834,
        "quasar": 0,
        "quasar-dogi-hybrid": 0,
    }
    reset = {
        "fifo": 0,
        "sepbit-style": 0,
        "midas-style": 0,
        "dogi-history": 0,
        "quasar": 98,
        "quasar-dogi-hybrid": 98,
    }
    xs = list(range(len(policies)))

    fig, ax = plt.subplots(figsize=(3.35, 2.1))
    bars = ax.bar(xs, [waf[p] for p in policies], color=[COLORS[p] for p in policies])
    ax.set_ylim(0.998, 1.006)
    ax.set_ylabel("WAF")
    ax.set_title("DOGI-axis control")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.grid(axis="y", alpha=0.25)
    annotate_bars(ax, bars, kind="waf", rotation=90, fontsize=4.8)
    save(fig, out_dir / "fig2-fairness-waf.pdf")

    fig, ax = plt.subplots(figsize=(3.35, 2.1))
    width = 0.36
    gc_bars = ax.bar([x - width / 2 for x in xs], [gc[p] for p in policies], width, label="GC", color="#4C78A8")
    stale_bars = ax.bar([x + width / 2 for x in xs], [stale[p] for p in policies], width, label="Expired secrets", color=COLORS["stale"])
    ax.set_yscale("log")
    ax.set_ylim(1, 220000)
    ax.set_ylabel("Blocks (log)")
    ax.set_title("WAF is not the whole story")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(fontsize=5.8, frameon=False, loc="upper left")
    annotate_bars(ax, gc_bars, include_zero=True, fontsize=4.7)
    annotate_bars(ax, stale_bars, include_zero=True, fontsize=4.7)
    save(fig, out_dir / "fig2-fairness-gc-stale.pdf")

    fig, ax = plt.subplots(figsize=(3.35, 2.1))
    bars = ax.bar(xs, [reset[p] for p in policies], color=[COLORS[p] for p in policies])
    ax.set_ylabel("Semantic resets")
    ax.set_title("Only semantic placement resets PQC cohorts")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.grid(axis="y", alpha=0.25)
    annotate_bars(ax, bars, include_zero=True, rotation=0, fontsize=5.2)
    save(fig, out_dir / "fig2-fairness-resets.pdf")


def plot_service_pressure_allbaseline_subfigs(dynamic: dict[str, Any], sysbench: dict[str, Any], out_dir: Path) -> None:
    rows = dynamic_rows(dynamic, sysbench)
    policies = ["fifo", "sepbit-style", "midas-style", "dogi-history", "quasar", "quasar-dogi-hybrid"]
    xs = list(range(len(rows)))
    width = 0.12
    offsets = [(-2.5 + i) * width for i in range(len(policies))]
    panels = [
        ("fig2-service-allbaseline-waf.pdf", "physical_waf", "WAF", "All-baseline WAF on PQC service pressure", "waf", False),
        ("fig2-service-allbaseline-gc.pdf", "sim_gc_blocks", "GC blocks", "GC from mixed PQC cohorts", "count", True),
        (
            "fig2-service-allbaseline-secrets.pdf",
            "sim_stale_secret_blocks",
            "Expired PQC secrets",
            "Expired PQC secrets stranded",
            "count",
            True,
        ),
    ]
    for filename, key, ylabel, title, kind, log_scale in panels:
        fig, ax = plt.subplots(figsize=(3.35, 1.75))
        all_values: list[float] = []
        for offset, policy in zip(offsets, policies):
            values = [entry[1][policy][key] for entry in rows]
            all_values.extend(values)
            bars = ax.bar(
                [x + offset for x in xs],
                values,
                width,
                label=POLICY_LABELS[policy],
                color=COLORS[policy],
            )
            annotate_bars(
                ax,
                bars,
                kind=kind,
                include_zero=(policy in {"quasar", "quasar-dogi-hybrid"}),
                fontsize=4.2,
                rotation=90,
            )
        if kind == "waf":
            ax.set_ylim(0.995, max(all_values) + 0.025)
        if log_scale:
            ax.set_yscale("log")
            ax.set_ylim(1, max(all_values) * 3.0)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_xticks(xs)
        ax.set_xticklabels([carrier_label(label) for label, _ in rows], rotation=12, ha="right")
        ax.grid(axis="y", alpha=0.25)
        if filename.endswith("waf.pdf"):
            ax.legend(ncol=2, fontsize=5.2, frameon=False, loc="upper left")
        save(fig, out_dir / filename)


def selected_ycsb_rows(curve: dict[str, Any]) -> list[dict[str, Any]]:
    wanted = {
        ("ycsb-a", 4000),
        ("ycsb-a", 6000),
        ("ycsb-a", 10000),
        ("ycsb-f", 6000),
        ("ycsb-f", 8000),
        ("ycsb-f", 10000),
    }
    selected = []
    for row in curve["rows"]:
        names = row.get("workloads", [])
        if len(names) != 1:
            continue
        base = "ycsb-a" if "ycsb-a" in names[0] else "ycsb-f"
        if (base, row.get("pqc_level")) in wanted:
            selected.append(row)
    return selected


def plot_ycsb_pressure_subfigs(curve: dict[str, Any], out_dir: Path) -> None:
    rows = selected_ycsb_rows(curve)
    labels = [short_ycsb_label(row) for row in rows]
    xs = list(range(len(rows)))
    width = 0.34

    panels = [
        ("fig3-ycsb-pressure-waf.pdf", "dogi_waf", "hybrid_waf", "WAF", "YCSB carrier WAF", "waf"),
        ("fig3-ycsb-pressure-gc.pdf", "dogi_gc_blocks", "hybrid_gc_blocks", "GC blocks", "GC from PQC cohort mixing", "count"),
        (
            "fig3-ycsb-pressure-secrets.pdf",
            "dogi_stale_secret_blocks",
            "hybrid_stale_secret_blocks",
            "Expired PQC secrets",
            "Expired secrets stranded",
            "count",
        ),
    ]
    for filename, dogi_key, hybrid_key, ylabel, title, kind in panels:
        fig, ax = plt.subplots(figsize=(3.35, 2.1))
        dogi_vals = [row[dogi_key] for row in rows]
        hybrid_vals = [row[hybrid_key] for row in rows]
        if kind == "waf":
            ax.set_ylim(0.995, max(dogi_vals + hybrid_vals) + 0.010)
        dogi_bars = ax.bar([x - width / 2 for x in xs], dogi_vals, width, label="DOGI-style", color=COLORS["dogi-history"])
        hybrid_bars = ax.bar([x + width / 2 for x in xs], hybrid_vals, width, label="QUASAR-DOGI", color=COLORS["quasar-dogi-hybrid"])
        if kind == "count" and max(dogi_vals + hybrid_vals) > 50000:
            ax.set_yscale("log")
            ax.set_ylim(1, max(dogi_vals + hybrid_vals) * 2.5)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.set_xticks(xs)
        ax.set_xticklabels(labels)
        ax.grid(axis="y", alpha=0.25)
        ax.legend(fontsize=5.8, frameon=False, loc="upper left")
        annotate_bars(ax, dogi_bars, kind=kind, include_zero=True, fontsize=4.7)
        annotate_bars(ax, hybrid_bars, kind=kind, include_zero=True, fontsize=4.7)
        save(fig, out_dir / filename)


def ycsb_policy_rows(path: Path) -> dict[str, dict[str, Any]]:
    artifact = load_json(path)
    rows: dict[str, dict[str, Any]] = {}
    for row in artifact["rows"]:
        rows[row["policy"]] = row["sim"]
    return rows


def plot_ycsb_allbaseline_subfigs(out_dir: Path) -> None:
    workloads = [
        ("YCSB-F\n8K", Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc8000-z733-helper.json")),
        ("YCSB-A\n10K", Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc10000-z1024-helper.json")),
        ("YCSB-F\n10K", Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc10000-z900-helper.json")),
    ]
    rows = [(label, ycsb_policy_rows(path)) for label, path in workloads]
    policies = ["fifo", "sepbit-style", "midas-style", "dogi-history", "quasar", "quasar-dogi-hybrid"]
    xs = list(range(len(rows)))
    width = 0.12
    offsets = [(-2.5 + i) * width for i in range(len(policies))]
    panels = [
        ("fig3-ycsb-allbaseline-waf.pdf", "waf", "WAF", "All-baseline WAF on PQC-YCSB pressure", "waf", False),
        ("fig3-ycsb-allbaseline-gc.pdf", "gc_write_blocks", "GC blocks", "GC from PQC-YCSB mixing", "count", True),
        (
            "fig3-ycsb-allbaseline-secrets.pdf",
            "stale_secret_blocks_remaining",
            "Expired PQC secrets",
            "Expired secrets stranded",
            "count",
            True,
        ),
    ]
    for filename, key, ylabel, title, kind, log_scale in panels:
        fig, ax = plt.subplots(figsize=(3.35, 1.75))
        all_values: list[float] = []
        for offset, policy in zip(offsets, policies):
            values = [entry[1][policy][key] for entry in rows]
            all_values.extend(values)
            bars = ax.bar(
                [x + offset for x in xs],
                values,
                width,
                label=POLICY_LABELS[policy],
                color=COLORS[policy],
            )
            annotate_bars(
                ax,
                bars,
                kind=kind,
                include_zero=(policy in {"quasar", "quasar-dogi-hybrid"}),
                fontsize=4.2,
                rotation=90,
            )
        if kind == "waf":
            ax.set_ylim(0.995, max(all_values) + 0.025)
        if log_scale:
            ax.set_yscale("log")
            ax.set_ylim(1, max(all_values) * 3.0)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_xticks(xs)
        ax.set_xticklabels([label for label, _ in rows])
        ax.grid(axis="y", alpha=0.25)
        if filename.endswith("waf.pdf"):
            ax.legend(ncol=2, fontsize=5.2, frameon=False, loc="upper left")
        save(fig, out_dir / filename)


def plot_ratio_sweep_subfigs(ratio: dict[str, Any], out_dir: Path) -> None:
    rows = ratio["ratio_summary"]
    xs = [row["ratio"] * 100 for row in rows]

    fig, ax = plt.subplots(figsize=(3.35, 2.1))
    ax.plot(xs, [row["avg_waf_reduction_vs_dogi"] * 100 for row in rows], marker="o", color=COLORS["quasar-dogi-hybrid"], label="WAF")
    ax.axhline(0, color="#6b7280", linewidth=0.8)
    ax.axvline(ratio["break_even_ratio"] * 100, color=COLORS["stale"], linewidth=0.9, linestyle="--", label="break-even")
    ax.set_xlabel("PQC overlay ratio (%)")
    ax.set_ylabel("WAF reduction vs DOGI (%)")
    ax.set_title("PQC pressure break-even")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=5.8, frameon=False, loc="upper left")
    save(fig, out_dir / "fig4-ratio-waf.pdf")

    fig, ax = plt.subplots(figsize=(3.35, 2.1))
    ax.plot(xs, [row["aggregate_gc_reduction_vs_dogi"] * 100 for row in rows], marker="s", color="#4C78A8", label="GC")
    ax.axhline(0, color="#6b7280", linewidth=0.8)
    ax.set_xlabel("PQC overlay ratio (%)")
    ax.set_ylabel("GC reduction vs DOGI (%)")
    ax.set_title("GC benefit appears under pressure")
    ax.grid(alpha=0.25)
    save(fig, out_dir / "fig4-ratio-gc.pdf")

    fig, ax = plt.subplots(figsize=(3.35, 2.1))
    bars = ax.bar(xs, [row["stale_avoided"] for row in rows], width=2.8, color=COLORS["stale"])
    ax.set_xlabel("PQC overlay ratio (%)")
    ax.set_ylabel("Expired secrets avoided")
    ax.set_title("Exposure improves before WAF")
    ax.grid(axis="y", alpha=0.25)
    annotate_bars(ax, bars, include_zero=True, fontsize=4.7)
    save(fig, out_dir / "fig4-ratio-secrets.pdf")


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

    fig, axes = plt.subplots(2, 1, figsize=(6.45, 3.45), sharex=True)
    for offset, policy in zip(offsets, policies):
        gc_bars = axes[0].bar(
            [x + offset for x in xs],
            [entry[1][policy]["sim_gc_blocks"] for entry in rows],
            width,
            label=POLICY_LABELS[policy],
            color=COLORS[policy],
        )
        stale_bars = axes[1].bar(
            [x + offset for x in xs],
            [entry[1][policy]["sim_stale_secret_blocks"] for entry in rows],
            width,
            label=POLICY_LABELS[policy],
            color=COLORS[policy],
        )
        annotate_bars(axes[0], gc_bars, include_zero=(policy == "quasar-dogi-hybrid"))
        annotate_bars(axes[1], stale_bars, include_zero=(policy == "quasar-dogi-hybrid"))
    axes[0].set_ylabel("GC blocks")
    axes[0].set_title("PQC lifecycle pressure carriers")
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].set_ylabel("Expired PQC secrets")
    axes[1].set_xticks(xs)
    axes[1].set_xticklabels([carrier_label(label) for label, _ in rows])
    axes[1].grid(axis="y", alpha=0.25)
    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.99))
    setattr(fig, "_tight_layout_rect", (0.0, 0.0, 1.0, 0.90))
    save(fig, out)


def plot_pressure_breadth_subfigs(dynamic: dict[str, Any], sysbench: dict[str, Any], out_dir: Path) -> None:
    rows = dynamic_rows(dynamic, sysbench)
    policies = ["dogi-history", "midas-style", "sepbit-style", "quasar-dogi-hybrid"]
    xs = list(range(len(rows)))
    width = 0.18
    offsets = [(-1.5 + i) * width for i in range(len(policies))]
    panels = [
        ("fig2-pressure-breadth-gc.pdf", "sim_gc_blocks", "GC blocks", "GC from mixed PQC cohorts", True),
        (
            "fig2-pressure-breadth-secrets.pdf",
            "sim_stale_secret_blocks",
            "Expired PQC secrets",
            "Expired secrets stranded",
            False,
        ),
    ]
    for filename, key, ylabel, title, show_legend in panels:
        fig, ax = plt.subplots(figsize=(3.35, 2.15))
        for offset, policy in zip(offsets, policies):
            bars = ax.bar(
                [x + offset for x in xs],
                [entry[1][policy][key] for entry in rows],
                width,
                label=POLICY_LABELS[policy],
                color=COLORS[policy],
            )
            annotate_bars(ax, bars, include_zero=(policy == "quasar-dogi-hybrid"), fontsize=4.7)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_xticks(xs)
        ax.set_xticklabels([carrier_label(label) for label, _ in rows])
        ax.grid(axis="y", alpha=0.25)
        if show_legend:
            ax.legend(ncol=2, fontsize=5.8, frameon=False, loc="upper left")
        save(fig, out_dir / filename)


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
    fig, axes = plt.subplots(2, 1, figsize=(6.45, 3.35), sharex=True)
    for i, (policy, label, color) in enumerate(zip(policies, labels, colors)):
        offset = (i - 1) * width
        gc_bars = axes[0].bar(
            [x + offset for x in xs],
            [by_key[(workload, policy)]["gc_blocks"] for workload in workloads],
            width,
            label=label,
            color=color,
        )
        stale_bars = axes[1].bar(
            [x + offset for x in xs],
            [by_key[(workload, policy)]["stale_secret_blocks"] for workload in workloads],
            width,
            label=label,
            color=color,
        )
        annotate_bars(axes[0], gc_bars, include_zero=("hints" in policy.lower()))
        annotate_bars(axes[1], stale_bars, include_zero=("hints" in policy.lower()))
    axes[0].set_ylabel("GC blocks")
    axes[0].set_title("PQC lifecycle signal ablation")
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].set_ylabel("Expired PQC secrets")
    axes[1].set_xticks(xs)
    axes[1].set_xticklabels(["PQC-YCSB", "PQC-DB", "PQC-mail"])
    axes[1].grid(axis="y", alpha=0.25)
    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 0.99))
    setattr(fig, "_tight_layout_rect", (0.0, 0.0, 1.0, 0.90))
    save(fig, out)


def plot_component_ablation_subfigs(ablation: dict[str, Any], out_dir: Path) -> None:
    rows = [row for row in ablation["main_components"] if row["policy"] != "component delta"]
    workloads = []
    for row in rows:
        if row["workload"] not in workloads:
            workloads.append(row["workload"])
    policies = ["history-only DOGI-style", "lifecycle hints only", "hints + DOGI payload fallback"]
    stage_labels = ["History", "+lifecycle", "+payload"]
    workload_colors = ["#4C78A8", "#F58518", "#54A24B"]
    markers = ["o", "s", "^"]
    xs = list(range(len(policies)))
    by_key = {(row["workload"], row["policy"]): row for row in rows}
    panels = [
        ("fig3-component-ablation-waf.pdf", "waf", "Physical WAF", "Incremental policy effect", False),
        ("fig3-component-ablation-gc.pdf", "gc_blocks", "GC blocks", "GC removed by components", True),
        (
            "fig3-component-ablation-secrets.pdf",
            "stale_secret_blocks",
            "Expired PQC secrets + 1",
            "Exposure removed by hints",
            False,
        ),
    ]
    for filename, key, ylabel, title, show_legend in panels:
        fig, ax = plt.subplots(figsize=(2.5, 1.85))
        for workload, color, marker in zip(workloads, workload_colors, markers):
            values = [by_key[(workload, policy)][key] for policy in policies]
            if key == "stale_secret_blocks":
                values = [value + 1 for value in values]
            ax.plot(xs, values, marker=marker, linewidth=1.6, markersize=4.2, label=component_workload_label(workload), color=color)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_xticks(xs)
        ax.set_xticklabels(stage_labels)
        if key == "stale_secret_blocks":
            ax.set_yscale("log")
            all_values = [by_key[(workload, policy)][key] + 1 for workload in workloads for policy in policies]
            ax.set_ylim(1, max(all_values) * 1.35)
        if key == "waf":
            values = [by_key[(workload, policy)][key] for workload in workloads for policy in policies]
            ax.set_ylim(max(0.995, min(values) - 0.004), max(values) + 0.008)
        ax.grid(axis="y", alpha=0.25)
        if show_legend:
            ax.legend(ncol=1, fontsize=5.7, frameon=False, loc="upper right")
        save(fig, out_dir / filename)


def plot_open_zone_robustness_subfigs(robustness: dict[str, Any], out_dir: Path) -> None:
    limit = robustness["device_limits"]["mor"]
    cases = [
        ("Clean", robustness["clean"]["hybrid"]),
        ("Missing", robustness["missing_hint_5pct"]["hybrid"]),
        ("Wrong", robustness["wrong_epoch_5pct"]["hybrid"]),
        ("Exact", robustness["straggler_5pct_exact_secret_group"]["hybrid"]),
        ("Bin", robustness["straggler_5pct_epoch_bin_4"]["hybrid"]),
        ("Bin+copy", robustness["straggler_5pct_epoch_bin_5_residual_12288"]["hybrid"]),
    ]
    labels = [case[0] for case in cases]
    x = list(range(len(cases)))
    panels = [
        (
            "fig6-open-zone-zones.pdf",
            [case[1]["max_live_physical_zones"] for case in cases],
            "Max live zones",
            "Open-zone budget",
            "#4C78A8",
            "limit",
        ),
        (
            "fig6-open-zone-waiting.pdf",
            [case[1]["secret_waiting_end"] + 1 for case in cases],
            "Waiting PQC secrets + 1",
            "Residual exposure",
            COLORS["stale"],
            "log",
        ),
        (
            "fig6-open-zone-waf.pdf",
            [case[1]["physical_waf"] for case in cases],
            "Physical WAF",
            "Strict-mode cost",
            "#F58518",
            "waf",
        ),
    ]
    for filename, values, ylabel, title, color, mode in panels:
        fig, ax = plt.subplots(figsize=(2.45, 1.9))
        ax.bar(x, values, color=color)
        if mode == "limit":
            ax.axhline(limit, color=COLORS["stale"], linestyle="--", linewidth=1.0, label="device limit")
            ax.legend(fontsize=5.7, frameon=False, loc="upper left")
        if mode == "log":
            ax.set_yscale("log")
        if mode == "waf":
            ax.set_ylim(0.95, max(values) + 0.20)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.grid(axis="y", alpha=0.25)
        save(fig, out_dir / filename)


def plot_prototype_overhead_subfigs(
    overhead: dict[str, Any],
    policy_overhead: dict[str, Any],
    out_dir: Path,
) -> None:
    policies = ["fifo", "sepbit-style", "midas-style", "dogi-history", "quasar", "quasar-dogi-hybrid"]
    fig, ax = plt.subplots(figsize=(3.35, 1.95))
    xs = list(range(len(policies)))
    ax.bar(xs, [overhead["by_policy"][policy]["throughput_mib_s"] for policy in policies], color=[COLORS[p] for p in policies])
    ax.set_title("Actual-ZNS replay throughput")
    ax.set_ylabel("MiB/s")
    ax.set_xticks(xs)
    ax.set_xticklabels([POLICY_LABELS[p].replace("-style", "") for p in policies], rotation=25, ha="right")
    ax.grid(axis="y", alpha=0.25)
    save(fig, out_dir / "fig7-prototype-throughput.pdf")

    trace_names = []
    for row in policy_overhead["rows"]:
        name = row["trace_name"]
        if name not in trace_names:
            trace_names.append(name)
    policy_order = ["dogi-mlp", "quasar-dogi-hybrid", "quasar-hint"]
    policy_labels = {"dogi-mlp": "DOGI MLP", "quasar-dogi-hybrid": "Hybrid", "quasar-hint": "QUASAR hint"}
    policy_colors = {"dogi-mlp": COLORS["dogi-history"], "quasar-dogi-hybrid": COLORS["quasar-dogi-hybrid"], "quasar-hint": COLORS["quasar"]}
    by_key = {(row["trace_name"], row["policy"]): row for row in policy_overhead["rows"]}
    width = 0.24
    fig, ax = plt.subplots(figsize=(3.35, 1.95))
    xs = list(range(len(trace_names)))
    for i, policy in enumerate(policy_order):
        offset = (i - 1) * width
        ax.bar(
            [x + offset for x in xs],
            [by_key[(trace, policy)]["ns_per_write_median"] for trace in trace_names],
            width,
            label=policy_labels[policy],
            color=policy_colors[policy],
        )
    ax.set_yscale("log")
    ax.set_title("Placement-decision cost")
    ax.set_ylabel("ns/write, log")
    ax.set_xticks(xs)
    ax.set_xticklabels([overhead_trace_label(name) for name in trace_names])
    ax.grid(axis="y", alpha=0.25)
    ax.legend(ncol=1, fontsize=5.7, frameon=False, loc="upper left")
    save(fig, out_dir / "fig7-decision-cost.pdf")


def plot_space_sensitivity(rows: list[dict[str, Any]], out: Path) -> None:
    dogi = next(row for row in rows if row.get("policy") == "dogi-history" and not row.get("failed"))
    hybrids = [row for row in rows if row.get("policy") == "quasar-dogi-hybrid" and not row.get("failed")]

    fig, ax = plt.subplots(figsize=(4.45, 2.75))
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
    representatives = hybrids[:2] + hybrids[len(hybrids) // 2 : len(hybrids) // 2 + 1] + hybrids[-2:]
    annotate_points(
        ax,
        [row["closed_zone_fill_avg"] for row in representatives],
        [row["waf"] for row in representatives],
        [f"b{row.get('quasar_open_zone_budget')}: {row['waf']:.3f}" for row in representatives],
    )
    annotate_points(
        ax,
        [dogi["closed_zone_fill_avg"]],
        [dogi["waf"]],
        [f"DOGI {dogi['waf']:.3f}\\nstale {compact_count(dogi['stale_secret_blocks_remaining'])}"],
        fontsize=5.6,
    )
    ax.set_xlabel("Closed-zone fill")
    ax.set_ylabel("WAF")
    ax.set_title("Space sensitivity")
    ax.set_xlim(
        min([row["closed_zone_fill_avg"] for row in hybrids] + [dogi["closed_zone_fill_avg"]]) - 0.006,
        max([row["closed_zone_fill_avg"] for row in hybrids] + [dogi["closed_zone_fill_avg"]]) + 0.012,
    )
    ax.set_ylim(
        min([row["waf"] for row in hybrids] + [dogi["waf"]]) - 0.0008,
        max([row["waf"] for row in hybrids] + [dogi["waf"]]) + 0.0015,
    )
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

    fig, axes = plt.subplots(1, 2, figsize=(6.35, 2.25))
    bars = axes[0].bar(x, cpu, color=[COLORS["dogi-history"], COLORS["quasar-dogi-hybrid"], COLORS["quasar"]])
    axes[0].set_yscale("log")
    axes[0].set_ylabel("Policy cost (ns/write, log)")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels)
    axes[0].set_title("Policy decision cost")
    axes[0].grid(axis="y", alpha=0.25)
    annotate_bars(axes[0], bars, kind="latency", rotation=0, fontsize=5.4)

    reset_x = [0, 1]
    latency_bars = axes[1].bar(reset_x, [xnvme["append_p50_ns"] / 1000.0, xnvme["append_p99_ns"] / 1000.0], color="#4C78A8")
    axes[1].set_xticks(reset_x)
    axes[1].set_xticklabels(["append\np50", "append\np99"])
    axes[1].set_ylabel("xNVMe append latency (us)")
    axes[1].set_title("xNVMe append latency")
    axes[1].grid(axis="y", alpha=0.25)
    annotate_bars(axes[1], latency_bars, kind="latency", rotation=0, fontsize=5.6)
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

    fig, axes = plt.subplots(1, 3, figsize=(6.65, 2.18))

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
    selected_hybrids = hybrids[:1] + hybrids[len(hybrids) // 2 : len(hybrids) // 2 + 1] + hybrids[-1:]
    annotate_points(
        ax,
        [row["closed_zone_fill_avg"] for row in selected_hybrids],
        [row["waf"] for row in selected_hybrids],
        [f"{row['waf']:.3f}" for row in selected_hybrids],
    )
    annotate_points(ax, [dogi["closed_zone_fill_avg"]], [dogi["waf"]], [f"{dogi['waf']:.3f}"], fontsize=5.6)
    ax.set_xlabel("Closed-zone fill")
    ax.set_ylabel("WAF")
    ax.set_title("PQC placement space cost")
    ax.set_xlim(
        min([row["closed_zone_fill_avg"] for row in hybrids] + [dogi["closed_zone_fill_avg"]]) - 0.006,
        max([row["closed_zone_fill_avg"] for row in hybrids] + [dogi["closed_zone_fill_avg"]]) + 0.010,
    )
    ax.set_ylim(
        min([row["waf"] for row in hybrids] + [dogi["waf"]]) - 0.0006,
        max([row["waf"] for row in hybrids] + [dogi["waf"]]) + 0.0012,
    )
    ax.grid(alpha=0.25)
    ax.legend(fontsize=6, frameon=False, loc="upper left")

    ax = axes[1]
    bars = ax.bar(range(len(policies)), cpu, color=[COLORS["dogi-history"], COLORS["quasar-dogi-hybrid"], COLORS["quasar"]])
    ax.set_yscale("log")
    ax.set_xticks(range(len(policies)))
    ax.set_xticklabels(labels)
    ax.set_ylabel("ns/write, log")
    ax.set_title("PQC hint routing cost")
    ax.grid(axis="y", alpha=0.25)
    annotate_bars(ax, bars, kind="latency", rotation=0, fontsize=5.1)

    ax = axes[2]
    bars = ax.bar(
        [0, 1],
        [xnvme["append_p50_ns"] / 1000.0, xnvme["append_p99_ns"] / 1000.0],
        color="#4C78A8",
    )
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["append\np50", "append\np99"])
    ax.set_ylabel("us")
    ax.set_title("xNVMe append")
    ax.grid(axis="y", alpha=0.25)
    annotate_bars(ax, bars, kind="latency", rotation=0, fontsize=5.4)
    save(fig, out)


def plot_resource_overhead_subfigs(
    rows: list[dict[str, Any]],
    overhead: dict[str, Any],
    xnvme: dict[str, Any],
    out_dir: Path,
) -> None:
    dogi = next(row for row in rows if row.get("policy") == "dogi-history" and not row.get("failed"))
    hybrids = [row for row in rows if row.get("policy") == "quasar-dogi-hybrid" and not row.get("failed")]
    policies = ["dogi-history", "quasar-dogi-hybrid", "quasar"]
    labels = ["DOGI\nMLP", "Hybrid", "QUASAR\nhint"]
    cpu = [
        overhead["by_policy"][policy]["cpu_policy"]["median_ns_per_write"]
        for policy in policies
    ]

    fig, ax = plt.subplots(figsize=(2.35, 2.05))
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
    selected_hybrids = hybrids[:1] + hybrids[len(hybrids) // 2 : len(hybrids) // 2 + 1] + hybrids[-1:]
    annotate_points(
        ax,
        [row["closed_zone_fill_avg"] for row in selected_hybrids],
        [row["waf"] for row in selected_hybrids],
        [f"{row['waf']:.3f}" for row in selected_hybrids],
    )
    annotate_points(ax, [dogi["closed_zone_fill_avg"]], [dogi["waf"]], [f"{dogi['waf']:.3f}"], fontsize=5.6)
    ax.set_xlabel("Closed-zone fill")
    ax.set_ylabel("WAF")
    ax.set_title("Space cost")
    ax.set_xlim(
        min([row["closed_zone_fill_avg"] for row in hybrids] + [dogi["closed_zone_fill_avg"]]) - 0.006,
        max([row["closed_zone_fill_avg"] for row in hybrids] + [dogi["closed_zone_fill_avg"]]) + 0.010,
    )
    ax.set_ylim(
        min([row["waf"] for row in hybrids] + [dogi["waf"]]) - 0.0006,
        max([row["waf"] for row in hybrids] + [dogi["waf"]]) + 0.0012,
    )
    ax.grid(alpha=0.25)
    ax.legend(fontsize=5.5, frameon=False, loc="upper left")
    save(fig, out_dir / "fig4-resource-space.pdf")

    fig, ax = plt.subplots(figsize=(2.35, 2.05))
    bars = ax.bar(range(len(policies)), cpu, color=[COLORS["dogi-history"], COLORS["quasar-dogi-hybrid"], COLORS["quasar"]])
    ax.set_yscale("log")
    ax.set_xticks(range(len(policies)))
    ax.set_xticklabels(labels)
    ax.set_ylabel("ns/write, log")
    ax.set_title("Decision cost")
    ax.grid(axis="y", alpha=0.25)
    annotate_bars(ax, bars, kind="latency", rotation=0, fontsize=5.1)
    save(fig, out_dir / "fig4-resource-decision.pdf")

    fig, ax = plt.subplots(figsize=(2.35, 2.05))
    bars = ax.bar(
        [0, 1],
        [xnvme["append_p50_ns"] / 1000.0, xnvme["append_p99_ns"] / 1000.0],
        color="#4C78A8",
    )
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["append\np50", "append\np99"])
    ax.set_ylabel("us")
    ax.set_title("xNVMe append")
    ax.grid(axis="y", alpha=0.25)
    annotate_bars(ax, bars, kind="latency", rotation=0, fontsize=5.4)
    save(fig, out_dir / "fig4-resource-xnvme.pdf")


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

    fig, axes = plt.subplots(1, 3, figsize=(6.65, 2.22))
    bars = axes[0].bar(x, waiting, color=COLORS["stale"])
    axes[0].set_ylabel("Waiting PQC secrets")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels([case[0] for case in cases])
    axes[0].set_title("PQC exposure fallback")
    axes[0].grid(axis="y", alpha=0.25)
    annotate_bars(axes[0], bars, include_zero=True, fontsize=5.0)

    bars = axes[1].bar(x, waf, color="#F58518")
    axes[1].set_ylabel("Physical WAF")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([case[0] for case in cases])
    axes[1].set_title("Strict PQC erase cost")
    axes[1].grid(axis="y", alpha=0.25)
    annotate_bars(axes[1], bars, kind="waf", include_zero=True, rotation=0, fontsize=5.3)

    bars = axes[2].bar(x, copied, color="#4C78A8")
    axes[2].set_ylabel("Residual copied blocks")
    axes[2].set_xticks(x)
    axes[2].set_xticklabels([case[0] for case in cases])
    axes[2].set_title("Copy cost exposed")
    axes[2].grid(axis="y", alpha=0.25)
    annotate_bars(axes[2], bars, include_zero=True, fontsize=5.0)
    save(fig, out)


def plot_robustness_subfigs(ablation: dict[str, Any], out_dir: Path) -> None:
    residual = ablation["residual_fallback"]
    cases = [
        ("Exact", residual["exact_secret_group"], None),
        ("Bin", residual["epoch_bin_no_residual"], None),
        ("Bin+copy", residual["epoch_bin_with_residual"], residual["epoch_bin_with_residual"]["physical_waf"]),
        ("Strict", residual["strict_ycsb_f_boundary"], residual["strict_ycsb_f_boundary"]["physical_waf"]),
    ]
    labels = [case[0] for case in cases]
    waiting = [case[1].get("secret_waiting_end", 0) for case in cases]
    waf = [case[2] if case[2] is not None else 0 for case in cases]
    copied = [case[1].get("residual_migrated_blocks", 0) for case in cases]
    x = list(range(len(cases)))
    panels = [
        ("fig6-robustness-waiting.pdf", waiting, "Waiting PQC secrets", "Exposure fallback", COLORS["stale"], "count"),
        ("fig6-robustness-waf.pdf", waf, "Physical WAF", "Strict erase cost", "#F58518", "waf"),
        ("fig6-robustness-copy.pdf", copied, "Residual copied blocks", "Copy cost exposed", "#4C78A8", "count"),
    ]
    for filename, values, ylabel, title, color, kind in panels:
        fig, ax = plt.subplots(figsize=(2.35, 2.05))
        bars = ax.bar(x, values, color=color)
        ax.set_ylabel(ylabel)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.25)
        annotate_bars(ax, bars, kind=kind, include_zero=True, rotation=0 if kind == "waf" else 90, fontsize=5.0)
        save(fig, out_dir / filename)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/figures/fast-style"))
    parser.add_argument("--ycsb", type=Path, default=Path("artifacts/results/fast-ycsb-pressure/ycsb-actual-zns-pressure-curve.json"))
    parser.add_argument("--dynamic", type=Path, default=Path("artifacts/results/fast-dynamic-pressure/dynamic-pressure-summary.json"))
    parser.add_argument("--sysbench", type=Path, default=Path("artifacts/results/fast-db-pressure/sysbench-pressure-summary.json"))
    parser.add_argument("--ablation", type=Path, default=Path("artifacts/results/component-ablation.json"))
    parser.add_argument("--space", type=Path, default=Path("artifacts/results/dogi-paper-workloads-smoke/space-sensitivity-tight-open.json"))
    parser.add_argument("--overhead", type=Path, default=Path("artifacts/results/actual-zns-overhead-summary.json"))
    parser.add_argument("--policy-overhead", type=Path, default=Path("artifacts/results/c-policy-overhead.json"))
    parser.add_argument("--physical-robustness", type=Path, default=Path("artifacts/results/physical-robustness-ycsb-a-pqc4000/summary.json"))
    parser.add_argument("--xnvme", type=Path, default=Path("artifacts/results/xnvme-zns-latency/summary.json"))
    parser.add_argument("--ratio", type=Path, default=Path("artifacts/results/dogi-paper-ratio-sweep-50k/summary.json"))
    args = parser.parse_args()

    plot_intro_failure(load_json(args.ycsb), args.out_dir / "fig1-intro-pressure.pdf")
    plot_fairness_matrix_subfigs(args.out_dir)
    plot_service_pressure_allbaseline_subfigs(load_json(args.dynamic), load_json(args.sysbench), args.out_dir)
    plot_ycsb_pressure_subfigs(load_json(args.ycsb), args.out_dir)
    plot_ycsb_allbaseline_subfigs(args.out_dir)
    plot_ratio_sweep_subfigs(load_json(args.ratio), args.out_dir)
    plot_pressure_breadth(load_json(args.dynamic), load_json(args.sysbench), args.out_dir / "fig2-pressure-breadth.pdf")
    plot_pressure_breadth_subfigs(load_json(args.dynamic), load_json(args.sysbench), args.out_dir)
    plot_component_ablation(load_json(args.ablation), args.out_dir / "fig3-component-ablation.pdf")
    plot_component_ablation_subfigs(load_json(args.ablation), args.out_dir)
    plot_open_zone_robustness_subfigs(load_json(args.physical_robustness), args.out_dir)
    plot_prototype_overhead_subfigs(load_json(args.overhead), load_json(args.policy_overhead), args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
