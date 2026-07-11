#!/usr/bin/env python3
"""Replay simulator policy operations on a physical zonefs mount.

`physical_write_pressure_suite.py` proves that simulator-derived WAF accounting
turns into proportional bytes on the real ZNS device.  This script is more
direct: it asks the simulator to emit append/reset operations for each policy
and replays those logical zone operations on zonefs files.

The result is still not an exact external MiDAS/SepBIT/DOGI binary run.  It is a
physical placement-path replay for the in-repo FIFO/SepBIT/MiDAS/DOGI-history
and QUASAR policies.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, deque
from pathlib import Path
from typing import Any

try:
    import physical_zonefs_replay as zonefs
except ModuleNotFoundError:  # pragma: no cover
    from quasar import physical_zonefs_replay as zonefs

try:
    from sim import zns_pqc_verify as sim
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from sim import zns_pqc_verify as sim


DEFAULT_POLICIES = [
    "fifo",
    "midas-style",
    "dogi-history",
    "quasar",
    "quasar-dogi-hybrid",
]


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def workload_name(trace: Path) -> str:
    name = trace.name
    if name.endswith(".jsonl"):
        name = name[: -len(".jsonl")]
    return name


def load_trace_paths(args: argparse.Namespace) -> list[Path]:
    traces = list(args.trace)
    if args.trace_list:
        with args.trace_list.open("r", encoding="utf-8") as src:
            for line in src:
                line = line.strip()
                if line and not line.startswith("#"):
                    traces.append(Path(line))
    return traces


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
        return sim.make_quasar_policy(args)
    if policy_name == "quasar-adaptive":
        return sim.make_quasar_policy(args, adaptive=True)
    if policy_name == "quasar-dogi-hybrid":
        return sim.QuasarDogiHybridPolicy(
            quasar=sim.make_quasar_policy(args),
            dogi=sim.DogiHistoryPolicy(args.lba_bucket_size),
        )
    if policy_name == "quasar-adaptive-hybrid":
        return sim.QuasarDogiHybridPolicy(
            quasar=sim.make_quasar_policy(args, adaptive=True),
            dogi=sim.DogiHistoryPolicy(args.lba_bucket_size),
        )
    raise ValueError(policy_name)


def simulator_for(args: argparse.Namespace, policy_name: str, operation_log: list[dict[str, Any]]) -> sim.Simulator:
    quasar_policy_names = {
        "quasar",
        "quasar-dogi-hybrid",
        "quasar-adaptive",
        "quasar-adaptive-hybrid",
    }
    residual_threshold = 0
    if policy_name in quasar_policy_names:
        residual_threshold = args.quasar_residual_threshold
        if residual_threshold < 0:
            residual_threshold = int(args.zone_capacity * args.quasar_residual_fraction)
    return sim.Simulator(
        policy=make_policy(args, policy_name),
        zone_count=args.zones,
        zone_capacity=args.zone_capacity,
        min_free_zones=args.min_free_zones,
        residual_threshold=residual_threshold,
        hint_missing_rate=args.hint_missing_rate if policy_name in quasar_policy_names else 0.0,
        wrong_epoch_rate=args.wrong_epoch_rate if policy_name in quasar_policy_names else 0.0,
        straggler_rate=args.straggler_rate if policy_name in quasar_policy_names else 0.0,
        random_seed=args.seed,
        base_write_ns=args.base_write_ns,
        gc_copy_ns=args.gc_copy_ns,
        policy_cpu_ns_per_write=sim.policy_cpu_cost(args, policy_name),
        operation_log=operation_log,
    )


def coalesce_operations(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for op in operations:
        if (
            op["op"] == "append"
            and out
            and out[-1]["op"] == "append"
            and out[-1]["zone_id"] == op["zone_id"]
            and out[-1].get("is_gc") == op.get("is_gc")
        ):
            out[-1]["blocks"] += int(op.get("blocks", 1))
            out[-1]["coalesced_ops"] = int(out[-1].get("coalesced_ops", 1)) + 1
            out[-1]["last_ts"] = op.get("ts")
            continue
        row = dict(op)
        if row["op"] == "append":
            row["coalesced_ops"] = 1
            row["last_ts"] = row.get("ts")
        out.append(row)
    return out


def simulate_policy(trace: Path, policy_name: str, args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    operation_log: list[dict[str, Any]] = []
    simulator = simulator_for(args, policy_name, operation_log)
    stats = simulator.run(trace)
    stats["policy"] = policy_name
    stats["trace"] = str(trace)
    stats["zones"] = args.zones
    stats["zone_capacity"] = args.zone_capacity
    operations = coalesce_operations(operation_log) if args.coalesce else operation_log
    return stats, operations


def reset_zone_files(zone_files: list[Path], *, execute: bool, fail_fast: bool) -> tuple[list[dict[str, Any]], list[int]]:
    rows: list[dict[str, Any]] = []
    latencies: list[int] = []
    if not execute:
        return rows, latencies
    for path in zone_files:
        result = zonefs.run_truncate_reset(path)
        rows.append(result)
        latencies.append(int(result["latency_ns"]))
        if not result["succeeded"] and fail_fast:
            raise RuntimeError(f"initial zone reset failed: {json.dumps(result, sort_keys=True)}")
    return rows, latencies


def execute_operations(operations: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    zone_files = zonefs.select_zone_files(
        args.mount,
        start_index=args.start_zone_index,
        max_zone_files=args.max_zone_files,
        require_empty=False,
    )
    initial_resets, reset_latencies = reset_zone_files(
        zone_files,
        execute=args.execute,
        fail_fast=args.fail_fast,
    )
    free_files = deque(zone_files)
    logical_to_physical: dict[int, Path] = {}
    used_files_ever: set[Path] = set()
    append_latencies: list[int] = []
    failures: list[dict[str, Any]] = []
    executed_commands = 0
    append_operations = 0
    physical_append_commands = 0
    reset_commands = 0
    bytes_written = 0
    user_blocks = 0
    gc_blocks = 0
    prefill_blocks = 0
    max_allocated_files = 0
    max_open_files = 0
    sampled_rows: list[dict[str, Any]] = []
    zone_fill_blocks: dict[int, int] = {}
    open_zone_ids: set[int] = set()
    pending_append_blocks: Counter[int] = Counter()
    started = time.perf_counter_ns()

    def record(row: dict[str, Any]) -> None:
        if len(sampled_rows) < args.max_rows_in_output:
            sampled_rows.append(row)

    def issue_physical_append(zone_id: int, blocks: int) -> bool:
        nonlocal physical_append_commands
        target = logical_to_physical[zone_id]
        blocks_remaining = blocks
        while blocks_remaining > 0:
            chunk = blocks_remaining
            if args.max_blocks_per_dd:
                chunk = min(chunk, args.max_blocks_per_dd)
            if args.execute:
                result = zonefs.run_dd_append(target, chunk)
                if not result["succeeded"]:
                    failure = {
                        "op": "append",
                        "zone_id": zone_id,
                        "target": str(target),
                        "blocks": chunk,
                        **result,
                    }
                    failures.append(failure)
                    record(failure)
                    if args.fail_fast:
                        raise RuntimeError(f"append failed: {json.dumps(failure, sort_keys=True)}")
                    return False
                append_latencies.append(int(result["latency_ns"]))
            physical_append_commands += 1
            blocks_remaining -= chunk
        return True

    def flush_pending(zone_id: int) -> bool:
        blocks = int(pending_append_blocks.pop(zone_id, 0))
        if blocks <= 0:
            return True
        return issue_physical_append(zone_id, blocks)

    for operation in operations:
        if args.max_physical_commands and executed_commands >= args.max_physical_commands:
            break
        executed_commands += 1
        op = operation["op"]
        zone_id = int(operation["zone_id"])
        if op == "append":
            append_operations += 1
            if zone_id not in logical_to_physical:
                if not free_files:
                    failure = {
                        "op": "append",
                        "zone_id": zone_id,
                        "stderr": "no free selected zonefs files",
                        "active_files": len(logical_to_physical),
                    }
                    failures.append(failure)
                    record(failure)
                    if args.fail_fast:
                        raise RuntimeError(json.dumps(failure, sort_keys=True))
                    break
                logical_to_physical[zone_id] = free_files.popleft()
                used_files_ever.add(logical_to_physical[zone_id])
                zone_fill_blocks.setdefault(zone_id, 0)
            if zone_fill_blocks.get(zone_id, 0) < args.zone_capacity:
                open_zone_ids.add(zone_id)
            max_allocated_files = max(max_allocated_files, len(logical_to_physical))
            max_open_files = max(max_open_files, len(open_zone_ids))
            target = logical_to_physical[zone_id]
            blocks_remaining = int(operation.get("blocks", 1))
            row = {
                "op": "append",
                "zone_id": zone_id,
                "target": str(target),
                "blocks": blocks_remaining,
                "is_gc": bool(operation.get("is_gc")),
                "ts": operation.get("ts"),
                "last_ts": operation.get("last_ts"),
                "coalesced_ops": operation.get("coalesced_ops", 1),
            }
            while blocks_remaining > 0:
                chunk = blocks_remaining if args.batch_appends else min(
                    blocks_remaining,
                    args.max_blocks_per_dd or blocks_remaining,
                )
                bytes_written += chunk * 4096
                if operation.get("is_gc"):
                    gc_blocks += chunk
                elif operation.get("account_user", True):
                    user_blocks += chunk
                else:
                    prefill_blocks += chunk
                zone_fill_blocks[zone_id] = zone_fill_blocks.get(zone_id, 0) + chunk
                if zone_fill_blocks[zone_id] >= args.zone_capacity:
                    open_zone_ids.discard(zone_id)
                else:
                    open_zone_ids.add(zone_id)
                max_open_files = max(max_open_files, len(open_zone_ids))
                if args.batch_appends:
                    pending_append_blocks[zone_id] += chunk
                else:
                    if not issue_physical_append(zone_id, chunk):
                        break
                blocks_remaining -= chunk
            row["succeeded"] = not failures or failures[-1] is not row
            record(row)
            if failures:
                break
        elif op == "reset_zone":
            reset_commands += 1
            if args.batch_appends and not flush_pending(zone_id):
                break
            target = logical_to_physical.pop(zone_id, None)
            zone_fill_blocks.pop(zone_id, None)
            open_zone_ids.discard(zone_id)
            row = {
                "op": "reset_zone",
                "zone_id": zone_id,
                "target": str(target) if target else None,
                "ts": operation.get("ts"),
                "fill": operation.get("fill"),
                "live_blocks": operation.get("live_blocks"),
                "invalid_blocks": operation.get("invalid_blocks"),
                "succeeded": True,
            }
            if target is not None:
                if args.execute:
                    result = zonefs.run_truncate_reset(target)
                    row.update(result)
                    if not result["succeeded"]:
                        failures.append(row)
                        record(row)
                        if args.fail_fast:
                            raise RuntimeError(f"reset failed: {json.dumps(row, sort_keys=True)}")
                        break
                    reset_latencies.append(int(result["latency_ns"]))
                free_files.append(target)
            record(row)
        else:
            raise ValueError(op)

    if args.batch_appends and not failures:
        for zone_id in list(pending_append_blocks):
            if not flush_pending(zone_id):
                break

    cleanup_resets: list[dict[str, Any]] = []
    if args.execute and args.reset_at_end and not failures:
        for target in list(logical_to_physical.values()):
            result = zonefs.run_truncate_reset(target)
            cleanup_resets.append(result)
            reset_latencies.append(int(result["latency_ns"]))
            if not result["succeeded"] and args.fail_fast:
                raise RuntimeError(f"cleanup reset failed: {json.dumps(result, sort_keys=True)}")
        logical_to_physical.clear()
        zone_fill_blocks.clear()
        open_zone_ids.clear()

    wall_time_ns = time.perf_counter_ns() - started
    wall_s = wall_time_ns / 1_000_000_000
    return {
        "execute": args.execute,
        "failed": bool(failures),
        "failures": failures[:8],
        "truncated": bool(args.max_physical_commands and executed_commands < len(operations)),
        "operations_total": len(operations),
        "operations_executed": executed_commands,
        "append_operations_executed": append_operations,
        "append_commands_executed": physical_append_commands,
        "physical_append_commands_executed": physical_append_commands,
        "reset_commands_executed": reset_commands,
        "initial_reset_zones": len(initial_resets),
        "cleanup_reset_zones": len(cleanup_resets),
        "zone_files_available": len(zone_files),
        "zone_files_used": len(used_files_ever),
        "max_allocated_zone_files": max_allocated_files,
        "max_open_zone_files": max_open_files,
        "max_active_zone_files": max_open_files,
        "final_allocated_zone_files": len(logical_to_physical),
        "final_open_zone_files": len(open_zone_ids),
        "final_active_zone_files": len(open_zone_ids),
        "bytes_written": bytes_written,
        "user_blocks_written": user_blocks,
        "gc_blocks_written": gc_blocks,
        "prefill_blocks_written": prefill_blocks,
        "wall_time_ns": wall_time_ns,
        "wall_time_s": wall_s,
        "throughput_mib_s": (bytes_written / (1024 * 1024) / wall_s) if wall_s and args.execute else 0.0,
        "append_latency": zonefs.latency_summary(append_latencies),
        "reset_latency": zonefs.latency_summary(reset_latencies),
        "rows": sampled_rows,
    }


def run_suite(args: argparse.Namespace) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    started = time.perf_counter_ns()
    for trace in load_trace_paths(args):
        for policy in args.policies:
            try:
                stats, operations = simulate_policy(trace, policy, args)
            except Exception as exc:
                stats = {"policy": policy, "trace": str(trace), "failed": True, "error": str(exc)}
                operations = []
                physical = {
                    "execute": args.execute,
                    "failed": True,
                    "failures": [{"op": "simulate", "stderr": str(exc)}],
                    "operations_total": 0,
                    "operations_executed": 0,
                    "append_commands_executed": 0,
                    "reset_commands_executed": 0,
                    "initial_reset_zones": 0,
                    "cleanup_reset_zones": 0,
                    "zone_files_available": 0,
                    "zone_files_used": 0,
                    "max_active_zone_files": 0,
                    "final_active_zone_files": 0,
                    "bytes_written": 0,
                    "user_blocks_written": 0,
                    "gc_blocks_written": 0,
                    "prefill_blocks_written": 0,
                    "wall_time_ns": 0,
                    "wall_time_s": 0.0,
                    "throughput_mib_s": 0.0,
                    "append_latency": zonefs.latency_summary([]),
                    "reset_latency": zonefs.latency_summary([]),
                    "rows": [],
                }
            else:
                physical = execute_operations(operations, args)
            row = {
                "workload": workload_name(trace),
                "trace": str(trace),
                "policy": policy,
                "sim": stats,
                "physical": physical,
                "operation_count": len(operations),
                "append_operation_count": sum(1 for op in operations if op["op"] == "append"),
                "reset_operation_count": sum(1 for op in operations if op["op"] == "reset_zone"),
            }
            rows.append(row)
            if physical["failed"] and args.stop_on_failure:
                break
        if rows and rows[-1]["physical"]["failed"] and args.stop_on_failure:
            break
    wall_time_ns = time.perf_counter_ns() - started
    return {
        "suite": "physical-policy-zonefs-replay",
        "execute": args.execute,
        "mount": str(args.mount),
        "policies": args.policies,
        "traces": [str(path) for path in load_trace_paths(args)],
        "zones": args.zones,
        "zone_capacity": args.zone_capacity,
        "max_zone_files": args.max_zone_files,
        "max_physical_commands": args.max_physical_commands,
        "coalesce": args.coalesce,
        "batch_appends": args.batch_appends,
        "reset_at_end": args.reset_at_end,
        "rows": rows,
        "summary": summarize(rows, wall_time_ns),
    }


def summarize(rows: list[dict[str, Any]], wall_time_ns: int) -> dict[str, Any]:
    by_policy: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = by_policy.setdefault(
            row["policy"],
            {
                "rows": 0,
                "failed_rows": 0,
                "sim_user_blocks": 0,
                "sim_gc_blocks": 0,
                "sim_stale_secret_blocks": 0,
                "physical_bytes_written": 0,
                "physical_user_blocks": 0,
                "physical_gc_blocks": 0,
                "physical_prefill_blocks": 0,
                "physical_resets": 0,
                "physical_append_commands": 0,
                "max_active_zone_files": 0,
                "max_open_zone_files": 0,
                "max_allocated_zone_files": 0,
                "zone_files_used": 0,
            },
        )
        sim_stats = row["sim"]
        physical = row["physical"]
        item["rows"] += 1
        item["failed_rows"] += int(bool(physical["failed"]))
        item["sim_user_blocks"] += int(sim_stats.get("user_write_blocks", 0))
        item["sim_gc_blocks"] += int(sim_stats.get("gc_write_blocks", 0))
        item["sim_stale_secret_blocks"] += int(sim_stats.get("stale_secret_blocks_remaining", 0))
        item["physical_bytes_written"] += int(physical.get("bytes_written", 0))
        item["physical_user_blocks"] += int(physical.get("user_blocks_written", 0))
        item["physical_gc_blocks"] += int(physical.get("gc_blocks_written", 0))
        item["physical_prefill_blocks"] += int(physical.get("prefill_blocks_written", 0))
        item["physical_resets"] += int(physical.get("reset_commands_executed", 0))
        item["physical_append_commands"] += int(physical.get("physical_append_commands_executed", physical.get("append_commands_executed", 0)))
        max_open = int(physical.get("max_open_zone_files", physical.get("max_active_zone_files", 0)))
        max_allocated = int(physical.get("max_allocated_zone_files", physical.get("max_active_zone_files", 0)))
        item["max_open_zone_files"] = max(item["max_open_zone_files"], max_open)
        item["max_active_zone_files"] = max(item["max_active_zone_files"], max_open)
        item["max_allocated_zone_files"] = max(item["max_allocated_zone_files"], max_allocated)
        item["zone_files_used"] += int(physical.get("zone_files_used", 0))
    for item in by_policy.values():
        user = max(1, int(item["sim_user_blocks"]))
        item["sim_waf"] = (int(item["sim_user_blocks"]) + int(item["sim_gc_blocks"])) / user
    dogi = by_policy.get("dogi-history", {})
    hybrid = by_policy.get("quasar-dogi-hybrid", {})
    comparison = {}
    if dogi and hybrid:
        dogi_blocks = int(dogi.get("physical_user_blocks", 0)) + int(dogi.get("physical_gc_blocks", 0))
        hybrid_blocks = int(hybrid.get("physical_user_blocks", 0)) + int(hybrid.get("physical_gc_blocks", 0))
        dogi_total_blocks = dogi_blocks + int(dogi.get("physical_prefill_blocks", 0))
        hybrid_total_blocks = hybrid_blocks + int(hybrid.get("physical_prefill_blocks", 0))
        comparison = {
            "dogi_physical_blocks": dogi_blocks,
            "hybrid_physical_blocks": hybrid_blocks,
            "dogi_total_physical_blocks_including_prefill": dogi_total_blocks,
            "hybrid_total_physical_blocks_including_prefill": hybrid_total_blocks,
            "hybrid_block_reduction_vs_dogi": (
                (dogi_blocks - hybrid_blocks) / dogi_blocks if dogi_blocks else 0.0
            ),
            "hybrid_total_block_reduction_vs_dogi_including_prefill": (
                (dogi_total_blocks - hybrid_total_blocks) / dogi_total_blocks if dogi_total_blocks else 0.0
            ),
            "stale_secret_blocks_avoided": int(dogi.get("sim_stale_secret_blocks", 0))
            - int(hybrid.get("sim_stale_secret_blocks", 0)),
        }
    return {
        "row_count": len(rows),
        "failed_rows": sum(1 for row in rows if row["physical"]["failed"]),
        "wall_time_s": wall_time_ns / 1_000_000_000,
        "by_policy": by_policy,
        "dogi_vs_hybrid": comparison,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Physical Policy Zonefs Replay Suite",
        "",
        f"- Executed: `{report['execute']}`",
        f"- Mount: `{report['mount']}`",
        f"- Rows: `{report['summary']['row_count']}`",
        f"- Failed rows: `{report['summary']['failed_rows']}`",
        f"- Coalesced operations: `{report['coalesce']}`",
        f"- Batched physical appends: `{report['batch_appends']}`",
        f"- Max physical commands per row: `{report['max_physical_commands']}`",
        "",
        "| Policy | Rows | Sim WAF | Physical MiB | Measured Blocks | Prefill Blocks | Append Cmds | Resets | Max Open Zones | Max Allocated Zones | Stale Secrets | Failed Rows |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for policy, item in sorted(report["summary"]["by_policy"].items()):
        mib = int(item["physical_bytes_written"]) / (1024 * 1024)
        measured_blocks = int(item["physical_user_blocks"]) + int(item["physical_gc_blocks"])
        lines.append(
            "| `{}` | {} | {:.4f} | {:.1f} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                policy,
                item["rows"],
                item["sim_waf"],
                mib,
                measured_blocks,
                item["physical_prefill_blocks"],
                item["physical_append_commands"],
                item["physical_resets"],
                item.get("max_open_zone_files", item["max_active_zone_files"]),
                item.get("max_allocated_zone_files", item["max_active_zone_files"]),
                item["sim_stale_secret_blocks"],
                item["failed_rows"],
            )
        )
    comparison = report["summary"].get("dogi_vs_hybrid", {})
    if comparison:
        lines.extend(
            [
                "",
                "DOGI vs QUASAR-DOGI hybrid:",
                "",
                "| Metric | Value |",
                "| --- | ---: |",
                f"| DOGI physical blocks | {comparison['dogi_physical_blocks']} |",
                f"| Hybrid physical blocks | {comparison['hybrid_physical_blocks']} |",
                f"| DOGI total physical blocks including prefill | {comparison['dogi_total_physical_blocks_including_prefill']} |",
                f"| Hybrid total physical blocks including prefill | {comparison['hybrid_total_physical_blocks_including_prefill']} |",
                f"| Hybrid block reduction vs DOGI | {comparison['hybrid_block_reduction_vs_dogi']:.4%} |",
                f"| Hybrid total block reduction vs DOGI including prefill | {comparison['hybrid_total_block_reduction_vs_dogi_including_prefill']:.4%} |",
                f"| Stale secret blocks avoided | {comparison['stale_secret_blocks_avoided']} |",
            ]
        )
    lines.extend(
        [
            "",
            "Interpretation:",
            "",
            "```text",
            "This suite replays simulator policy operations on physical zonefs files.",
            "It is stronger than byte-pressure replay because logical append/reset placement is executed.",
            "It is weaker than an exact external MiDAS/SepBIT/DOGI binary run because policy decisions still come from the in-repo simulator.",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", action="append", type=Path, default=[])
    parser.add_argument("--trace-list", type=Path)
    parser.add_argument("--mount", type=Path, default=Path("/mnt/zn540"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--policies", type=parse_csv, default=DEFAULT_POLICIES)
    parser.add_argument("--zones", type=int, default=64)
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
    parser.add_argument("--quasar-adaptive-exact-min-blocks", type=int, default=4)
    parser.add_argument("--quasar-adaptive-tenant-bin-width", type=int, default=16)
    parser.add_argument("--quasar-adaptive-coarse-bin-width", type=int, default=32_000_000)
    parser.add_argument("--quasar-adaptive-coarse-pressure", type=float, default=0.75)
    parser.add_argument("--quasar-adaptive-family-pressure", type=float, default=8.0)
    parser.add_argument("--quasar-adaptive-urgent-lifetime", type=int, default=32)
    parser.add_argument("--hint-missing-rate", type=float, default=0.0)
    parser.add_argument("--wrong-epoch-rate", type=float, default=0.0)
    parser.add_argument("--straggler-rate", type=float, default=0.0)
    parser.add_argument("--base-write-ns", type=int, default=10_000)
    parser.add_argument("--gc-copy-ns", type=int, default=15_000)
    parser.add_argument("--dogi-ml-ns-per-batch", type=int, default=600_000)
    parser.add_argument("--dogi-batch-size", type=int, default=128)
    parser.add_argument("--quasar-hint-ns", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--start-zone-index", type=int, default=100)
    parser.add_argument("--max-zone-files", type=int, default=32)
    parser.add_argument("--max-blocks-per-dd", type=int, default=256)
    parser.add_argument("--max-physical-commands", type=int, default=20000)
    parser.add_argument("--max-rows-in-output", type=int, default=64)
    parser.add_argument("--coalesce", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--batch-appends", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--reset-at-end", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--stop-on-failure", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/physical-policy-zonefs-replay.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/physical-policy-zonefs-replay.md"))
    args = parser.parse_args()

    if not load_trace_paths(args):
        raise SystemExit("at least one --trace or --trace-list entry is required")
    report = run_suite(args)
    write_json(args.out, report)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text(markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "execute": report["execute"],
                "rows": report["summary"]["row_count"],
                "failed_rows": report["summary"]["failed_rows"],
            },
            sort_keys=True,
        )
    )
    return 1 if report["summary"]["failed_rows"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
