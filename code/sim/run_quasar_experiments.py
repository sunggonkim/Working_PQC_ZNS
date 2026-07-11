#!/usr/bin/env python3
"""Run the first QUASAR simulator experiment set from plan.md.

This runner covers:

- E0: baseline sanity reproduction.
- E2: WAF vs. space-utilization sweep.
- E5: robustness to missing/wrong hints and stragglers.

It writes JSON files under `artifacts/results/` by default. Plotting can be
added on top of these stable result files.
"""

from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path

import zns_pqc_verify as sim


def base_args(args: argparse.Namespace, **overrides) -> Namespace:
    values = {
        "trace": args.trace,
        "zones": args.zones,
        "zone_capacity": args.zone_capacity,
        "min_free_zones": args.min_free_zones,
        "lba_bucket_size": args.lba_bucket_size,
        "quasar_cert_epochs": args.quasar_cert_epochs,
        "quasar_min_epoch_fill": 0.0,
        "quasar_bin_width": 1,
        "quasar_open_zone_budget": args.quasar_open_zone_budget,
        "quasar_residual_threshold": args.quasar_residual_threshold,
        "quasar_residual_fraction": args.quasar_residual_fraction,
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


def write_json(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        json.dump(rows, out, indent=2, sort_keys=True)
        out.write("\n")


BASELINE_POLICIES = ["fifo", "sepbit-style", "midas-style", "dogi-history", "quasar", "epoch-oracle"]


def run_e0(args: argparse.Namespace) -> list[dict]:
    ns = base_args(args)
    return [sim.run_policy(ns, policy) for policy in BASELINE_POLICIES]


def run_e2(args: argparse.Namespace) -> list[dict]:
    rows: list[dict] = []
    for min_fill in args.min_epoch_fill_values:
        for bin_width in args.bin_width_values:
            ns = base_args(args, quasar_min_epoch_fill=min_fill, quasar_bin_width=bin_width)
            row = sim.run_policy(ns, "quasar")
            row["experiment"] = "E2"
            row["quasar_min_epoch_fill"] = min_fill
            row["quasar_bin_width"] = bin_width
            rows.append(row)
    return rows


def run_e5(args: argparse.Namespace) -> list[dict]:
    rows: list[dict] = []
    for missing_rate in args.hint_missing_values:
        for wrong_rate in args.wrong_epoch_values:
            for straggler_rate in args.straggler_values:
                ns = base_args(
                    args,
                    hint_missing_rate=missing_rate,
                    wrong_epoch_rate=wrong_rate,
                    straggler_rate=straggler_rate,
                )
                row = sim.run_policy(ns, "quasar")
                row["experiment"] = "E5"
                row["hint_missing_rate"] = missing_rate
                row["wrong_epoch_rate"] = wrong_rate
                row["straggler_rate"] = straggler_rate
                rows.append(row)
    return rows


def print_summary(name: str, rows: list[dict]) -> None:
    print(f"{name}: {len(rows)} rows")
    for row in rows[:8]:
        sim.print_row(row)
    if len(rows) > 8:
        print(f"... {len(rows) - 8} more rows")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, default=Path("artifacts/traces/pqc-mixed.jsonl"))
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/results"))
    parser.add_argument("--zones", type=int, default=1100)
    parser.add_argument("--zone-capacity", type=int, default=512)
    parser.add_argument("--min-free-zones", type=int, default=12)
    parser.add_argument("--lba-bucket-size", type=int, default=4096)
    parser.add_argument("--quasar-cert-epochs", type=int, default=12)
    parser.add_argument("--quasar-open-zone-budget", type=int, default=0)
    parser.add_argument("--quasar-residual-threshold", type=int, default=-1)
    parser.add_argument("--quasar-residual-fraction", type=float, default=0.0)
    parser.add_argument("--base-write-ns", type=int, default=10_000)
    parser.add_argument("--gc-copy-ns", type=int, default=15_000)
    parser.add_argument("--dogi-ml-ns-per-batch", type=int, default=600_000)
    parser.add_argument("--dogi-batch-size", type=int, default=128)
    parser.add_argument("--quasar-hint-ns", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--min-epoch-fill-values", nargs="+", type=float, default=[0.0, 0.25, 0.40, 0.60])
    parser.add_argument("--bin-width-values", nargs="+", type=int, default=[1, 2, 4, 8])
    parser.add_argument("--hint-missing-values", nargs="+", type=float, default=[0.0, 0.05, 0.10])
    parser.add_argument("--wrong-epoch-values", nargs="+", type=float, default=[0.0, 0.05])
    parser.add_argument("--straggler-values", nargs="+", type=float, default=[0.0, 0.05])
    args = parser.parse_args()

    e0 = run_e0(args)
    e2 = run_e2(args)
    e5 = run_e5(args)

    write_json(args.out_dir / "e0-sanity.json", e0)
    write_json(args.out_dir / "e2-waf-vs-utilization.json", e2)
    write_json(args.out_dir / "e5-bad-hints.json", e5)

    print_summary("E0 sanity", e0)
    print_summary("E2 WAF vs utilization", e2)
    print_summary("E5 bad hints", e5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
