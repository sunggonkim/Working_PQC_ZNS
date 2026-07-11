#!/usr/bin/env python3
"""Evaluate QUASAR adaptive admission against fixed open-zone policies."""

from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path

import matplotlib.pyplot as plt

try:
    import run_open_zone_stress as stress
    import zns_pqc_verify as sim
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from sim import run_open_zone_stress as stress
    from sim import zns_pqc_verify as sim


def trace_args(args: argparse.Namespace) -> Namespace:
    return Namespace(
        trace_out=args.trace_out,
        trace_summary_out=args.trace_summary_out,
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
        seed=args.seed,
    )


def auto_zones(args: argparse.Namespace) -> int:
    if args.zones > 0:
        return args.zones
    peak_live = stress.max_live_blocks(args.trace_out)
    usable = int((peak_live * (1.0 + args.auto_op_ratio) + args.zone_capacity - 1) // args.zone_capacity)
    return max(args.min_free_zones + 1, usable + args.min_free_zones)


def sim_args(args: argparse.Namespace, zones: int, **overrides) -> Namespace:
    values = {
        "trace": args.trace_out,
        "zones": zones,
        "zone_capacity": args.zone_capacity,
        "min_free_zones": args.min_free_zones,
        "lba_bucket_size": args.lba_bucket_size,
        "quasar_cert_epochs": args.quasar_cert_epochs,
        "quasar_min_epoch_fill": 0.0,
        "quasar_bin_width": 1,
        "quasar_open_zone_budget": 1,
        "quasar_residual_threshold": -1,
        "quasar_residual_fraction": args.quasar_residual_fraction,
        "quasar_disable_overflow": False,
        "quasar_disable_secret_priority": False,
        "quasar_adaptive_exact_min_blocks": args.adaptive_exact_min_blocks,
        "quasar_adaptive_tenant_bin_width": args.adaptive_tenant_bin_width,
        "quasar_adaptive_coarse_bin_width": args.adaptive_coarse_bin_width,
        "quasar_adaptive_coarse_pressure": args.adaptive_coarse_pressure,
        "quasar_adaptive_family_pressure": args.adaptive_family_pressure,
        "quasar_adaptive_urgent_lifetime": args.adaptive_urgent_lifetime,
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


def configs(args: argparse.Namespace, zones: int) -> list[tuple[str, str, Namespace]]:
    return [
        ("DOGI baseline", "dogi-history", sim_args(args, zones)),
        (
            "priority exact-ish",
            "quasar-dogi-hybrid",
            sim_args(args, zones, quasar_open_zone_budget=1, quasar_bin_width=1),
        ),
        (
            "priority tenant-bin",
            "quasar-dogi-hybrid",
            sim_args(args, zones, quasar_open_zone_budget=1, quasar_bin_width=16),
        ),
        (
            "strict coarse-bin",
            "quasar-dogi-hybrid",
            sim_args(
                args,
                zones,
                quasar_open_zone_budget=1,
                quasar_bin_width=args.adaptive_coarse_bin_width,
                quasar_disable_secret_priority=True,
            ),
        ),
        (
            "adaptive clean",
            "quasar-adaptive-hybrid",
            sim_args(args, zones, quasar_open_zone_budget=1),
        ),
        (
            "adaptive missing-5%",
            "quasar-adaptive-hybrid",
            sim_args(args, zones, quasar_open_zone_budget=1, hint_missing_rate=0.05),
        ),
    ]


def run(args: argparse.Namespace) -> tuple[dict, list[dict]]:
    trace_summary = stress.generate_trace(trace_args(args))
    zones = auto_zones(args)
    rows = []
    for name, policy, ns in configs(args, zones):
        row = run_policy_with_retry(ns, policy, args.max_retries)
        row["experiment"] = name
        rows.append(row)
        sim.print_row(row)
    return trace_summary, rows


def fmt_float(value: object, digits: int = 3) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def fmt_int(value: object) -> str:
    if value is None:
        return "N/A"
    return f"{int(value):,}"


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def write_outputs(args: argparse.Namespace, trace_summary: dict, rows: list[dict]) -> None:
    payload = {"trace_summary": trace_summary, "rows": rows}
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    table_rows = []
    for row in rows:
        table_rows.append(
            [
                row["experiment"],
                row["policy"],
                fmt_float(row["waf"]),
                fmt_int(row["gc_write_blocks"]),
                fmt_float(row["lifetime_zone_utilization"]),
                fmt_float(row["closed_zone_fill_avg"]),
                fmt_int(row["stale_secret_blocks_remaining"]),
                fmt_int(row["stale_secret_block_seconds"]),
                fmt_int(row["max_secret_exposure_time"]),
                fmt_int(row.get("quasar_exact_epoch_writes")),
                fmt_int(row.get("quasar_tenant_bin_writes")),
                fmt_int(row.get("quasar_coarse_bin_writes")),
                fmt_int(row.get("hint_missing_injected", 0)),
            ]
        )
    lines = [
        "# Adaptive Admission Evaluation",
        "",
        "## Setup",
        "",
        f"- Trace: `{trace_summary['trace']}`",
        f"- Tenants: {trace_summary['tenants']}",
        f"- Epoch length: {trace_summary['epoch_len']}",
        f"- Adaptive exact min blocks: {args.adaptive_exact_min_blocks}",
        f"- Adaptive tenant bin width: {args.adaptive_tenant_bin_width}",
        f"- Adaptive coarse bin width: {args.adaptive_coarse_bin_width}",
        f"- Adaptive family pressure: {args.adaptive_family_pressure}",
        f"- Adaptive urgent lifetime: {args.adaptive_urgent_lifetime}",
        "",
        "## Results",
        "",
        markdown_table(
            [
                "Experiment",
                "Policy",
                "WAF",
                "GC Blocks",
                "Lifetime Util",
                "Closed Fill",
                "Stale Secrets",
                "Stale Block-Seconds",
                "Max Exposure",
                "Exact",
                "Tenant Bin",
                "Coarse Bin",
                "Missing",
            ],
            table_rows,
        ),
        "",
        "## Interpretation",
        "",
        "- Fixed priority placement minimizes exposure for narrow bins but can waste space in many-tenant tiny-epoch regimes.",
        "- Fixed strict coarse binning improves WAF and space utilization but increases stale-secret exposure by mixing more death cohorts.",
        "- Adaptive admission uses exact placement only after a minimum cohort size, tenant bins for urgent ephemeral secrets, and coarse bins under pressure.",
        "- The policy is not a final optimal controller; it is a concrete starting point for the WAF/space/exposure trade-off curve.",
        "",
    ]
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text("\n".join(lines), encoding="utf-8")

    args.figure.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8.4, 5.0))
    x = [row["lifetime_zone_utilization"] for row in rows]
    y = [row["waf"] for row in rows]
    colors = [row["stale_secret_block_seconds"] for row in rows]
    scatter = ax.scatter(x, y, c=colors, cmap="viridis_r", s=95, edgecolors="black", linewidths=0.35)
    for row in rows:
        ax.annotate(row["experiment"], (row["lifetime_zone_utilization"], row["waf"]), fontsize=7, xytext=(4, 4), textcoords="offset points")
    ax.set_xlabel("Lifetime zone utilization")
    ax.set_ylabel("WAF")
    ax.set_title("Adaptive admission trade-off")
    ax.grid(alpha=0.25)
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("Stale secret block-seconds")
    fig.tight_layout()
    fig.savefig(args.figure, dpi=180)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-out", type=Path, default=Path("artifacts/traces/adaptive-admission/adversarial.jsonl"))
    parser.add_argument("--trace-summary-out", type=Path, default=Path("artifacts/results/adaptive-admission/trace-summary.json"))
    parser.add_argument("--json-out", type=Path, default=Path("artifacts/results/adaptive-admission/summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/adaptive-admission/summary.md"))
    parser.add_argument("--figure", type=Path, default=Path("artifacts/figures/adaptive-admission/summary.png"))
    parser.add_argument("--events", type=int, default=6_000)
    parser.add_argument("--tenants", type=int, default=32)
    parser.add_argument("--epoch-len", type=int, default=24)
    parser.add_argument("--epoch-namespace", type=int, default=1_000_000)
    parser.add_argument("--tenant-skew", type=int, default=8)
    parser.add_argument("--expire-jitter", type=int, default=4)
    parser.add_argument("--rotation-epochs", type=int, default=16)
    parser.add_argument("--pqc-writes-per-tick", type=int, default=2)
    parser.add_argument("--pqc-lba-base", type=int, default=20_000_000)
    parser.add_argument("--tenant-lba-stride", type=int, default=100_000)
    parser.add_argument("--payload-working-set", type=int, default=3_072)
    parser.add_argument("--payload-hot-set", type=int, default=384)
    parser.add_argument("--payload-hot-fraction", type=float, default=0.85)
    parser.add_argument("--payload-updates-per-tick", type=int, default=1)
    parser.add_argument("--zones", type=int, default=0)
    parser.add_argument("--auto-op-ratio", type=float, default=0.15)
    parser.add_argument("--zone-capacity", type=int, default=128)
    parser.add_argument("--min-free-zones", type=int, default=8)
    parser.add_argument("--lba-bucket-size", type=int, default=4096)
    parser.add_argument("--quasar-cert-epochs", type=int, default=12)
    parser.add_argument("--quasar-residual-fraction", type=float, default=0.0)
    parser.add_argument("--adaptive-exact-min-blocks", type=int, default=4)
    parser.add_argument("--adaptive-tenant-bin-width", type=int, default=16)
    parser.add_argument("--adaptive-coarse-bin-width", type=int, default=32_000_000)
    parser.add_argument("--adaptive-coarse-pressure", type=float, default=0.75)
    parser.add_argument("--adaptive-family-pressure", type=float, default=8.0)
    parser.add_argument("--adaptive-urgent-lifetime", type=int, default=32)
    parser.add_argument("--base-write-ns", type=int, default=10_000)
    parser.add_argument("--gc-copy-ns", type=int, default=15_000)
    parser.add_argument("--dogi-ml-ns-per-batch", type=int, default=600_000)
    parser.add_argument("--dogi-batch-size", type=int, default=128)
    parser.add_argument("--quasar-hint-ns", type=int, default=200)
    parser.add_argument("--seed", type=int, default=71)
    parser.add_argument("--max-retries", type=int, default=3)
    args = parser.parse_args()

    trace_summary, rows = run(args)
    write_outputs(args, trace_summary, rows)
    print(f"wrote {args.json_out}")
    print(f"wrote {args.markdown_out}")
    print(f"wrote {args.figure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
