#!/usr/bin/env python3
"""Run QUASAR-DOGI robustness checks across multiple workloads."""

from __future__ import annotations

import argparse
import json
import math
from argparse import Namespace
from pathlib import Path

try:
    import zns_pqc_verify as sim
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from sim import zns_pqc_verify as sim


DEFAULT_WORKLOADS = [
    "fio-zipf=artifacts/traces/dogi-paper-workloads-smoke/fio-zipf-pqc2000.jsonl",
    "varmail=artifacts/traces/dogi-paper-workloads-smoke/varmail-pqc2000.jsonl",
    "ycsb-f=artifacts/traces/dogi-paper-workloads-smoke/ycsb-f-pqc2000.jsonl",
    "kms=artifacts/traces/liboqs-profiles/traces/kms-rotation.jsonl",
]


def parse_workload(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        path = Path(spec)
        return path.stem, path
    name, path = spec.split("=", 1)
    return name, Path(path)


def max_live_blocks(trace: Path) -> int:
    live_by_object: dict[int, int] = {}
    live = 0
    peak = 0
    with trace.open("r", encoding="utf-8") as src:
        for line in src:
            event = json.loads(line)
            op = event["op"]
            object_id = int(event["object_id"])
            size_blocks = int(event["size_blocks"])
            if op in {"write", "prefill"}:
                old = live_by_object.get(object_id, 0)
                live += size_blocks - old
                live_by_object[object_id] = size_blocks
                peak = max(peak, live)
            elif op == "expire":
                live -= live_by_object.pop(object_id, 0)
    return peak


def auto_zones(args: argparse.Namespace, trace: Path) -> int:
    if args.zones:
        return args.zones
    peak_live = max_live_blocks(trace)
    usable = math.ceil((peak_live * (1.0 + args.auto_op_ratio)) / args.zone_capacity)
    return max(args.min_free_zones + 1, usable + args.min_free_zones)


def base_args(args: argparse.Namespace, trace: Path, zones: int, **overrides) -> Namespace:
    values = {
        "trace": trace,
        "zones": zones,
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


def failure_row(ns: Namespace, policy: str, workload: str, experiment: str, error: Exception) -> dict:
    return {
        "policy": policy,
        "workload": workload,
        "experiment": experiment,
        "trace": str(ns.trace),
        "zones": ns.zones,
        "zone_capacity": ns.zone_capacity,
        "failed": True,
        "error": str(error),
        "waf": 0.0,
        "gc_write_blocks": 0,
        "zone_utilization": 0.0,
        "closed_zone_fill_avg": 0.0,
        "epoch_impurity": 0.0,
        "intent_impurity": 0.0,
        "stale_secret_blocks_remaining": 0,
    }


def run_policy_with_retry(ns: Namespace, policy: str, workload: str, experiment: str, max_retries: int) -> dict:
    requested_zones = ns.zones
    attempt_ns = ns
    last_error: Exception | None = None
    for retry in range(max_retries + 1):
        try:
            row = sim.run_policy(attempt_ns, policy)
            row["failed"] = False
            row["workload"] = workload
            row["experiment"] = experiment
            row["requested_zones"] = requested_zones
            row["retry_count"] = retry
            return row
        except RuntimeError as error:
            last_error = error
            attempt_ns = Namespace(**{**vars(attempt_ns), "zones": int(attempt_ns.zones * args_retry_factor()) + 1})
    return failure_row(attempt_ns, policy, workload, experiment, last_error or RuntimeError("failed"))


def args_retry_factor() -> float:
    return 1.35


def experiment_args(args: argparse.Namespace, trace: Path, zones: int) -> list[tuple[str, str, Namespace]]:
    items: list[tuple[str, str, Namespace]] = [
        ("dogi_baseline", "dogi-history", base_args(args, trace, zones)),
        ("clean", "quasar-dogi-hybrid", base_args(args, trace, zones)),
    ]
    for value in args.hint_missing_values:
        items.append(
            (
                f"missing-{value:.2f}",
                "quasar-dogi-hybrid",
                base_args(args, trace, zones, hint_missing_rate=value),
            )
        )
    for value in args.wrong_epoch_values:
        items.append(
            (
                f"wrong-{value:.2f}",
                "quasar-dogi-hybrid",
                base_args(args, trace, zones, wrong_epoch_rate=value),
            )
        )
    for value in args.straggler_values:
        items.append(
            (
                f"straggler-{value:.2f}",
                "quasar-dogi-hybrid",
                base_args(args, trace, zones, straggler_rate=value),
            )
        )
    return items


def run(args: argparse.Namespace) -> list[dict]:
    rows: list[dict] = []
    for spec in args.workloads:
        workload, trace = parse_workload(spec)
        if not trace.exists():
            raise SystemExit(f"missing trace for {workload}: {trace}")
        zones = auto_zones(args, trace)
        print(f"== {workload} zones={zones} trace={trace} ==")
        for experiment, policy, ns in experiment_args(args, trace, zones):
            row = run_policy_with_retry(ns, policy, workload, experiment, args.max_retries)
            rows.append(row)
            sim.print_row(row)
    return rows


def fmt_float(value: object, digits: int = 3) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def fmt_int(value: object) -> str:
    if isinstance(value, float):
        value = int(value)
    return f"{value:,}"


def improvement(dogi: dict | None, row: dict) -> float | None:
    if dogi is None or dogi.get("waf", 0) == 0:
        return None
    return (dogi["waf"] - row["waf"]) / dogi["waf"] * 100.0


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def summarize(rows: list[dict]) -> dict:
    by_workload: dict[str, list[dict]] = {}
    for row in rows:
        by_workload.setdefault(row["workload"], []).append(row)
    summary: dict[str, dict] = {}
    for workload, workload_rows in by_workload.items():
        dogi = next((r for r in workload_rows if r["experiment"] == "dogi_baseline"), None)
        clean = next((r for r in workload_rows if r["experiment"] == "clean"), None)
        perturbations = [r for r in workload_rows if r["experiment"] not in {"dogi_baseline", "clean"}]
        summary[workload] = {
            "dogi_waf": dogi.get("waf") if dogi else None,
            "clean_waf": clean.get("waf") if clean else None,
            "clean_waf_vs_dogi_pct": improvement(dogi, clean) if dogi and clean else None,
            "clean_stale_secret_blocks": clean.get("stale_secret_blocks_remaining") if clean else None,
            "max_perturbed_waf": max((r["waf"] for r in perturbations if not r.get("failed")), default=None),
            "max_perturbed_stale_secret_blocks": max(
                (r["stale_secret_blocks_remaining"] for r in perturbations if not r.get("failed")),
                default=None,
            ),
            "failed_runs": sum(1 for r in workload_rows if r.get("failed")),
        }
    return summary


def write_outputs(rows: list[dict], json_out: Path, markdown_out: Path) -> None:
    summary = summarize(rows)
    payload = {"summary": summary, "rows": rows}
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    sections = ["# Cross-Workload Hint Robustness", ""]
    overview_rows = []
    for workload in sorted(summary):
        item = summary[workload]
        overview_rows.append(
            [
                f"`{workload}`",
                fmt_float(item["dogi_waf"]),
                fmt_float(item["clean_waf"]),
                "N/A" if item["clean_waf_vs_dogi_pct"] is None else f"{item['clean_waf_vs_dogi_pct']:.1f}%",
                fmt_int(item["clean_stale_secret_blocks"]),
                fmt_float(item["max_perturbed_waf"]),
                fmt_int(item["max_perturbed_stale_secret_blocks"]),
                fmt_int(item["failed_runs"]),
            ]
        )
    sections.extend(
        [
            "## Overview",
            "",
            markdown_table(
                [
                    "Workload",
                    "DOGI WAF",
                    "Clean Hybrid WAF",
                    "Clean vs DOGI",
                    "Clean Stale",
                    "Max Perturbed WAF",
                    "Max Perturbed Stale",
                    "Failed Runs",
                ],
                overview_rows,
            ),
            "",
        ]
    )

    for workload in sorted({row["workload"] for row in rows}):
        detail_rows = []
        for row in [r for r in rows if r["workload"] == workload]:
            detail_rows.append(
                [
                    row["experiment"],
                    row["policy"],
                    fmt_float(row["waf"]),
                    fmt_int(row["gc_write_blocks"]),
                    fmt_float(row["zone_utilization"]),
                    fmt_float(row["epoch_impurity"]),
                    fmt_int(row["stale_secret_blocks_remaining"]),
                    fmt_int(row.get("hint_missing_injected", 0)),
                    fmt_int(row.get("wrong_epoch_injected", 0)),
                    fmt_int(row.get("stragglers_injected", 0)),
                    "yes" if row.get("failed") else "no",
                ]
            )
        sections.extend(
            [
                f"## {workload}",
                "",
                markdown_table(
                    [
                        "Experiment",
                        "Policy",
                        "WAF",
                        "GC Blocks",
                        "Zone Util",
                        "Epoch Impurity",
                        "Stale Secrets",
                        "Missing",
                        "Wrong",
                        "Stragglers",
                        "Failed",
                    ],
                    detail_rows,
                ),
                "",
            ]
        )
    markdown_out.parent.mkdir(parents=True, exist_ok=True)
    markdown_out.write_text("\n".join(sections), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workloads", nargs="+", default=DEFAULT_WORKLOADS)
    parser.add_argument("--json-out", type=Path, default=Path("artifacts/results/robustness-suite/summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/robustness-suite/summary.md"))
    parser.add_argument("--zones", type=int, default=0)
    parser.add_argument("--auto-op-ratio", type=float, default=0.10)
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
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--hint-missing-values", nargs="+", type=float, default=[0.05, 0.10, 0.20])
    parser.add_argument("--wrong-epoch-values", nargs="+", type=float, default=[0.05, 0.10])
    parser.add_argument("--straggler-values", nargs="+", type=float, default=[0.05, 0.10])
    args = parser.parse_args()

    rows = run(args)
    write_outputs(rows, args.json_out, args.markdown_out)
    print(f"wrote {args.json_out}")
    print(f"wrote {args.markdown_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
