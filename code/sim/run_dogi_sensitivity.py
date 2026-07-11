#!/usr/bin/env python3
"""Run QUASAR-DOGI sensitivity checks on a representative DOGI-shaped trace."""

from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path

import zns_pqc_verify as sim


def make_args(args: argparse.Namespace, **overrides) -> Namespace:
    values = {
        "trace": args.trace,
        "zones": args.zones,
        "zone_capacity": args.zone_capacity,
        "min_free_zones": args.min_free_zones,
        "lba_bucket_size": args.lba_bucket_size,
        "quasar_cert_epochs": args.quasar_cert_epochs,
        "quasar_min_epoch_fill": args.quasar_min_epoch_fill,
        "quasar_bin_width": args.quasar_bin_width,
        "quasar_open_zone_budget": args.quasar_open_zone_budget,
        "quasar_residual_threshold": -1,
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


def run(args: argparse.Namespace) -> list[dict]:
    rows: list[dict] = []

    for zones in args.zone_values:
        for policy in ("dogi-history", "quasar-dogi-hybrid"):
            ns = make_args(args, zones=zones)
            row = run_policy(ns, policy)
            row["experiment"] = "zone_pressure"
            rows.append(row)

    for missing_rate in args.hint_missing_values:
        ns = make_args(args, hint_missing_rate=missing_rate)
        row = run_policy_with_retry(ns, "quasar-dogi-hybrid")
        row["experiment"] = "hint_missing"
        row["hint_missing_rate"] = missing_rate
        rows.append(row)

    for wrong_rate in args.wrong_epoch_values:
        ns = make_args(args, wrong_epoch_rate=wrong_rate)
        row = run_policy_with_retry(ns, "quasar-dogi-hybrid")
        row["experiment"] = "wrong_epoch"
        row["wrong_epoch_rate"] = wrong_rate
        rows.append(row)

    for straggler_rate in args.straggler_values:
        ns = make_args(args, straggler_rate=straggler_rate)
        row = run_policy_with_retry(ns, "quasar-dogi-hybrid")
        row["experiment"] = "straggler"
        row["straggler_rate"] = straggler_rate
        rows.append(row)

    for residual_fraction in args.residual_fraction_values:
        ns = make_args(args, quasar_residual_fraction=residual_fraction)
        row = run_policy_with_retry(ns, "quasar-dogi-hybrid")
        row["experiment"] = "residual_fraction"
        row["quasar_residual_fraction"] = residual_fraction
        rows.append(row)

    return rows


def failure_row(ns: Namespace, policy: str, error: Exception) -> dict:
    return {
        "policy": policy,
        "trace": str(ns.trace),
        "zones": ns.zones,
        "zone_capacity": ns.zone_capacity,
        "failed": True,
        "error": str(error),
        "waf": 0.0,
        "gc_write_blocks": 0,
        "zone_utilization": 0.0,
        "epoch_impurity": 0.0,
        "intent_impurity": 0.0,
        "reset_eligibility": 0.0,
        "stale_secret_blocks_remaining": 0,
    }


def run_policy(ns: Namespace, policy: str) -> dict:
    try:
        row = sim.run_policy(ns, policy)
        row["failed"] = False
        return row
    except RuntimeError as error:
        return failure_row(ns, policy, error)


def run_policy_with_retry(ns: Namespace, policy: str) -> dict:
    requested_zones = ns.zones
    attempt = ns
    last_error: Exception | None = None
    for retry in range(4):
        row = run_policy(attempt, policy)
        row["requested_zones"] = requested_zones
        row["retry_count"] = retry
        if not row.get("failed"):
            return row
        last_error = RuntimeError(str(row.get("error", "failed")))
        attempt = Namespace(**{**vars(attempt), "zones": int(attempt.zones * 1.35) + 1})
    return failure_row(attempt, policy, last_error or RuntimeError("failed after retries"))


def fmt_float(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def fmt_int(value: object) -> str:
    if isinstance(value, float):
        value = int(value)
    return f"{value:,}"


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def write_outputs(rows: list[dict], json_out: Path, markdown_out: Path) -> None:
    json_out.parent.mkdir(parents=True, exist_ok=True)
    with json_out.open("w", encoding="utf-8") as out:
        json.dump(rows, out, indent=2, sort_keys=True)
        out.write("\n")

    by_experiment: dict[str, list[dict]] = {}
    for row in rows:
        by_experiment.setdefault(str(row["experiment"]), []).append(row)

    sections = ["# QUASAR-DOGI Sensitivity Summary", ""]
    for experiment, exp_rows in by_experiment.items():
        table_rows = []
        for row in exp_rows:
            setting = ""
            if experiment == "zone_pressure":
                setting = f"zones={row['zones']}"
            elif experiment == "hint_missing":
                setting = f"missing={row['hint_missing_rate']:.2f}"
            elif experiment == "wrong_epoch":
                setting = f"wrong={row['wrong_epoch_rate']:.2f}"
            elif experiment == "straggler":
                setting = f"straggler={row['straggler_rate']:.2f}"
            elif experiment == "residual_fraction":
                setting = f"residual={row['quasar_residual_fraction']:.2f}"
            table_rows.append(
                [
                    setting,
                    str(row["policy"]),
                    fmt_float(row["waf"]),
                    fmt_int(row["gc_write_blocks"]),
                    fmt_float(row["zone_utilization"]),
                    fmt_float(row["epoch_impurity"]),
                    fmt_int(row["stale_secret_blocks_remaining"]),
                    fmt_int(row.get("hint_missing_injected", 0)),
                    fmt_int(row.get("wrong_epoch_injected", 0)),
                    fmt_int(row.get("stragglers_injected", 0)),
                ]
            )
        sections.extend(
            [
                f"## {experiment}",
                "",
                markdown_table(
                    [
                        "Setting",
                        "Policy",
                        "WAF",
                        "GC Blocks",
                        "Zone Util",
                        "Epoch Impurity",
                        "Stale Secrets",
                        "Missing Hints",
                        "Wrong Epochs",
                        "Stragglers",
                    ],
                    table_rows,
                ),
                "",
            ]
        )

    markdown_out.parent.mkdir(parents=True, exist_ok=True)
    markdown_out.write_text("\n".join(sections), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, default=Path("artifacts/traces/dogi-paper-workloads-quick/exchange-pqc2000.jsonl"))
    parser.add_argument("--json-out", type=Path, default=Path("artifacts/results/dogi-paper-workloads-quick/sensitivity-summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/dogi-paper-workloads-quick/sensitivity-summary.md"))
    parser.add_argument("--zones", type=int, default=193)
    parser.add_argument("--zone-values", nargs="+", type=int, default=[193, 230, 280])
    parser.add_argument("--zone-capacity", type=int, default=512)
    parser.add_argument("--min-free-zones", type=int, default=8)
    parser.add_argument("--lba-bucket-size", type=int, default=4096)
    parser.add_argument("--quasar-cert-epochs", type=int, default=12)
    parser.add_argument("--quasar-min-epoch-fill", type=float, default=0.0)
    parser.add_argument("--quasar-bin-width", type=int, default=1)
    parser.add_argument("--quasar-open-zone-budget", type=int, default=0)
    parser.add_argument("--quasar-residual-fraction", type=float, default=0.0)
    parser.add_argument("--base-write-ns", type=int, default=10_000)
    parser.add_argument("--gc-copy-ns", type=int, default=15_000)
    parser.add_argument("--dogi-ml-ns-per-batch", type=int, default=600_000)
    parser.add_argument("--dogi-batch-size", type=int, default=128)
    parser.add_argument("--quasar-hint-ns", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--hint-missing-values", nargs="+", type=float, default=[0.0, 0.05, 0.10, 0.20])
    parser.add_argument("--wrong-epoch-values", nargs="+", type=float, default=[0.0, 0.05, 0.10])
    parser.add_argument("--straggler-values", nargs="+", type=float, default=[0.0, 0.05, 0.10])
    parser.add_argument("--residual-fraction-values", nargs="+", type=float, default=[0.0, 0.01, 0.05, 0.10])
    args = parser.parse_args()

    rows = run(args)
    write_outputs(rows, args.json_out, args.markdown_out)
    for row in rows:
        sim.print_row(row)
    print(f"wrote {args.json_out}")
    print(f"wrote {args.markdown_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
