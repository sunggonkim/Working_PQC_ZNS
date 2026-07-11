#!/usr/bin/env python3
"""Sweep QUASAR-DOGI space/placement knobs on a DOGI-shaped trace."""

from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path

import matplotlib.pyplot as plt

import zns_pqc_verify as sim


def make_args(args: argparse.Namespace, **overrides) -> Namespace:
    values = {
        "trace": args.trace,
        "zones": args.zones,
        "zone_capacity": args.zone_capacity,
        "min_free_zones": args.min_free_zones,
        "lba_bucket_size": args.lba_bucket_size,
        "quasar_cert_epochs": args.quasar_cert_epochs,
        "quasar_min_epoch_fill": 0.0,
        "quasar_bin_width": 1,
        "quasar_open_zone_budget": 0,
        "quasar_residual_threshold": -1,
        "quasar_residual_fraction": 0.0,
        "quasar_disable_overflow": False,
        "quasar_disable_secret_priority": False,
        "hint_missing_rate": 0.0,
        "wrong_epoch_rate": 0.0,
        "straggler_rate": 0.0,
        "base_write_ns": args.base_write_ns,
        "gc_copy_ns": args.gc_copy_ns,
        "dogi_ml_ns_per_batch": args.dogi_ml_ns_per_batch,
        "dogi_batch_size": args.dogi_batch_size,
        "quasar_hint_ns": args.quasar_hint_ns,
        "seed": args.seed,
    }
    values.update(overrides)
    return Namespace(**values)


def run_policy_with_retry(ns: Namespace, policy: str) -> dict:
    requested_zones = ns.zones
    attempt = ns
    for retry in range(4):
        try:
            row = sim.run_policy(attempt, policy)
            row["failed"] = False
            row["requested_zones"] = requested_zones
            row["retry_count"] = retry
            return row
        except RuntimeError as error:
            if retry == 3:
                return {
                    "policy": policy,
                    "failed": True,
                    "error": str(error),
                    "zones": attempt.zones,
                    "requested_zones": requested_zones,
                    "retry_count": retry,
                    "waf": 0.0,
                    "gc_write_blocks": 0,
                    "lifetime_zone_utilization": 0.0,
                    "closed_zone_fill_avg": 0.0,
                    "stale_secret_blocks_remaining": 0,
                }
            attempt = Namespace(**{**vars(attempt), "zones": int(attempt.zones * 1.35) + 1})
    raise AssertionError("unreachable")


def run_sweep(args: argparse.Namespace) -> list[dict]:
    rows: list[dict] = []

    baseline = run_policy_with_retry(make_args(args), "dogi-history")
    baseline["experiment"] = "space_sensitivity_baseline"
    baseline["quasar_min_epoch_fill"] = None
    baseline["quasar_bin_width"] = None
    baseline["quasar_open_zone_budget"] = None
    rows.append(baseline)

    for open_budget in args.open_zone_budget_values:
        for bin_width in args.bin_width_values:
            for min_fill in args.min_epoch_fill_values:
                ns = make_args(
                    args,
                    quasar_open_zone_budget=open_budget,
                    quasar_bin_width=bin_width,
                    quasar_min_epoch_fill=min_fill,
                )
                row = run_policy_with_retry(ns, "quasar-dogi-hybrid")
                row["experiment"] = "space_sensitivity"
                row["quasar_open_zone_budget"] = open_budget
                row["quasar_bin_width"] = bin_width
                row["quasar_min_epoch_fill"] = min_fill
                rows.append(row)
                if args.verbose:
                    sim.print_row(row)
    return rows


def write_json(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(rows: list[dict], path: Path) -> None:
    baseline = next(row for row in rows if row["experiment"] == "space_sensitivity_baseline")
    candidates = [row for row in rows if row["experiment"] == "space_sensitivity" and not row.get("failed")]
    best_waf = sorted(candidates, key=lambda row: (row["waf"], -row["lifetime_zone_utilization"]))[:8]
    best_util = sorted(candidates, key=lambda row: (-row["lifetime_zone_utilization"], row["waf"]))[:8]

    def setting(row: dict) -> str:
        return "fill={:.2f}, bin={}, open={}".format(
            row["quasar_min_epoch_fill"],
            row["quasar_bin_width"],
            "auto" if row["quasar_open_zone_budget"] == 0 else row["quasar_open_zone_budget"],
        )

    def table(title: str, selected: list[dict]) -> list[str]:
        lines = [
            f"## {title}",
            "",
            "| Setting | WAF | GC Blocks | Lifetime Util | Closed Fill | Stale Secrets | Exact Writes | Binned Writes | Retries |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in selected:
            lines.append(
                "| {setting} | {waf:.3f} | {gc:,} | {util:.3f} | {fill:.3f} | {stale:,} | {exact:,} | {binned:,} | {retry} |".format(
                    setting=setting(row),
                    waf=row["waf"],
                    gc=int(row["gc_write_blocks"]),
                    util=row["lifetime_zone_utilization"],
                    fill=row["closed_zone_fill_avg"],
                    stale=int(row["stale_secret_blocks_remaining"]),
                    exact=int(row.get("quasar_exact_epoch_writes", 0)),
                    binned=int(row.get("quasar_binned_epoch_writes", 0)),
                    retry=int(row.get("retry_count", 0)),
                )
            )
        return lines

    lines = [
        "# QUASAR-DOGI Space Sensitivity",
        "",
        f"- Trace: `{baseline['trace']}`",
        f"- Baseline DOGI WAF: {baseline['waf']:.3f}",
        f"- Baseline DOGI lifetime utilization: {baseline['lifetime_zone_utilization']:.3f}",
        f"- Baseline DOGI stale secrets: {int(baseline['stale_secret_blocks_remaining']):,}",
        f"- Candidate count: {len(candidates)}",
        "",
    ]
    lines.extend(table("Lowest WAF Settings", best_waf))
    lines.append("")
    lines.extend(table("Highest Utilization Settings", best_util))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot(rows: list[dict], path: Path) -> None:
    baseline = next(row for row in rows if row["experiment"] == "space_sensitivity_baseline")
    candidates = [row for row in rows if row["experiment"] == "space_sensitivity" and not row.get("failed")]
    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    scatter = ax.scatter(
        [row["lifetime_zone_utilization"] for row in candidates],
        [row["waf"] for row in candidates],
        c=[row["stale_secret_blocks_remaining"] for row in candidates],
        cmap="viridis_r",
        s=[45 + 8 * max(0, int(row["quasar_bin_width"])) for row in candidates],
        alpha=0.85,
        edgecolors="black",
        linewidths=0.25,
    )
    ax.scatter(
        [baseline["lifetime_zone_utilization"]],
        [baseline["waf"]],
        marker="X",
        s=130,
        color="#E45756",
        label="DOGI baseline",
    )
    ax.set_xlabel("Lifetime zone utilization")
    ax.set_ylabel("WAF")
    ax.set_title("QUASAR-DOGI space sensitivity")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=9)
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("Final stale secret blocks")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    print(f"wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, default=Path("artifacts/traces/dogi-paper-workloads-smoke/exchange-pqc2000.jsonl"))
    parser.add_argument("--json-out", type=Path, default=Path("artifacts/results/dogi-paper-workloads-smoke/space-sensitivity.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/dogi-paper-workloads-smoke/space-sensitivity.md"))
    parser.add_argument("--figure", type=Path, default=Path("artifacts/figures/dogi-paper-workloads-smoke/space-sensitivity.png"))
    parser.add_argument("--zones", type=int, default=170)
    parser.add_argument("--zone-capacity", type=int, default=512)
    parser.add_argument("--min-free-zones", type=int, default=8)
    parser.add_argument("--lba-bucket-size", type=int, default=4096)
    parser.add_argument("--quasar-cert-epochs", type=int, default=12)
    parser.add_argument("--min-epoch-fill-values", nargs="+", type=float, default=[0.0, 0.25, 0.50])
    parser.add_argument("--bin-width-values", nargs="+", type=int, default=[1, 2, 4, 8])
    parser.add_argument("--open-zone-budget-values", nargs="+", type=int, default=[0, 16, 32, 64])
    parser.add_argument("--base-write-ns", type=int, default=10_000)
    parser.add_argument("--gc-copy-ns", type=int, default=15_000)
    parser.add_argument("--dogi-ml-ns-per-batch", type=int, default=600_000)
    parser.add_argument("--dogi-batch-size", type=int, default=128)
    parser.add_argument("--quasar-hint-ns", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    rows = run_sweep(args)
    write_json(rows, args.json_out)
    write_markdown(rows, args.markdown_out)
    plot(rows, args.figure)
    print(f"wrote {args.json_out}")
    print(f"wrote {args.markdown_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
