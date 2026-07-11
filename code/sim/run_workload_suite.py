#!/usr/bin/env python3
"""Run E1 WAF comparison across the generated PQC workload suite."""

from __future__ import annotations

import argparse
import json
import math
from argparse import Namespace
from pathlib import Path

import zns_pqc_verify as sim


def max_live_blocks(trace: Path) -> int:
    live_by_object: dict[int, int] = {}
    live = 0
    peak = 0
    with trace.open("r", encoding="utf-8") as src:
        for line in src:
            event = json.loads(line)
            object_id = int(event["object_id"])
            size_blocks = int(event["size_blocks"])
            if event["op"] in {"write", "prefill"}:
                live_by_object[object_id] = size_blocks
                live += size_blocks
                peak = max(peak, live)
            elif event["op"] == "expire":
                live -= live_by_object.pop(object_id, 0)
    return peak


def zones_for_trace(base: argparse.Namespace, trace: Path) -> int:
    if not base.auto_zones:
        return base.zones
    peak_live = max_live_blocks(trace)
    usable = max(1, math.ceil((peak_live * (1.0 + base.auto_op_ratio)) / base.zone_capacity))
    return max(base.min_free_zones + 1, usable + base.min_free_zones)


def args_for(base: argparse.Namespace, trace: Path) -> Namespace:
    zones = zones_for_trace(base, trace)
    return Namespace(
        trace=trace,
        zones=zones,
        zone_capacity=base.zone_capacity,
        min_free_zones=base.min_free_zones,
        lba_bucket_size=base.lba_bucket_size,
        quasar_cert_epochs=base.quasar_cert_epochs,
        quasar_min_epoch_fill=base.quasar_min_epoch_fill,
        quasar_bin_width=base.quasar_bin_width,
        quasar_open_zone_budget=base.quasar_open_zone_budget,
        quasar_residual_threshold=base.quasar_residual_threshold,
        quasar_residual_fraction=base.quasar_residual_fraction,
        quasar_adaptive_exact_min_blocks=base.quasar_adaptive_exact_min_blocks,
        quasar_adaptive_tenant_bin_width=base.quasar_adaptive_tenant_bin_width,
        quasar_adaptive_coarse_bin_width=base.quasar_adaptive_coarse_bin_width,
        quasar_adaptive_coarse_pressure=base.quasar_adaptive_coarse_pressure,
        quasar_adaptive_family_pressure=base.quasar_adaptive_family_pressure,
        quasar_adaptive_urgent_lifetime=base.quasar_adaptive_urgent_lifetime,
        quasar_disable_overflow=False,
        quasar_disable_secret_priority=False,
        hint_missing_rate=0.0,
        wrong_epoch_rate=0.0,
        straggler_rate=0.0,
        base_write_ns=base.base_write_ns,
        gc_copy_ns=base.gc_copy_ns,
        dogi_ml_ns_per_batch=base.dogi_ml_ns_per_batch,
        dogi_batch_size=base.dogi_batch_size,
        quasar_hint_ns=base.quasar_hint_ns,
        seed=base.seed,
    )


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        json.dump(rows, out, indent=2, sort_keys=True)
        out.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", type=Path, default=Path("artifacts/traces/workloads"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/e1-workloads.json"))
    parser.add_argument("--zones", type=int, default=700)
    parser.add_argument("--auto-zones", action="store_true")
    parser.add_argument("--auto-op-ratio", type=float, default=0.05)
    parser.add_argument("--zone-capacity", type=int, default=512)
    parser.add_argument("--min-free-zones", type=int, default=8)
    parser.add_argument("--lba-bucket-size", type=int, default=4096)
    parser.add_argument("--quasar-cert-epochs", type=int, default=12)
    parser.add_argument("--quasar-min-epoch-fill", type=float, default=0.0)
    parser.add_argument("--quasar-bin-width", type=int, default=1)
    parser.add_argument("--quasar-open-zone-budget", type=int, default=0)
    parser.add_argument("--quasar-residual-threshold", type=int, default=-1)
    parser.add_argument("--quasar-residual-fraction", type=float, default=0.0)
    parser.add_argument("--quasar-adaptive-exact-min-blocks", type=int, default=4)
    parser.add_argument("--quasar-adaptive-tenant-bin-width", type=int, default=16)
    parser.add_argument("--quasar-adaptive-coarse-bin-width", type=int, default=32_000_000)
    parser.add_argument("--quasar-adaptive-coarse-pressure", type=float, default=0.75)
    parser.add_argument("--quasar-adaptive-family-pressure", type=float, default=8.0)
    parser.add_argument("--quasar-adaptive-urgent-lifetime", type=int, default=32)
    parser.add_argument("--base-write-ns", type=int, default=10_000)
    parser.add_argument("--gc-copy-ns", type=int, default=15_000)
    parser.add_argument("--dogi-ml-ns-per-batch", type=int, default=600_000)
    parser.add_argument("--dogi-batch-size", type=int, default=128)
    parser.add_argument("--quasar-hint-ns", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--policies",
        nargs="+",
        default=[
            "fifo",
            "sepbit-style",
            "midas-style",
            "dogi-history",
            "quasar",
            "quasar-dogi-hybrid",
            "epoch-oracle",
        ],
    )
    args = parser.parse_args()

    rows: list[dict] = []
    traces = sorted(args.trace_dir.glob("*.jsonl"))
    if not traces:
        raise SystemExit(f"no JSONL traces found under {args.trace_dir}")
    for trace in traces:
        workload = trace.stem
        ns = args_for(args, trace)
        for attempt in range(4):
            try:
                trial_rows = []
                print(f"== {workload} zones={ns.zones} attempt={attempt + 1} ==")
                for policy in args.policies:
                    row = sim.run_policy(ns, policy)
                    row["experiment"] = "E1"
                    row["workload"] = workload
                    trial_rows.append(row)
                rows.extend(trial_rows)
                for row in trial_rows:
                    sim.print_row(row)
                write_rows(args.out, rows)
                break
            except RuntimeError as exc:
                if attempt == 3:
                    raise
                ns.zones = int(ns.zones * 1.5) + 1
                print(f"retrying {workload} with zones={ns.zones}: {exc}")

    write_rows(args.out, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
