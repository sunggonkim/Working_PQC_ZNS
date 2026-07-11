#!/usr/bin/env python3
"""Multi-seed threshold sweep for QUASAR adaptive admission."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from argparse import Namespace
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

try:
    import run_open_zone_stress as stress
    import zns_pqc_verify as sim
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from sim import run_open_zone_stress as stress
    from sim import zns_pqc_verify as sim


def parse_ints(raw: str) -> list[int]:
    values = [int(item.strip()) for item in raw.split(",") if item.strip()]
    if not values:
        raise argparse.ArgumentTypeError("at least one integer is required")
    return values


def parse_floats(raw: str) -> list[float]:
    values = [float(item.strip()) for item in raw.split(",") if item.strip()]
    if not values:
        raise argparse.ArgumentTypeError("at least one float is required")
    return values


def mean_ci95(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "stdev": None, "ci95": None}
    mean = statistics.fmean(values)
    if len(values) == 1:
        return {"n": 1, "mean": mean, "stdev": 0.0, "ci95": 0.0}
    stdev = statistics.stdev(values)
    return {"n": len(values), "mean": mean, "stdev": stdev, "ci95": 1.96 * stdev / math.sqrt(len(values))}


def trace_args(args: argparse.Namespace, seed: int) -> Namespace:
    return Namespace(
        trace_out=args.trace_dir / f"seed-{seed}.jsonl",
        trace_summary_out=args.result_dir / f"seed-{seed}-trace-summary.json",
        events=args.events,
        tenants=args.tenants,
        epoch_len=args.epoch_len,
        epoch_namespace=args.epoch_namespace,
        tenant_skew=args.tenant_skew,
        expire_jitter=args.expire_jitter,
        rotation_epochs=args.rotation_epochs,
        pqc_writes_per_tick=args.pqc_writes_per_tick,
        pqc_lba_base=args.pqc_lba_base,
        tenant_lba_stride=args.tenant_lba_stride,
        payload_working_set=args.payload_working_set,
        payload_hot_set=args.payload_hot_set,
        payload_hot_fraction=args.payload_hot_fraction,
        payload_updates_per_tick=args.payload_updates_per_tick,
        trace_missing_hint_rate=0.0,
        seed=seed,
    )


def auto_zones(trace: Path, zone_capacity: int, min_free_zones: int, auto_op_ratio: float) -> int:
    peak_live = stress.max_live_blocks(trace)
    usable = math.ceil((peak_live * (1.0 + auto_op_ratio)) / zone_capacity)
    return max(min_free_zones + 1, usable + min_free_zones)


def sim_args(
    args: argparse.Namespace,
    *,
    trace: Path,
    seed: int,
    zone_capacity: int,
    zones: int,
    **overrides,
) -> Namespace:
    values = {
        "trace": trace,
        "zones": zones,
        "zone_capacity": zone_capacity,
        "min_free_zones": args.min_free_zones,
        "lba_bucket_size": args.lba_bucket_size,
        "quasar_cert_epochs": args.quasar_cert_epochs,
        "quasar_min_epoch_fill": 0.0,
        "quasar_bin_width": 1,
        "quasar_open_zone_budget": args.quasar_open_zone_budget,
        "quasar_residual_threshold": -1,
        "quasar_residual_fraction": args.quasar_residual_fraction,
        "quasar_disable_overflow": False,
        "quasar_disable_secret_priority": False,
        "quasar_adaptive_exact_min_blocks": 4,
        "quasar_adaptive_tenant_bin_width": 16,
        "quasar_adaptive_coarse_bin_width": args.adaptive_coarse_bin_width,
        "quasar_adaptive_coarse_pressure": args.adaptive_coarse_pressure,
        "quasar_adaptive_family_pressure": 8.0,
        "quasar_adaptive_urgent_lifetime": args.adaptive_urgent_lifetime,
        "hint_missing_rate": 0.0,
        "wrong_epoch_rate": 0.0,
        "straggler_rate": 0.0,
        "base_write_ns": args.base_write_ns,
        "gc_copy_ns": args.gc_copy_ns,
        "dogi_ml_ns_per_batch": args.dogi_ml_ns_per_batch,
        "dogi_batch_size": args.dogi_batch_size,
        "quasar_hint_ns": args.quasar_hint_ns,
        "seed": seed,
    }
    values.update(overrides)
    return Namespace(**values)


def run_policy_with_retry(ns: Namespace, policy: str, max_retries: int) -> dict:
    requested_zones = ns.zones
    attempt = ns
    last_error: Exception | None = None
    for retry in range(max_retries + 1):
        try:
            row = sim.run_policy(attempt, policy)
            row["failed"] = False
            row["requested_zones"] = requested_zones
            row["retry_count"] = retry
            return row
        except RuntimeError as error:
            last_error = error
            attempt = Namespace(**{**vars(attempt), "zones": int(attempt.zones * 1.35) + 1})
    return {
        "policy": policy,
        "failed": True,
        "error": str(last_error or RuntimeError("failed")),
        "requested_zones": requested_zones,
        "zones": attempt.zones,
        "retry_count": max_retries,
        "waf": 0.0,
        "gc_write_blocks": 0,
        "lifetime_zone_utilization": 0.0,
        "closed_zone_fill_avg": 0.0,
        "stale_secret_blocks_remaining": 0,
        "stale_secret_block_seconds": 0,
        "max_secret_exposure_time": 0,
    }


def config_key(row: dict) -> str:
    if row["experiment"] != "adaptive":
        return row["experiment"]
    return "exact={};family={};tenant={}".format(
        row["adaptive_exact_min_blocks"],
        row["adaptive_family_pressure"],
        row["adaptive_tenant_bin_width"],
    )


def run(args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    trace_summaries: list[dict] = []
    args.trace_dir.mkdir(parents=True, exist_ok=True)
    args.result_dir.mkdir(parents=True, exist_ok=True)

    for seed in args.seeds:
        targs = trace_args(args, seed)
        trace_summary = stress.generate_trace(targs)
        trace_summaries.append(trace_summary)
        for zone_capacity in args.zone_capacities:
            zones = auto_zones(targs.trace_out, zone_capacity, args.min_free_zones, args.auto_op_ratio)
            base = {
                "seed": seed,
                "zone_capacity": zone_capacity,
                "auto_zones": zones,
                "trace": str(targs.trace_out),
            }

            reference_runs = [
                (
                    "dogi_baseline",
                    "dogi-history",
                    sim_args(args, trace=targs.trace_out, seed=seed, zone_capacity=zone_capacity, zones=zones),
                ),
                (
                    "priority_tenant_bin",
                    "quasar-dogi-hybrid",
                    sim_args(
                        args,
                        trace=targs.trace_out,
                        seed=seed,
                        zone_capacity=zone_capacity,
                        zones=zones,
                        quasar_open_zone_budget=1,
                        quasar_bin_width=16,
                    ),
                ),
                (
                    "strict_coarse_bin",
                    "quasar-dogi-hybrid",
                    sim_args(
                        args,
                        trace=targs.trace_out,
                        seed=seed,
                        zone_capacity=zone_capacity,
                        zones=zones,
                        quasar_open_zone_budget=1,
                        quasar_bin_width=args.adaptive_coarse_bin_width,
                        quasar_disable_secret_priority=True,
                    ),
                ),
            ]
            for experiment, policy, ns in reference_runs:
                row = run_policy_with_retry(ns, policy, args.max_retries)
                row.update(base)
                row["experiment"] = experiment
                rows.append(row)
                if args.verbose:
                    sim.print_row(row)

            for exact_min in args.adaptive_exact_min_blocks_values:
                for family_pressure in args.adaptive_family_pressure_values:
                    for tenant_width in args.adaptive_tenant_bin_width_values:
                        ns = sim_args(
                            args,
                            trace=targs.trace_out,
                            seed=seed,
                            zone_capacity=zone_capacity,
                            zones=zones,
                            quasar_open_zone_budget=1,
                            quasar_adaptive_exact_min_blocks=exact_min,
                            quasar_adaptive_family_pressure=family_pressure,
                            quasar_adaptive_tenant_bin_width=tenant_width,
                        )
                        row = run_policy_with_retry(ns, "quasar-adaptive-hybrid", args.max_retries)
                        row.update(base)
                        row["experiment"] = "adaptive"
                        row["adaptive_exact_min_blocks"] = exact_min
                        row["adaptive_family_pressure"] = family_pressure
                        row["adaptive_tenant_bin_width"] = tenant_width
                        rows.append(row)
                        if args.verbose:
                            sim.print_row(row)
    return trace_summaries, rows


def summarize(rows: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if not row.get("failed"):
            grouped[config_key(row)].append(row)

    configs = []
    for key, items in sorted(grouped.items()):
        configs.append(
            {
                "config": key,
                "runs": len(items),
                "waf": mean_ci95([row["waf"] for row in items]),
                "gc_blocks": mean_ci95([float(row["gc_write_blocks"]) for row in items]),
                "lifetime_zone_utilization": mean_ci95([row["lifetime_zone_utilization"] for row in items]),
                "closed_zone_fill_avg": mean_ci95([row["closed_zone_fill_avg"] for row in items]),
                "stale_secret_blocks_remaining": mean_ci95([float(row["stale_secret_blocks_remaining"]) for row in items]),
                "stale_secret_block_seconds": mean_ci95([float(row["stale_secret_block_seconds"]) for row in items]),
                "max_secret_exposure_time": mean_ci95([float(row["max_secret_exposure_time"]) for row in items]),
            }
        )

    def score(item: dict) -> float:
        waf = item["waf"]["mean"] or 0.0
        exposure = item["stale_secret_block_seconds"]["mean"] or 0.0
        util = item["lifetime_zone_utilization"]["mean"] or 0.0
        return waf + (exposure / 10_000_000.0) - (0.05 * util)

    adaptive = [item for item in configs if item["config"].startswith("exact=")]
    best_adaptive = sorted(adaptive, key=score)[:8]
    return {
        "configs": configs,
        "best_adaptive_by_score": best_adaptive,
        "failed_runs": sum(1 for row in rows if row.get("failed")),
        "row_count": len(rows),
    }


def fmt_stat(stat: dict[str, Any], digits: int = 3) -> str:
    mean = stat.get("mean")
    ci95 = stat.get("ci95")
    if mean is None:
        return "N/A"
    if ci95 is None:
        return f"{mean:.{digits}f}"
    return f"{mean:.{digits}f} +/- {ci95:.{digits}f}"


def fmt_float(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def write_markdown(args: argparse.Namespace, summary: dict, path: Path) -> None:
    overview_rows = []
    for item in summary["configs"]:
        overview_rows.append(
            [
                f"`{item['config']}`",
                str(item["runs"]),
                fmt_stat(item["waf"]),
                fmt_stat(item["lifetime_zone_utilization"]),
                fmt_stat(item["closed_zone_fill_avg"]),
                fmt_stat(item["stale_secret_block_seconds"], 1),
                fmt_stat(item["max_secret_exposure_time"], 1),
            ]
        )

    best_rows = []
    for item in summary["best_adaptive_by_score"]:
        best_rows.append(
            [
                f"`{item['config']}`",
                str(item["runs"]),
                fmt_stat(item["waf"]),
                fmt_stat(item["lifetime_zone_utilization"]),
                fmt_stat(item["stale_secret_block_seconds"], 1),
                fmt_stat(item["max_secret_exposure_time"], 1),
            ]
        )

    lines = [
        "# Adaptive Threshold Sweep",
        "",
        "## Setup",
        "",
        f"- Seeds: `{','.join(str(seed) for seed in args.seeds)}`",
        f"- Zone capacities: `{','.join(str(value) for value in args.zone_capacities)}`",
        f"- Exact-min-blocks: `{','.join(str(value) for value in args.adaptive_exact_min_blocks_values)}`",
        f"- Family-pressure: `{','.join(str(value) for value in args.adaptive_family_pressure_values)}`",
        f"- Tenant-bin-width: `{','.join(str(value) for value in args.adaptive_tenant_bin_width_values)}`",
        "",
        "## Overview",
        "",
        markdown_table(
            [
                "Config",
                "Runs",
                "WAF",
                "Lifetime Util",
                "Closed Fill",
                "Stale Block-Seconds",
                "Max Exposure",
            ],
            overview_rows,
        ),
        "",
        "## Best Adaptive Configs By Simple Score",
        "",
        markdown_table(
            ["Config", "Runs", "WAF", "Lifetime Util", "Stale Block-Seconds", "Max Exposure"],
            best_rows,
        ),
        "",
        "## Interpretation",
        "",
        "- This sweep is a variance check, not a final optimizer.",
        "- Lower family-pressure values switch to coarse bins earlier, usually improving WAF/space at the cost of exposure.",
        "- Higher exact-min-blocks avoid underfilled exact families but can push more data into bins.",
        "- A paper-ready controller should choose thresholds from the WAF/space/exposure objective, not from WAF alone.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_json(trace_summaries: list[dict], rows: list[dict], summary: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"trace_summaries": trace_summaries, "rows": rows, "summary": summary}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def plot(summary: dict, path: Path) -> None:
    adaptive = [item for item in summary["configs"] if item["config"].startswith("exact=")]
    if not adaptive:
        return
    fig, ax = plt.subplots(figsize=(8.4, 5.1))
    x = [item["lifetime_zone_utilization"]["mean"] or 0.0 for item in adaptive]
    y = [item["waf"]["mean"] or 0.0 for item in adaptive]
    color = [item["stale_secret_block_seconds"]["mean"] or 0.0 for item in adaptive]
    scatter = ax.scatter(x, y, c=color, cmap="viridis_r", s=90, edgecolors="black", linewidths=0.3)
    for item in adaptive:
        ax.annotate(
            item["config"].replace("exact=", "e=").replace(";family=", ";f=").replace(";tenant=", ";t="),
            (item["lifetime_zone_utilization"]["mean"] or 0.0, item["waf"]["mean"] or 0.0),
            fontsize=6,
            xytext=(3, 3),
            textcoords="offset points",
        )
    ax.set_xlabel("Mean lifetime zone utilization")
    ax.set_ylabel("Mean WAF")
    ax.set_title("Adaptive threshold sweep")
    ax.grid(alpha=0.25)
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("Mean stale secret block-seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", type=Path, default=Path("artifacts/traces/adaptive-threshold-sweep"))
    parser.add_argument("--result-dir", type=Path, default=Path("artifacts/results/adaptive-threshold-sweep"))
    parser.add_argument("--json-out", type=Path, default=Path("artifacts/results/adaptive-threshold-sweep/summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/adaptive-threshold-sweep/summary.md"))
    parser.add_argument("--figure", type=Path, default=Path("artifacts/figures/adaptive-threshold-sweep/summary.png"))
    parser.add_argument("--seeds", type=parse_ints, default=parse_ints("71,73,79"))
    parser.add_argument("--events", type=int, default=3_000)
    parser.add_argument("--tenants", type=int, default=32)
    parser.add_argument("--epoch-len", type=int, default=24)
    parser.add_argument("--epoch-namespace", type=int, default=1_000_000)
    parser.add_argument("--tenant-skew", type=int, default=8)
    parser.add_argument("--expire-jitter", type=int, default=4)
    parser.add_argument("--rotation-epochs", type=int, default=16)
    parser.add_argument("--pqc-writes-per-tick", type=int, default=2)
    parser.add_argument("--pqc-lba-base", type=int, default=20_000_000)
    parser.add_argument("--tenant-lba-stride", type=int, default=100_000)
    parser.add_argument("--payload-working-set", type=int, default=2_048)
    parser.add_argument("--payload-hot-set", type=int, default=256)
    parser.add_argument("--payload-hot-fraction", type=float, default=0.85)
    parser.add_argument("--payload-updates-per-tick", type=int, default=1)
    parser.add_argument("--zone-capacities", type=parse_ints, default=parse_ints("128,256"))
    parser.add_argument("--auto-op-ratio", type=float, default=1.0)
    parser.add_argument("--min-free-zones", type=int, default=8)
    parser.add_argument("--lba-bucket-size", type=int, default=4096)
    parser.add_argument("--quasar-cert-epochs", type=int, default=12)
    parser.add_argument("--quasar-open-zone-budget", type=int, default=1)
    parser.add_argument("--quasar-residual-fraction", type=float, default=0.0)
    parser.add_argument("--adaptive-exact-min-blocks-values", type=parse_ints, default=parse_ints("2,4"))
    parser.add_argument("--adaptive-family-pressure-values", type=parse_floats, default=parse_floats("4,8"))
    parser.add_argument("--adaptive-tenant-bin-width-values", type=parse_ints, default=parse_ints("8,16"))
    parser.add_argument("--adaptive-coarse-bin-width", type=int, default=32_000_000)
    parser.add_argument("--adaptive-coarse-pressure", type=float, default=0.75)
    parser.add_argument("--adaptive-urgent-lifetime", type=int, default=32)
    parser.add_argument("--base-write-ns", type=int, default=10_000)
    parser.add_argument("--gc-copy-ns", type=int, default=15_000)
    parser.add_argument("--dogi-ml-ns-per-batch", type=int, default=600_000)
    parser.add_argument("--dogi-batch-size", type=int, default=128)
    parser.add_argument("--quasar-hint-ns", type=int, default=200)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    trace_summaries, rows = run(args)
    summary = summarize(rows)
    write_json(trace_summaries, rows, summary, args.json_out)
    write_markdown(args, summary, args.markdown_out)
    plot(summary, args.figure)
    print(f"wrote {args.json_out}")
    print(f"wrote {args.markdown_out}")
    print(f"wrote {args.figure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
