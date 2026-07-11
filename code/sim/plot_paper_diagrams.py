#!/usr/bin/env python3
"""Generate paper-only diagrams for the QUASAR draft."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "figures" / "paper"


COLORS = {
    "ink": "#1f2933",
    "muted": "#5f6f7f",
    "line": "#6b7280",
    "blue": "#dbeafe",
    "blue_edge": "#2563eb",
    "green": "#dcfce7",
    "green_edge": "#16a34a",
    "amber": "#fef3c7",
    "amber_edge": "#d97706",
    "rose": "#fee2e2",
    "rose_edge": "#dc2626",
    "violet": "#ede9fe",
    "violet_edge": "#7c3aed",
    "gray": "#f3f4f6",
    "gray_edge": "#4b5563",
}


def box(ax, xy, wh, title, body, fc, ec, fontsize=11):
    x, y = xy
    w, h = wh
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.025,rounding_size=0.035",
        linewidth=1.4,
        edgecolor=ec,
        facecolor=fc,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h - 0.12, title, ha="center", va="top",
            fontsize=fontsize, fontweight="bold", color=COLORS["ink"])
    ax.text(x + w / 2, y + h / 2 - 0.04, body, ha="center", va="center",
            fontsize=fontsize - 1, color=COLORS["ink"], linespacing=1.25)


def arrow(ax, start, end, text=None, rad=0.0, text_offset=0.06):
    patch = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=12,
        linewidth=1.25,
        color=COLORS["line"],
        connectionstyle=f"arc3,rad={rad}",
    )
    ax.add_patch(patch)
    if text:
        mx = (start[0] + end[0]) / 2
        my = (start[1] + end[1]) / 2
        ax.text(mx, my + text_offset, text, ha="center", va="bottom",
                fontsize=9, color=COLORS["muted"],
                bbox=dict(facecolor="white", edgecolor="none", pad=0.4, alpha=0.85))


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.png", dpi=240, bbox_inches="tight")
    plt.close(fig)


def plot_architecture():
    fig, ax = plt.subplots(figsize=(10.8, 4.65))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.45)
    ax.axis("off")

    box(
        ax,
        (0.20, 3.02),
        (2.05, 1.05),
        "PQC service",
        "TLS / KMS / signed log\npayload writer",
        COLORS["blue"],
        COLORS["blue_edge"],
    )
    box(
        ax,
        (2.85, 3.02),
        (2.10, 1.05),
        "Lifecycle hint",
        "intent, epoch,\nsecurity, size",
        COLORS["green"],
        COLORS["green_edge"],
    )
    box(
        ax,
        (5.55, 3.02),
        (2.20, 1.05),
        "QUASAR allocator",
        "classify write\nchoose zone family",
        COLORS["amber"],
        COLORS["amber_edge"],
    )
    box(
        ax,
        (8.35, 3.02),
        (1.45, 1.05),
        "ZNS append",
        "sequential\nzone write",
        COLORS["gray"],
        COLORS["gray_edge"],
    )

    box(
        ax,
        (0.75, 0.92),
        (1.75, 1.05),
        "Payload",
        "DOGI-style\nhistory fallback",
        COLORS["gray"],
        COLORS["gray_edge"],
        fontsize=10,
    )
    box(
        ax,
        (3.05, 0.92),
        (1.75, 1.05),
        "Epoch-secret",
        "KEM artifacts\nshort-lived secrets",
        COLORS["rose"],
        COLORS["rose_edge"],
        fontsize=10,
    )
    box(
        ax,
        (5.35, 0.92),
        (1.75, 1.05),
        "Rotation/log",
        "cert metadata\nsignatures",
        COLORS["violet"],
        COLORS["violet_edge"],
        fontsize=10,
    )
    box(
        ax,
        (7.65, 0.92),
        (1.75, 1.05),
        "Overflow",
        "missing hints\nlow confidence",
        COLORS["gray"],
        COLORS["gray_edge"],
        fontsize=10,
    )

    arrow(ax, (2.25, 3.55), (2.85, 3.55))
    arrow(ax, (4.95, 3.55), (5.55, 3.55))
    arrow(ax, (7.75, 3.55), (8.35, 3.55))
    arrow(ax, (6.55, 3.02), (1.65, 1.97), "payload")
    arrow(ax, (6.65, 3.02), (3.95, 1.97), "death cohort")
    arrow(ax, (6.85, 3.02), (6.20, 1.97), "rotation")
    arrow(ax, (7.05, 3.02), (8.50, 1.97), "fallback")

    arrow(
        ax,
        (3.93, 0.82),
        (8.45, 0.82),
        "epoch close -> reset/sanitize if safe",
        rad=-0.08,
        text_offset=-0.02,
    )
    ax.text(
        5.0,
        0.24,
        "Invariant: reset only after the epoch manager proves all objects in the family are expired or migrated.",
        ha="center",
        va="bottom",
        fontsize=9,
        color=COLORS["muted"],
    )

    save(fig, "quasar-architecture")


def plot_design_hint_path():
    fig, ax = plt.subplots(figsize=(3.45, 1.75))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.2)
    ax.axis("off")

    box(ax, (0.25, 1.75), (1.75, 0.82), "PQC", "TLS/KMS", COLORS["blue"], COLORS["blue_edge"], fontsize=9)
    box(ax, (2.75, 1.75), (1.75, 0.82), "Hint", "intent+epoch", COLORS["green"], COLORS["green_edge"], fontsize=9)
    box(ax, (5.25, 1.75), (1.95, 0.82), "Allocator", "family", COLORS["amber"], COLORS["amber_edge"], fontsize=9)
    box(ax, (7.95, 1.75), (1.75, 0.82), "ZNS", "append/reset", COLORS["gray"], COLORS["gray_edge"], fontsize=9)

    arrow(ax, (2.00, 2.16), (2.75, 2.16))
    arrow(ax, (4.50, 2.16), (5.25, 2.16))
    arrow(ax, (7.20, 2.16), (7.95, 2.16))

    ax.text(5.0, 0.65, "Only lifecycle labels cross the storage boundary.", ha="center", fontsize=8.5, color=COLORS["muted"])
    save(fig, "quasar-design-hint-path")


def plot_design_zone_families():
    fig, ax = plt.subplots(figsize=(3.45, 1.75))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.2)
    ax.axis("off")

    families = [
        ("Epoch secret", COLORS["rose"], COLORS["rose_edge"]),
        ("Rotation", COLORS["violet"], COLORS["violet_edge"]),
        ("Append log", COLORS["green"], COLORS["green_edge"]),
        ("Payload", COLORS["gray"], COLORS["gray_edge"]),
        ("Overflow", COLORS["amber"], COLORS["amber_edge"]),
    ]
    for i, (title, fc, ec) in enumerate(families):
        x = 0.25 + i * 1.93
        patch = FancyBboxPatch(
            (x, 1.65),
            1.58,
            0.85,
            boxstyle="round,pad=0.02,rounding_size=0.035",
            linewidth=1.2,
            edgecolor=ec,
            facecolor=fc,
        )
        ax.add_patch(patch)
        ax.text(x + 0.79, 2.08, title, ha="center", va="center", fontsize=8.7, fontweight="bold", color=COLORS["ink"])

    ax.text(5.0, 0.72, "Priority: cohort purity -> secret isolation -> utilization -> open-zone budget.", ha="center", fontsize=7.8, color=COLORS["muted"])
    save(fig, "quasar-design-zone-families")


def plot_design_epoch_reclaim():
    fig, ax = plt.subplots(figsize=(3.45, 1.75))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.2)
    ax.axis("off")

    box(ax, (0.25, 1.75), (1.75, 0.82), "Close", "epoch E", COLORS["blue"], COLORS["blue_edge"], fontsize=9)
    box(ax, (2.55, 1.75), (1.75, 0.82), "Check", "live bytes", COLORS["amber"], COLORS["amber_edge"], fontsize=9)
    box(ax, (4.85, 1.75), (1.55, 0.82), "Reset", "empty", COLORS["green"], COLORS["green_edge"], fontsize=9)
    box(ax, (6.85, 1.75), (1.55, 0.82), "Copy", "residue", COLORS["violet"], COLORS["violet_edge"], fontsize=9)
    box(ax, (8.55, 1.75), (1.20, 0.82), "GC", "unsafe", COLORS["gray"], COLORS["gray_edge"], fontsize=9)

    arrow(ax, (2.00, 2.16), (2.55, 2.16))
    arrow(ax, (4.30, 2.16), (4.85, 2.16))
    arrow(ax, (6.40, 2.16), (6.85, 2.16))
    arrow(ax, (8.40, 2.16), (8.55, 2.16))
    ax.text(5.0, 0.72, "Wrong hints hurt placement, not correctness.", ha="center", fontsize=8.2, color=COLORS["muted"])
    save(fig, "quasar-design-epoch-reclaim")


def plot_epoch_upper_bound():
    fig, ax = plt.subplots(figsize=(7.6, 3.2))
    workloads = ["mixed sanity", "stress rekey"]
    values = {
        "DOGI-style": [1.791, 2.031],
        "QUASAR": [1.010, 1.019],
        "epoch oracle": [1.000, 1.003],
    }
    colors = {
        "DOGI-style": "#ef4444",
        "QUASAR": "#2563eb",
        "epoch oracle": "#16a34a",
    }
    x = range(len(workloads))
    width = 0.23
    offsets = [-width, 0, width]
    for (label, vals), dx in zip(values.items(), offsets):
        bars = ax.bar([i + dx for i in x], vals, width=width, label=label, color=colors[label])
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, val + 0.025, f"{val:.3f}",
                    ha="center", va="bottom", fontsize=8)

    ax.set_xticks(list(x))
    ax.set_xticklabels(workloads)
    ax.set_ylabel("WAF")
    ax.set_ylim(0.9, 2.22)
    ax.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.17))
    ax.set_title("Epoch oracle is an upper bound, not the deployed policy", pad=28)
    ax.text(
        0.5,
        -0.30,
        "The gap shows that protocol lifetime is the missing placement signal; QUASAR uses lifecycle hints, not exact future delete timestamps.",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=9,
        color=COLORS["muted"],
    )
    save(fig, "epoch-upper-bound")


def main():
    plot_architecture()
    plot_design_hint_path()
    plot_design_zone_families()
    plot_design_epoch_reclaim()
    plot_epoch_upper_bound()


if __name__ == "__main__":
    main()
