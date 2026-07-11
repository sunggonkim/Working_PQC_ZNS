#!/usr/bin/env python3
"""Microbenchmark simulator policy-decision overhead.

This is not a production CPU measurement. It is a trace-driven Python
microbenchmark that measures the cost of the current policy implementations'
decision path: storage-visible DOGI-style feature extraction versus QUASAR
intent/epoch routing. The final paper still needs C/C++ or real replay CPU
measurements.
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import time
from pathlib import Path

try:
    import zns_pqc_verify as sim
except ModuleNotFoundError:  # pragma: no cover
    from sim import zns_pqc_verify as sim


def load_events(path: Path) -> list[dict]:
    events = []
    with path.open("r", encoding="utf-8") as src:
        for line in src:
            if line.strip():
                events.append(json.loads(line))
    return events


def make_policy(args: argparse.Namespace, policy_name: str) -> sim.Policy:
    if policy_name == "fifo":
        return sim.FifoPolicy()
    if policy_name == "sepbit-style":
        return sim.SepbitStylePolicy(args.lba_bucket_size)
    if policy_name == "midas-style":
        return sim.MidasStylePolicy(args.lba_bucket_size)
    if policy_name == "dogi-history":
        return sim.DogiHistoryPolicy(args.lba_bucket_size)
    if policy_name == "quasar":
        open_zone_budget = args.quasar_open_zone_budget
        if open_zone_budget <= 0:
            open_zone_budget = max(1, int((args.zones - args.min_free_zones) * 0.8))
        return sim.QuasarPolicy(
            zone_capacity=args.zone_capacity,
            cert_epochs=args.quasar_cert_epochs,
            bin_width=args.quasar_bin_width,
            min_epoch_fill=args.quasar_min_epoch_fill,
            open_zone_budget=open_zone_budget,
            overflow_enabled=True,
            secret_priority=True,
        )
    if policy_name == "quasar-dogi-hybrid":
        open_zone_budget = args.quasar_open_zone_budget
        if open_zone_budget <= 0:
            open_zone_budget = max(1, int((args.zones - args.min_free_zones) * 0.8))
        return sim.QuasarDogiHybridPolicy(
            quasar=sim.QuasarPolicy(
                zone_capacity=args.zone_capacity,
                cert_epochs=args.quasar_cert_epochs,
                bin_width=args.quasar_bin_width,
                min_epoch_fill=args.quasar_min_epoch_fill,
                open_zone_budget=open_zone_budget,
                overflow_enabled=True,
                secret_priority=True,
            ),
            dogi=sim.DogiHistoryPolicy(args.lba_bucket_size),
        )
    if policy_name == "epoch-oracle":
        return sim.EpochOraclePolicy()
    raise ValueError(policy_name)


def run_once(args: argparse.Namespace, events: list[dict], policy_name: str) -> dict:
    policy = make_policy(args, policy_name)
    writes_by_object: dict[int, dict] = {}
    write_ops = 0
    expire_ops = 0

    start = time.perf_counter_ns()
    for event in events:
        op = event["op"]
        if op in {"write", "prefill"}:
            policy.assign(event)
            writes_by_object[event["object_id"]] = event
            write_ops += 1
        elif op == "expire":
            write_event = writes_by_object.get(event["object_id"])
            if write_event is not None:
                policy.observe_expire(event, write_event)
            expire_ops += 1
    elapsed_ns = time.perf_counter_ns() - start
    total_ops = write_ops + expire_ops
    return {
        "elapsed_ns": elapsed_ns,
        "write_ops": write_ops,
        "expire_ops": expire_ops,
        "total_ops": total_ops,
        "ns_per_total_op": elapsed_ns / total_ops if total_ops else 0.0,
        "ns_per_write_op": elapsed_ns / write_ops if write_ops else 0.0,
    }


def benchmark(args: argparse.Namespace, trace: Path, events: list[dict], policy_name: str) -> dict:
    samples = []
    old_gc = gc.isenabled()
    gc.disable()
    try:
        for _ in range(args.repeats):
            samples.append(run_once(args, events, policy_name))
    finally:
        if old_gc:
            gc.enable()

    ns_per_total = [sample["ns_per_total_op"] for sample in samples]
    ns_per_write = [sample["ns_per_write_op"] for sample in samples]
    elapsed = [sample["elapsed_ns"] for sample in samples]
    first = samples[0]
    return {
        "trace": str(trace),
        "policy": policy_name,
        "repeats": args.repeats,
        "write_ops": first["write_ops"],
        "expire_ops": first["expire_ops"],
        "total_ops": first["total_ops"],
        "elapsed_ns_median": statistics.median(elapsed),
        "elapsed_ns_min": min(elapsed),
        "ns_per_total_op_median": statistics.median(ns_per_total),
        "ns_per_total_op_min": min(ns_per_total),
        "ns_per_write_op_median": statistics.median(ns_per_write),
        "ns_per_write_op_min": min(ns_per_write),
    }


def write_markdown(rows: list[dict], path: Path) -> None:
    lines = [
        "# Policy Decision Microbenchmark",
        "",
        "This is a Python prototype microbenchmark, not a production CPU measurement.",
        "",
        "| Trace | Policy | Writes | Expires | Median ns/op | Min ns/op | Median ns/write |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| `{trace}` | `{policy}` | {writes:,} | {expires:,} | {ns_op:,.1f} | {min_op:,.1f} | {ns_write:,.1f} |".format(
                trace=Path(row["trace"]).name,
                policy=row["policy"],
                writes=row["write_ops"],
                expires=row["expire_ops"],
                ns_op=row["ns_per_total_op_median"],
                min_op=row["ns_per_total_op_min"],
                ns_write=row["ns_per_write_op_median"],
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--traces", nargs="+", type=Path, required=True)
    parser.add_argument(
        "--policies",
        nargs="+",
        default=["fifo", "dogi-history", "quasar", "quasar-dogi-hybrid"],
    )
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--zones", type=int, default=256)
    parser.add_argument("--zone-capacity", type=int, default=512)
    parser.add_argument("--min-free-zones", type=int, default=8)
    parser.add_argument("--lba-bucket-size", type=int, default=4096)
    parser.add_argument("--quasar-cert-epochs", type=int, default=12)
    parser.add_argument("--quasar-min-epoch-fill", type=float, default=0.0)
    parser.add_argument("--quasar-bin-width", type=int, default=1)
    parser.add_argument("--quasar-open-zone-budget", type=int, default=0)
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/policy-overhead.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/policy-overhead.md"))
    args = parser.parse_args()

    rows = []
    for trace in args.traces:
        events = load_events(trace)
        for policy_name in args.policies:
            row = benchmark(args, trace, events, policy_name)
            rows.append(row)
            print(
                "{trace} {policy}: {ns:.1f} ns/op".format(
                    trace=trace.name,
                    policy=policy_name,
                    ns=row["ns_per_total_op_median"],
                )
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(rows, args.markdown_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
