#!/usr/bin/env python3
"""Generate stale-secret exposure timelines for QUASAR E4.

The aggregate simulator metric `stale_secret_block_seconds` is useful, but the
paper needs a time-window view: after an epoch expires, do secret bytes remain
resident or drop immediately? This script reuses the simulator policies and
samples remaining stale secret blocks over time.
"""

from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path

import matplotlib.pyplot as plt

try:
    import zns_pqc_verify as sim
except ModuleNotFoundError:  # pragma: no cover - used by root-level imports
    from sim import zns_pqc_verify as sim


POLICY_LABELS = {
    "fifo": "FIFO",
    "sepbit-style": "SepBIT-style",
    "midas-style": "MiDAS-style",
    "dogi-history": "DOGI-style",
    "quasar": "QUASAR",
    "quasar-dogi-hybrid": "QUASAR-DOGI hybrid",
    "epoch-oracle": "Epoch oracle",
}


def policy_for(args: Namespace, policy_name: str) -> sim.Policy:
    if policy_name == "fifo":
        return sim.FifoPolicy()
    if policy_name == "sepbit-style":
        return sim.SepbitStylePolicy(args.lba_bucket_size)
    if policy_name == "midas-style":
        return sim.MidasStylePolicy(args.lba_bucket_size)
    if policy_name == "dogi-history":
        return sim.DogiHistoryPolicy(args.lba_bucket_size)
    if policy_name == "epoch-oracle":
        return sim.EpochOraclePolicy()
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
            overflow_enabled=not args.quasar_disable_overflow,
            secret_priority=not args.quasar_disable_secret_priority,
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
                overflow_enabled=not args.quasar_disable_overflow,
                secret_priority=not args.quasar_disable_secret_priority,
            ),
            dogi=sim.DogiHistoryPolicy(args.lba_bucket_size),
        )
    raise ValueError(policy_name)


def residual_threshold_for(args: Namespace, policy_name: str) -> int:
    if policy_name not in {"quasar", "quasar-dogi-hybrid"}:
        return 0
    if args.quasar_residual_threshold >= 0:
        return args.quasar_residual_threshold
    return int(args.zone_capacity * args.quasar_residual_fraction)


def make_simulator(args: Namespace, policy_name: str) -> sim.Simulator:
    return sim.Simulator(
        policy=policy_for(args, policy_name),
        zone_count=args.zones,
        zone_capacity=args.zone_capacity,
        min_free_zones=args.min_free_zones,
        residual_threshold=residual_threshold_for(args, policy_name),
        hint_missing_rate=args.hint_missing_rate if policy_name in {"quasar", "quasar-dogi-hybrid"} else 0.0,
        wrong_epoch_rate=args.wrong_epoch_rate if policy_name in {"quasar", "quasar-dogi-hybrid"} else 0.0,
        straggler_rate=args.straggler_rate if policy_name in {"quasar", "quasar-dogi-hybrid"} else 0.0,
        random_seed=args.seed,
        base_write_ns=args.base_write_ns,
        gc_copy_ns=args.gc_copy_ns,
        policy_cpu_ns_per_write=sim.policy_cpu_cost(args, policy_name),
    )


def run_timeline(args: Namespace, policy_name: str) -> list[dict]:
    simulator = make_simulator(args, policy_name)
    rows: list[dict] = []
    next_sample_ts = 0
    with args.trace.open("r", encoding="utf-8") as trace:
        for line in trace:
            if not line.strip():
                continue
            event = json.loads(line)
            simulator.current_ts = int(event["ts"])
            if event["op"] == "write":
                simulator.write(event)
            elif event["op"] == "prefill":
                simulator.write(event, account_user=False)
            elif event["op"] == "expire":
                simulator.expire(event)
            else:
                raise ValueError(f"unknown op: {event['op']}")
            if simulator.current_ts >= next_sample_ts or (args.sample_on_expire and event["op"] == "expire"):
                rows.append(sample_row(simulator, policy_name))
                while next_sample_ts <= simulator.current_ts:
                    next_sample_ts += args.sample_interval
    rows.append(sample_row(simulator, policy_name))
    return rows


def sample_row(simulator: sim.Simulator, policy_name: str) -> dict:
    remaining, block_seconds, max_exposure = simulator._remaining_secret_exposure()
    return {
        "policy": policy_name,
        "ts": simulator.current_ts,
        "stale_secret_blocks": remaining,
        "stale_secret_block_seconds_remaining": block_seconds,
        "max_secret_exposure_time_remaining": max_exposure,
        "resets": simulator.reset_count,
        "gc_write_blocks": simulator.gc_write_blocks,
        "user_write_blocks": simulator.user_write_blocks,
    }


def write_json(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def plot(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    by_policy: dict[str, list[dict]] = {}
    for row in rows:
        by_policy.setdefault(row["policy"], []).append(row)
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for policy, vals in by_policy.items():
        vals = sorted(vals, key=lambda row: row["ts"])
        ax.plot(
            [row["ts"] for row in vals],
            [row["stale_secret_blocks"] for row in vals],
            label=POLICY_LABELS.get(policy, policy),
            linewidth=2.0,
        )
    ax.set_xlabel("Trace timestamp")
    ax.set_ylabel("Stale secret blocks remaining")
    ax.set_title("E4: stale-secret exposure window")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=9)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    print(f"wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--zones", type=int, default=256)
    parser.add_argument("--zone-capacity", type=int, default=512)
    parser.add_argument("--min-free-zones", type=int, default=4)
    parser.add_argument("--lba-bucket-size", type=int, default=4096)
    parser.add_argument("--quasar-cert-epochs", type=int, default=12)
    parser.add_argument("--quasar-min-epoch-fill", type=float, default=0.0)
    parser.add_argument("--quasar-bin-width", type=int, default=1)
    parser.add_argument("--quasar-open-zone-budget", type=int, default=0)
    parser.add_argument("--quasar-residual-threshold", type=int, default=-1)
    parser.add_argument("--quasar-residual-fraction", type=float, default=0.0)
    parser.add_argument("--quasar-disable-overflow", action="store_true")
    parser.add_argument("--quasar-disable-secret-priority", action="store_true")
    parser.add_argument("--hint-missing-rate", type=float, default=0.0)
    parser.add_argument("--wrong-epoch-rate", type=float, default=0.0)
    parser.add_argument("--straggler-rate", type=float, default=0.0)
    parser.add_argument("--base-write-ns", type=int, default=10_000)
    parser.add_argument("--gc-copy-ns", type=int, default=15_000)
    parser.add_argument("--dogi-ml-ns-per-batch", type=int, default=600_000)
    parser.add_argument("--dogi-batch-size", type=int, default=128)
    parser.add_argument("--quasar-hint-ns", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--sample-interval", type=int, default=1000)
    parser.add_argument("--sample-on-expire", action="store_true")
    parser.add_argument("--policies", nargs="+", default=["fifo", "dogi-history", "quasar"])
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/e4-exposure-timeline.json"))
    parser.add_argument("--figure", type=Path, default=Path("artifacts/figures/e4-exposure-timeline.png"))
    args = parser.parse_args()

    rows: list[dict] = []
    for policy_name in args.policies:
        rows.extend(run_timeline(args, policy_name))
    write_json(args.out, rows)
    print(f"wrote {args.out}")
    plot(rows, args.figure)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
