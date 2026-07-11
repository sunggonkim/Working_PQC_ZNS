#!/usr/bin/env python3
"""Execute packed logical-zone replay on physical zonefs files.

`packed_policy_replay_analysis.py` models what happens when small simulator
zones are packed into real ZNS-sized zones.  This script performs the same
mapping while issuing actual zonefs appends and resets.  It is meant to answer a
more concrete question:

    If QUASAR/DOGI-style logical placement is packed onto a real ZNS device,
    which logical resets actually become physical zone resets?

Cleanup resets at the end are recorded separately from semantic resets caused
by the replayed policy.  The exposure metrics are captured before cleanup.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import physical_policy_replay_suite as replay_suite
except ModuleNotFoundError:  # pragma: no cover
    from quasar import physical_policy_replay_suite as replay_suite

try:
    import physical_zonefs_replay as zonefs
except ModuleNotFoundError:  # pragma: no cover
    from quasar import physical_zonefs_replay as zonefs


SECRET_INTENTS = {"EPHEMERAL_SECRET", "KEM_ARTIFACT"}
DEFAULT_PACKINGS = ["any", "group"]


def epoch_bin_width(packing: str) -> int | None:
    prefix = "epoch-bin-"
    if not packing.startswith(prefix):
        return None
    width = int(packing[len(prefix) :])
    if width <= 0:
        raise ValueError(f"epoch bin width must be positive: {packing}")
    return width


@dataclass
class Extent:
    logical_zone_id: int
    blocks: int
    live: bool
    is_secret: bool
    account_user: bool
    is_gc: bool


@dataclass
class PhysicalZone:
    physical_zone_id: int
    path: Path
    capacity: int
    pack_key: str
    extents: list[Extent] = field(default_factory=list)
    used_blocks: int = 0
    live_blocks: int = 0
    invalid_blocks: int = 0
    pending_secret_erase_blocks: int = 0

    @property
    def free_blocks(self) -> int:
        return self.capacity - self.used_blocks

    @property
    def is_resettable(self) -> bool:
        return self.used_blocks > 0 and self.live_blocks == 0

    def append(self, extent: Extent) -> None:
        self.extents.append(extent)
        self.used_blocks += extent.blocks
        if extent.live:
            self.live_blocks += extent.blocks
        else:
            self.invalid_blocks += extent.blocks
            if extent.is_secret:
                self.pending_secret_erase_blocks += extent.blocks

    def invalidate_logical_zone(self, logical_zone_id: int) -> tuple[int, int]:
        invalidated = 0
        secret_invalidated = 0
        for extent in self.extents:
            if extent.logical_zone_id != logical_zone_id or not extent.live:
                continue
            extent.live = False
            invalidated += extent.blocks
            self.live_blocks -= extent.blocks
            self.invalid_blocks += extent.blocks
            if extent.is_secret:
                secret_invalidated += extent.blocks
                self.pending_secret_erase_blocks += extent.blocks
        return invalidated, secret_invalidated


def packing_key(operation: dict[str, Any], packing: str) -> str:
    if "pack_key_override" in operation:
        return str(operation["pack_key_override"])
    if packing == "any":
        return "any"
    if packing == "group":
        return f"group:{operation.get('group', 'unknown')}"
    if packing == "security-group":
        intent = str(operation.get("intent", "UNKNOWN"))
        security = "secret" if intent in SECRET_INTENTS else "nonsecret"
        return f"{security}:group:{operation.get('group', 'unknown')}"
    if packing == "secret-group":
        intent = str(operation.get("intent", "UNKNOWN"))
        if intent in SECRET_INTENTS:
            return f"secret:group:{operation.get('group', 'unknown')}"
        return "nonsecret:any"
    if packing == "logical-zone":
        return f"logical-zone:{operation.get('zone_id', 'unknown')}"
    width = epoch_bin_width(packing)
    if width is not None:
        intent = str(operation.get("intent", "UNKNOWN"))
        if intent in SECRET_INTENTS:
            epoch_id = int(operation.get("epoch_id", 0))
            return f"secret-epoch-bin:{epoch_id // width}:width:{width}"
        return f"nonsecret:group:{operation.get('group', 'unknown')}"
    raise ValueError(f"unknown packing mode: {packing}")


class PackedPhysicalExecutor:
    def __init__(self, zone_files: list[Path], args: argparse.Namespace, *, packing: str) -> None:
        self.zone_files = zone_files
        self.free_zone_ids = list(range(len(zone_files)))
        self.args = args
        self.packing = packing
        self.physical_zones: dict[int, PhysicalZone] = {}
        self.active_by_key: dict[str, int] = {}
        self.logical_to_physical: dict[int, set[int]] = defaultdict(set)
        self.pending_append_blocks: Counter[int] = Counter()
        self.used_zone_files_ever: set[Path] = set()
        self.failures: list[dict[str, Any]] = []
        self.sampled_rows: list[dict[str, Any]] = []

        self.logical_append_operations = 0
        self.physical_append_commands = 0
        self.logical_reset_commands = 0
        self.physical_reset_commands = 0
        self.delayed_logical_resets = 0
        self.append_blocks = 0
        self.user_blocks = 0
        self.gc_blocks = 0
        self.prefill_blocks = 0
        self.bytes_written = 0
        self.secret_logical_reset_blocks = 0
        self.secret_blocks_waiting_for_physical_reset = 0
        self.max_secret_blocks_waiting_for_physical_reset = 0
        self.residual_migration_commands = 0
        self.residual_migrated_blocks = 0
        self.residual_migration_budget_skips = 0
        self.max_live_physical_zones = 0
        self.max_active_pack_keys = 0
        self.append_latencies: list[int] = []
        self.reset_latencies: list[int] = []

    def record(self, row: dict[str, Any]) -> None:
        if len(self.sampled_rows) < self.args.max_rows_in_output:
            self.sampled_rows.append(row)

    def fail(self, row: dict[str, Any]) -> None:
        self.failures.append(row)
        self.record(row)
        if self.args.fail_fast:
            raise RuntimeError(json.dumps(row, sort_keys=True))

    def issue_append(self, zone: PhysicalZone, blocks: int) -> bool:
        remaining = blocks
        while remaining > 0:
            chunk = remaining
            if self.args.max_blocks_per_dd:
                chunk = min(chunk, self.args.max_blocks_per_dd)
            if self.args.execute:
                if self.args.append_engine == "helper":
                    result = zonefs.run_helper_append(
                        zone.path,
                        chunk,
                        self.args.append_helper,
                        chunk_blocks=self.args.helper_chunk_blocks,
                    )
                else:
                    result = zonefs.run_dd_append(zone.path, chunk)
                if not result["succeeded"]:
                    self.fail(
                        {
                            "op": "append",
                            "packing": self.packing,
                            "physical_zone_id": zone.physical_zone_id,
                            "target": str(zone.path),
                            "blocks": chunk,
                            **result,
                        }
                    )
                    return False
                self.append_latencies.append(int(result["latency_ns"]))
            self.physical_append_commands += 1
            self.bytes_written += chunk * 4096
            remaining -= chunk
        return True

    def flush_pending(self, physical_zone_id: int) -> bool:
        blocks = int(self.pending_append_blocks.pop(physical_zone_id, 0))
        if blocks <= 0:
            return True
        zone = self.physical_zones.get(physical_zone_id)
        if zone is None:
            return True
        return self.issue_append(zone, blocks)

    def flush_all_pending(self) -> bool:
        for physical_zone_id in list(self.pending_append_blocks):
            if not self.flush_pending(physical_zone_id):
                return False
        return True

    def reset_physical_zone(self, physical_zone_id: int) -> bool:
        zone = self.physical_zones.get(physical_zone_id)
        if zone is None:
            return True
        if not self.flush_pending(physical_zone_id):
            return False
        if self.args.execute:
            result = zonefs.run_truncate_reset(zone.path)
            if not result["succeeded"]:
                self.fail(
                    {
                        "op": "physical_reset",
                        "packing": self.packing,
                        "physical_zone_id": physical_zone_id,
                        "target": str(zone.path),
                        **result,
                    }
                )
                return False
            self.reset_latencies.append(int(result["latency_ns"]))
        self.physical_zones.pop(physical_zone_id, None)
        if self.active_by_key.get(zone.pack_key) == physical_zone_id:
            self.active_by_key.pop(zone.pack_key, None)
        for extent in zone.extents:
            zones = self.logical_to_physical.get(extent.logical_zone_id)
            if zones:
                zones.discard(physical_zone_id)
                if not zones:
                    self.logical_to_physical.pop(extent.logical_zone_id, None)
        self.secret_blocks_waiting_for_physical_reset -= zone.pending_secret_erase_blocks
        self.physical_reset_commands += 1
        self.free_zone_ids.append(physical_zone_id)
        return True

    def allocate_zone(self, key: str) -> PhysicalZone | None:
        resettable = [zone for zone in self.physical_zones.values() if zone.is_resettable]
        if resettable:
            victim = max(resettable, key=lambda zone: zone.used_blocks)
            if not self.reset_physical_zone(victim.physical_zone_id):
                return None
        if not self.free_zone_ids:
            self.fail(
                {
                    "op": "allocate_zone",
                    "packing": self.packing,
                    "stderr": "out of selected physical zonefs files",
                    "zone_files_available": len(self.zone_files),
                    "live_physical_zones": len(self.physical_zones),
                }
            )
            return None
        physical_zone_id = self.free_zone_ids.pop(0)
        zone = PhysicalZone(
            physical_zone_id=physical_zone_id,
            path=self.zone_files[physical_zone_id],
            capacity=self.args.physical_zone_capacity,
            pack_key=key,
        )
        self.physical_zones[physical_zone_id] = zone
        self.active_by_key[key] = physical_zone_id
        self.used_zone_files_ever.add(zone.path)
        self.max_live_physical_zones = max(self.max_live_physical_zones, len(self.physical_zones))
        self.max_active_pack_keys = max(self.max_active_pack_keys, len(self.active_by_key))
        return zone

    def active_zone_for(self, key: str, blocks: int) -> PhysicalZone | None:
        physical_zone_id = self.active_by_key.get(key)
        zone = self.physical_zones.get(physical_zone_id) if physical_zone_id is not None else None
        if zone is not None and zone.free_blocks >= blocks:
            return zone
        if zone is not None and zone.free_blocks == 0:
            self.active_by_key.pop(key, None)
        return self.allocate_zone(key)

    def append(self, operation: dict[str, Any]) -> None:
        self.logical_append_operations += 1
        logical_zone_id = int(operation["zone_id"])
        is_secret = str(operation.get("intent", "UNKNOWN")) in SECRET_INTENTS
        is_gc = bool(operation.get("is_gc"))
        account_user = bool(operation.get("account_user", True))
        key = packing_key(operation, self.packing)
        remaining = int(operation.get("blocks", 1))

        while remaining > 0:
            chunk = min(remaining, self.args.physical_zone_capacity)
            zone = self.active_zone_for(key, chunk)
            if zone is None:
                return
            if zone.free_blocks < chunk:
                chunk = zone.free_blocks
            extent = Extent(
                logical_zone_id=logical_zone_id,
                blocks=chunk,
                live=True,
                is_secret=is_secret,
                account_user=account_user,
                is_gc=is_gc,
            )
            zone.append(extent)
            self.logical_to_physical[logical_zone_id].add(zone.physical_zone_id)
            self.append_blocks += chunk
            if is_gc:
                self.gc_blocks += chunk
            elif account_user:
                self.user_blocks += chunk
            else:
                self.prefill_blocks += chunk
            if self.args.batch_appends:
                self.pending_append_blocks[zone.physical_zone_id] += chunk
            else:
                if not self.issue_append(zone, chunk):
                    return
            remaining -= chunk

    def migrate_residual_live_extents(self, physical_zone_id: int) -> bool:
        threshold = int(getattr(self.args, "physical_residual_threshold", 0) or 0)
        if threshold <= 0:
            return False
        zone = self.physical_zones.get(physical_zone_id)
        if zone is None:
            return False
        if zone.pending_secret_erase_blocks <= 0 or zone.live_blocks <= 0 or zone.live_blocks > threshold:
            return False

        live_extents = [extent for extent in zone.extents if extent.live]
        if not live_extents:
            return False

        copy_budget = int(getattr(self.args, "physical_residual_copy_budget", 0) or 0)
        if copy_budget > 0 and self.residual_migrated_blocks + zone.live_blocks > copy_budget:
            self.residual_migration_budget_skips += 1
            return False

        if self.active_by_key.get(zone.pack_key) == physical_zone_id:
            self.active_by_key.pop(zone.pack_key, None)

        migrated_blocks = 0
        for extent in live_extents:
            remaining = extent.blocks
            while remaining > 0:
                chunk = min(remaining, self.args.physical_zone_capacity)
                target = self.active_zone_for(zone.pack_key, chunk)
                if target is None:
                    return False
                if target.physical_zone_id == physical_zone_id:
                    self.fail(
                        {
                            "op": "residual_migration",
                            "packing": self.packing,
                            "stderr": "residual migration selected the source zone",
                            "physical_zone_id": physical_zone_id,
                        }
                    )
                    return False
                if target.free_blocks < chunk:
                    chunk = target.free_blocks
                new_extent = Extent(
                    logical_zone_id=extent.logical_zone_id,
                    blocks=chunk,
                    live=True,
                    is_secret=extent.is_secret,
                    account_user=False,
                    is_gc=True,
                )
                target.append(new_extent)
                self.logical_to_physical[extent.logical_zone_id].add(target.physical_zone_id)
                self.append_blocks += chunk
                self.gc_blocks += chunk
                if self.args.batch_appends:
                    self.pending_append_blocks[target.physical_zone_id] += chunk
                else:
                    if not self.issue_append(target, chunk):
                        return False
                remaining -= chunk
                migrated_blocks += chunk
            extent.live = False

        zone.invalid_blocks += zone.live_blocks
        zone.live_blocks = 0
        self.residual_migration_commands += 1
        self.residual_migrated_blocks += migrated_blocks
        return self.reset_physical_zone(physical_zone_id)

    def reset_logical_zone(self, operation: dict[str, Any]) -> None:
        logical_zone_id = int(operation["zone_id"])
        self.logical_reset_commands += 1
        touched = set(self.logical_to_physical.get(logical_zone_id, set()))
        invalidated = 0
        secret_invalidated = 0
        for physical_zone_id in touched:
            zone = self.physical_zones.get(physical_zone_id)
            if zone is None:
                continue
            inv, secret = zone.invalidate_logical_zone(logical_zone_id)
            invalidated += inv
            secret_invalidated += secret
        self.secret_logical_reset_blocks += secret_invalidated
        self.secret_blocks_waiting_for_physical_reset += secret_invalidated
        self.max_secret_blocks_waiting_for_physical_reset = max(
            self.max_secret_blocks_waiting_for_physical_reset,
            self.secret_blocks_waiting_for_physical_reset,
        )
        physical_resets = 0
        for physical_zone_id in list(touched):
            zone = self.physical_zones.get(physical_zone_id)
            if zone is not None and zone.is_resettable:
                if self.reset_physical_zone(physical_zone_id):
                    physical_resets += 1
            elif zone is not None and self.migrate_residual_live_extents(physical_zone_id):
                physical_resets += 1
        if invalidated and physical_resets == 0:
            self.delayed_logical_resets += 1

    def final_metrics(self) -> dict[str, Any]:
        live_physical_zones = len(self.physical_zones)
        used_blocks = sum(zone.used_blocks for zone in self.physical_zones.values())
        live_blocks = sum(zone.live_blocks for zone in self.physical_zones.values())
        invalid_blocks = sum(zone.invalid_blocks for zone in self.physical_zones.values())
        return {
            "packing": self.packing,
            "append_blocks": self.append_blocks,
            "user_blocks": self.user_blocks,
            "gc_blocks": self.gc_blocks,
            "prefill_blocks": self.prefill_blocks,
            "logical_append_operations": self.logical_append_operations,
            "logical_reset_commands": self.logical_reset_commands,
            "physical_reset_commands": self.physical_reset_commands,
            "delayed_logical_resets": self.delayed_logical_resets,
            "secret_logical_reset_blocks": self.secret_logical_reset_blocks,
            "secret_blocks_waiting_for_physical_reset": self.secret_blocks_waiting_for_physical_reset,
            "max_secret_blocks_waiting_for_physical_reset": self.max_secret_blocks_waiting_for_physical_reset,
            "residual_migration_commands": self.residual_migration_commands,
            "residual_migrated_blocks": self.residual_migrated_blocks,
            "residual_migration_budget_skips": self.residual_migration_budget_skips,
            "live_physical_zones": live_physical_zones,
            "max_live_physical_zones": self.max_live_physical_zones,
            "max_active_pack_keys": self.max_active_pack_keys,
            "used_blocks_in_live_physical_zones": used_blocks,
            "live_blocks_in_live_physical_zones": live_blocks,
            "invalid_blocks_in_live_physical_zones": invalid_blocks,
            "space_utilization": (
                used_blocks / (live_physical_zones * self.args.physical_zone_capacity)
                if live_physical_zones
                else 0.0
            ),
        }

    def cleanup(self) -> int:
        cleanup_resets = 0
        if not self.args.reset_at_end:
            return cleanup_resets
        for physical_zone_id in list(self.physical_zones):
            zone = self.physical_zones.get(physical_zone_id)
            if zone is None:
                continue
            if not self.flush_pending(physical_zone_id):
                break
            if self.args.execute:
                result = zonefs.run_truncate_reset(zone.path)
                cleanup_resets += 1
                self.reset_latencies.append(int(result["latency_ns"]))
                if not result["succeeded"]:
                    self.fail({"op": "cleanup_reset", "physical_zone_id": physical_zone_id, **result})
                    break
            else:
                cleanup_resets += 1
        self.physical_zones.clear()
        self.active_by_key.clear()
        self.logical_to_physical.clear()
        self.pending_append_blocks.clear()
        return cleanup_resets

    def run(self, operations: list[dict[str, Any]]) -> dict[str, Any]:
        started = time.perf_counter_ns()
        executed = 0
        for operation in operations:
            if self.args.max_logical_operations and executed >= self.args.max_logical_operations:
                break
            executed += 1
            if operation["op"] == "append":
                self.append(operation)
            elif operation["op"] == "reset_zone":
                self.reset_logical_zone(operation)
            else:
                raise ValueError(operation["op"])
            if self.failures:
                break
        if not self.flush_all_pending():
            pass
        metrics_before_cleanup = self.final_metrics()
        cleanup_resets = self.cleanup()
        wall_time_ns = time.perf_counter_ns() - started
        wall_s = wall_time_ns / 1_000_000_000
        return {
            "execute": self.args.execute,
            "failed": bool(self.failures),
            "failures": self.failures[:8],
            "truncated": bool(self.args.max_logical_operations and executed < len(operations)),
            "operations_total": len(operations),
            "operations_executed": executed,
            "physical_append_commands": self.physical_append_commands,
            "physical_bytes_written": self.bytes_written,
            "zone_files_available": len(self.zone_files),
            "zone_files_used": len(self.used_zone_files_ever),
            "cleanup_reset_zones": cleanup_resets,
            "wall_time_ns": wall_time_ns,
            "wall_time_s": wall_s,
            "throughput_mib_s": (self.bytes_written / (1024 * 1024) / wall_s) if wall_s and self.args.execute else 0.0,
            "append_latency": zonefs.latency_summary(self.append_latencies),
            "reset_latency": zonefs.latency_summary(self.reset_latencies),
            "rows": self.sampled_rows,
            **metrics_before_cleanup,
        }


def reset_zone_files(zone_files: list[Path], *, execute: bool, fail_fast: bool) -> tuple[int, list[int], list[dict[str, Any]]]:
    latencies: list[int] = []
    failures: list[dict[str, Any]] = []
    if not execute:
        return (0, latencies, failures)
    for path in zone_files:
        result = zonefs.run_truncate_reset(path)
        latencies.append(int(result["latency_ns"]))
        if not result["succeeded"]:
            failures.append(result)
            if fail_fast:
                raise RuntimeError(f"initial zone reset failed: {json.dumps(result, sort_keys=True)}")
            break
    return (len(zone_files), latencies, failures)


def execute_packed_operations(operations: list[dict[str, Any]], args: argparse.Namespace, *, packing: str) -> dict[str, Any]:
    zone_files = zonefs.select_zone_files(
        args.mount,
        start_index=args.start_zone_index,
        max_zone_files=args.max_zone_files,
        require_empty=False,
    )
    initial_reset_zones, initial_reset_latencies, initial_failures = reset_zone_files(
        zone_files,
        execute=args.execute and args.reset_selected_zones_at_start,
        fail_fast=args.fail_fast,
    )
    executor = PackedPhysicalExecutor(zone_files, args, packing=packing)
    executor.reset_latencies.extend(initial_reset_latencies)
    for failure in initial_failures:
        executor.fail({"op": "initial_reset", **failure})
    physical = executor.run(operations)
    physical["initial_reset_zones"] = initial_reset_zones
    return physical


def load_trace_paths(args: argparse.Namespace) -> list[Path]:
    return replay_suite.load_trace_paths(args)


def run_suite(args: argparse.Namespace) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    started = time.perf_counter_ns()
    for trace in load_trace_paths(args):
        for policy in args.policies:
            try:
                stats, operations = replay_suite.simulate_policy(trace, policy, args)
            except Exception as exc:
                stats = {"policy": policy, "trace": str(trace), "failed": True, "error": str(exc)}
                operations = []
            for packing in args.packings:
                if operations:
                    physical = execute_packed_operations(operations, args, packing=packing)
                else:
                    physical = {
                        "execute": args.execute,
                        "failed": True,
                        "failures": [{"op": "simulate", "stderr": stats.get("error", "simulation failed")}],
                        "packing": packing,
                        "operations_total": 0,
                        "operations_executed": 0,
                        "physical_append_commands": 0,
                        "physical_bytes_written": 0,
                        "logical_reset_commands": 0,
                        "physical_reset_commands": 0,
                        "delayed_logical_resets": 0,
                        "secret_logical_reset_blocks": 0,
                        "secret_blocks_waiting_for_physical_reset": 0,
                        "max_secret_blocks_waiting_for_physical_reset": 0,
                        "residual_migration_commands": 0,
                        "residual_migrated_blocks": 0,
                        "residual_migration_budget_skips": 0,
                        "max_live_physical_zones": 0,
                        "max_active_pack_keys": 0,
                        "space_utilization": 0.0,
                        "append_latency": zonefs.latency_summary([]),
                        "reset_latency": zonefs.latency_summary([]),
                        "rows": [],
                    }
                rows.append(
                    {
                        "workload": replay_suite.workload_name(trace),
                        "trace": str(trace),
                        "policy": policy,
                        "packing": packing,
                        "sim": stats,
                        "physical": physical,
                        "operation_count": len(operations),
                        "append_operation_count": sum(1 for op in operations if op["op"] == "append"),
                        "reset_operation_count": sum(1 for op in operations if op["op"] == "reset_zone"),
                    }
                )
                if physical["failed"] and args.stop_on_failure:
                    break
            if rows and rows[-1]["physical"]["failed"] and args.stop_on_failure:
                break
        if rows and rows[-1]["physical"]["failed"] and args.stop_on_failure:
            break
    wall_time_ns = time.perf_counter_ns() - started
    return {
        "suite": "packed-physical-zonefs-replay",
        "execute": args.execute,
        "mount": str(args.mount),
        "policies": args.policies,
        "packings": args.packings,
        "traces": [str(path) for path in load_trace_paths(args)],
        "logical_zones": args.zones,
        "logical_zone_capacity": args.zone_capacity,
        "physical_zone_capacity": args.physical_zone_capacity,
        "max_zone_files": args.max_zone_files,
        "batch_appends": args.batch_appends,
        "physical_residual_threshold": args.physical_residual_threshold,
        "physical_residual_copy_budget": args.physical_residual_copy_budget,
        "append_engine": args.append_engine,
        "append_helper": str(args.append_helper),
        "helper_chunk_blocks": args.helper_chunk_blocks,
        "reset_at_end": args.reset_at_end,
        "rows": rows,
        "summary": summarize(rows, wall_time_ns),
    }


def summarize(rows: list[dict[str, Any]], wall_time_ns: int) -> dict[str, Any]:
    by_policy_packing: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = f"{row['policy']}::{row['packing']}"
        item = by_policy_packing.setdefault(
            key,
            {
                "policy": row["policy"],
                "packing": row["packing"],
                "rows": 0,
                "failed_rows": 0,
                "sim_user_blocks": 0,
                "sim_gc_blocks": 0,
                "sim_stale_secret_blocks": 0,
                "append_blocks": 0,
                "user_blocks": 0,
                "gc_blocks": 0,
                "prefill_blocks": 0,
                "physical_bytes_written": 0,
                "physical_append_commands": 0,
                "logical_reset_commands": 0,
                "physical_reset_commands": 0,
                "delayed_logical_resets": 0,
                "secret_logical_reset_blocks": 0,
                "secret_blocks_waiting_for_physical_reset": 0,
                "max_secret_blocks_waiting_for_physical_reset": 0,
                "residual_migration_commands": 0,
                "residual_migrated_blocks": 0,
                "residual_migration_budget_skips": 0,
                "max_live_physical_zones": 0,
                "max_active_pack_keys": 0,
                "space_utilization_sum": 0.0,
            },
        )
        sim = row["sim"]
        physical = row["physical"]
        item["rows"] += 1
        item["failed_rows"] += int(bool(physical.get("failed")))
        item["sim_user_blocks"] += int(sim.get("user_write_blocks", 0))
        item["sim_gc_blocks"] += int(sim.get("gc_write_blocks", 0))
        item["sim_stale_secret_blocks"] += int(sim.get("stale_secret_blocks_remaining", 0))
        for field_name in (
            "append_blocks",
            "user_blocks",
            "gc_blocks",
            "prefill_blocks",
            "physical_bytes_written",
            "physical_append_commands",
            "logical_reset_commands",
            "physical_reset_commands",
            "delayed_logical_resets",
            "secret_logical_reset_blocks",
            "secret_blocks_waiting_for_physical_reset",
            "residual_migration_commands",
            "residual_migrated_blocks",
            "residual_migration_budget_skips",
        ):
            item[field_name] += int(physical.get(field_name, 0))
        item["max_secret_blocks_waiting_for_physical_reset"] = max(
            item["max_secret_blocks_waiting_for_physical_reset"],
            int(physical.get("max_secret_blocks_waiting_for_physical_reset", 0)),
        )
        item["max_live_physical_zones"] = max(
            item["max_live_physical_zones"],
            int(physical.get("max_live_physical_zones", 0)),
        )
        item["max_active_pack_keys"] = max(
            item["max_active_pack_keys"],
            int(physical.get("max_active_pack_keys", 0)),
        )
        item["space_utilization_sum"] += float(physical.get("space_utilization", 0.0))
    for item in by_policy_packing.values():
        rows_count = max(1, int(item["rows"]))
        user = max(1, int(item["sim_user_blocks"]))
        item["sim_waf"] = (int(item["sim_user_blocks"]) + int(item["sim_gc_blocks"])) / user
        physical_user = max(1, int(item["user_blocks"]))
        item["physical_waf"] = (int(item["user_blocks"]) + int(item["gc_blocks"])) / physical_user
        item["avg_space_utilization"] = item.pop("space_utilization_sum") / rows_count
        logical_resets = max(1, int(item["logical_reset_commands"]))
        item["delayed_reset_ratio"] = int(item["delayed_logical_resets"]) / logical_resets
    return {
        "row_count": len(rows),
        "failed_rows": sum(1 for row in rows if row["physical"].get("failed")),
        "wall_time_s": wall_time_ns / 1_000_000_000,
        "by_policy_packing": by_policy_packing,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Packed Physical Zonefs Replay Suite",
        "",
        f"- Executed: `{report['execute']}`",
        f"- Mount: `{report['mount']}`",
        f"- Rows: `{report['summary']['row_count']}`",
        f"- Failed rows: `{report['summary']['failed_rows']}`",
        f"- Logical zone capacity: `{report['logical_zone_capacity']}` blocks",
        f"- Physical zone capacity: `{report['physical_zone_capacity']}` blocks",
        f"- Max selected zone files: `{report['max_zone_files']}`",
        f"- Batched physical appends: `{report['batch_appends']}`",
        f"- Append engine: `{report['append_engine']}`",
        f"- Append helper: `{report['append_helper']}`",
        f"- Helper chunk blocks: `{report['helper_chunk_blocks']}`",
        f"- Physical residual threshold: `{report['physical_residual_threshold']}` blocks",
        f"- Physical residual copy budget: `{report['physical_residual_copy_budget']}` blocks",
        f"- Wall time: `{report['summary']['wall_time_s']:.3f}` s",
        "",
        "| Policy | Packing | Rows | Sim WAF | Physical WAF | Physical MiB | Avg Util | Max Phys Zones | Max Pack Keys | Logical Resets | Semantic Physical Resets | Residual Migrations | Residual Blocks | Budget Skips | Delayed Reset % | Secret Reset Blocks | Secret Waiting End | Max Secret Waiting | Sim Stale Secrets | Failed Rows |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, item in sorted(report["summary"]["by_policy_packing"].items()):
        lines.append(
            "| `{policy}` | `{packing}` | {rows} | {sim_waf:.4f} | {physical_waf:.4f} | {mib:.1f} | {avg_util:.3f} | {max_zones} | {max_keys} | {logical_resets} | {physical_resets} | {residual_migrations} | {residual_blocks} | {budget_skips} | {delayed:.2%} | {secret_reset} | {secret_waiting} | {max_secret_waiting} | {stale} | {failed} |".format(
                policy=item["policy"],
                packing=item["packing"],
                rows=item["rows"],
                sim_waf=item["sim_waf"],
                physical_waf=item["physical_waf"],
                mib=int(item["physical_bytes_written"]) / (1024 * 1024),
                avg_util=item["avg_space_utilization"],
                max_zones=item["max_live_physical_zones"],
                max_keys=item["max_active_pack_keys"],
                logical_resets=item["logical_reset_commands"],
                physical_resets=item["physical_reset_commands"],
                residual_migrations=item["residual_migration_commands"],
                residual_blocks=item["residual_migrated_blocks"],
                budget_skips=item["residual_migration_budget_skips"],
                delayed=item["delayed_reset_ratio"],
                secret_reset=item["secret_logical_reset_blocks"],
                secret_waiting=item["secret_blocks_waiting_for_physical_reset"],
                max_secret_waiting=item["max_secret_blocks_waiting_for_physical_reset"],
                stale=item["sim_stale_secret_blocks"],
                failed=item["failed_rows"],
            )
        )
    lines.extend(
        [
            "",
            "Interpretation:",
            "",
            "```text",
            "This suite physically appends packed logical-zone traffic to zonefs files.",
            "Semantic physical resets count only reset commands made possible by replayed logical resets.",
            "Cleanup resets are excluded from exposure metrics and only return the device to a clean state.",
            "Any-packing tests the high-utilization but unsafe mixing case.",
            "Group-packing tests exact death-cohort separation.",
            "Secret-group packing keeps secret cohorts exact while packing nonsecret extents together.",
            "Epoch-bin packing intentionally trades reset immediacy for fewer physical pack keys.",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], out: Path, markdown_out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    markdown_out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_out.write_text(markdown(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", action="append", type=Path, default=[])
    parser.add_argument("--trace-list", type=Path)
    parser.add_argument("--mount", type=Path, default=Path("/mnt/zn540"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--policies", type=replay_suite.parse_csv, default=["dogi-history", "quasar", "quasar-dogi-hybrid"])
    parser.add_argument("--packings", type=replay_suite.parse_csv, default=DEFAULT_PACKINGS)
    parser.add_argument("--zones", type=int, default=512)
    parser.add_argument("--zone-capacity", type=int, default=512)
    parser.add_argument("--min-free-zones", type=int, default=4)
    parser.add_argument("--physical-zone-capacity", type=int, default=275_712)
    parser.add_argument("--physical-residual-threshold", type=int, default=0)
    parser.add_argument("--physical-residual-copy-budget", type=int, default=0)
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
    parser.add_argument("--start-zone-index", type=int, default=200)
    parser.add_argument("--max-zone-files", type=int, default=64)
    parser.add_argument("--max-blocks-per-dd", type=int, default=8192)
    parser.add_argument("--append-engine", choices=["dd", "helper"], default="dd")
    parser.add_argument("--append-helper", type=Path, default=Path("artifacts/results/bin/zonefs_direct_append"))
    parser.add_argument("--helper-chunk-blocks", type=int, default=1024)
    parser.add_argument("--max-logical-operations", type=int, default=0)
    parser.add_argument("--max-rows-in-output", type=int, default=64)
    parser.add_argument("--coalesce", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--batch-appends", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--reset-at-end", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--reset-selected-zones-at-start", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--stop-on-failure", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/packed-physical-zonefs-replay.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/packed-physical-zonefs-replay.md"))
    args = parser.parse_args()

    if not load_trace_paths(args):
        raise SystemExit("at least one --trace or --trace-list entry is required")
    report = run_suite(args)
    write_outputs(report, args.out, args.markdown_out)
    print(
        json.dumps(
            {
                "execute": report["execute"],
                "rows": report["summary"]["row_count"],
                "failed_rows": report["summary"]["failed_rows"],
                "wall_time_s": report["summary"]["wall_time_s"],
            },
            sort_keys=True,
        )
    )
    return 1 if report["summary"]["failed_rows"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
