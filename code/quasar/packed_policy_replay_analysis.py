#!/usr/bin/env python3
"""Analyze packed logical-zone replay on physical ZNS-sized zones.

The direct physical policy replay has two safe modes:

* use real physical-zone capacity, so each simulator zone maps naturally to one
  zonefs file; or
* use small simulator zones only as a dry run.

This analyzer fills the gap between them.  It keeps the simulator's small
logical zones, but models a host packing layer that appends many logical-zone
extents into a larger physical ZNS zone.  A physical zone can be reset only when
all packed extents in it are invalid.  This exposes the real trade-off:
packing improves space utilization, but mixing unrelated death cohorts delays
physical reset/erase of expired secret extents.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import physical_policy_replay_suite as replay_suite
except ModuleNotFoundError:  # pragma: no cover
    from quasar import physical_policy_replay_suite as replay_suite


SECRET_INTENTS = {"EPHEMERAL_SECRET", "KEM_ARTIFACT"}


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


class PackedMapper:
    def __init__(self, *, physical_zone_count: int, physical_zone_capacity: int, packing: str) -> None:
        self.physical_zone_count = physical_zone_count
        self.physical_zone_capacity = physical_zone_capacity
        self.packing = packing
        self.next_physical_zone_id = 0
        self.physical_zones: dict[int, PhysicalZone] = {}
        self.active_by_key: dict[str, int] = {}
        self.logical_to_physical: dict[int, set[int]] = defaultdict(set)
        self.failed = False
        self.failures: list[dict[str, Any]] = []

        self.append_blocks = 0
        self.user_blocks = 0
        self.gc_blocks = 0
        self.prefill_blocks = 0
        self.gc_copy_blocks = 0
        self.logical_reset_commands = 0
        self.physical_reset_commands = 0
        self.delayed_logical_resets = 0
        self.secret_blocks_waiting_for_physical_reset = 0
        self.max_secret_blocks_waiting_for_physical_reset = 0
        self.secret_logical_reset_blocks = 0
        self.max_live_physical_zones = 0
        self.max_active_pack_keys = 0

    def pack_key(self, operation: dict[str, Any]) -> str:
        if self.packing == "any":
            return "any"
        if self.packing == "group":
            return f"group:{operation.get('group', 'unknown')}"
        if self.packing == "security-group":
            intent = str(operation.get("intent", "UNKNOWN"))
            security = "secret" if intent in SECRET_INTENTS else "nonsecret"
            return f"{security}:group:{operation.get('group', 'unknown')}"
        if self.packing == "secret-group":
            intent = str(operation.get("intent", "UNKNOWN"))
            if intent in SECRET_INTENTS:
                return f"secret:group:{operation.get('group', 'unknown')}"
            return "nonsecret:any"
        if self.packing == "logical-zone":
            return f"logical-zone:{operation.get('zone_id', 'unknown')}"
        width = epoch_bin_width(self.packing)
        if width is not None:
            intent = str(operation.get("intent", "UNKNOWN"))
            if intent in SECRET_INTENTS:
                epoch_id = int(operation.get("epoch_id", 0))
                return f"secret-epoch-bin:{epoch_id // width}:width:{width}"
            return f"nonsecret:group:{operation.get('group', 'unknown')}"
        raise ValueError(f"unknown packing mode: {self.packing}")

    def allocate_zone(self, key: str) -> PhysicalZone | None:
        resettable = [zone for zone in self.physical_zones.values() if zone.is_resettable]
        if resettable:
            victim = max(resettable, key=lambda zone: zone.used_blocks)
            self.reset_physical_zone(victim.physical_zone_id)
        if len(self.physical_zones) >= self.physical_zone_count:
            self.failures.append(
                {
                    "op": "allocate_zone",
                    "stderr": "out of physical zones in packed model",
                    "physical_zone_count": self.physical_zone_count,
                    "live_physical_zones": len(self.physical_zones),
                }
            )
            self.failed = True
            return None
        zone_id = self.next_physical_zone_id
        self.next_physical_zone_id += 1
        zone = PhysicalZone(zone_id, self.physical_zone_capacity, key)
        self.physical_zones[zone_id] = zone
        self.active_by_key[key] = zone_id
        self.max_live_physical_zones = max(self.max_live_physical_zones, len(self.physical_zones))
        self.max_active_pack_keys = max(self.max_active_pack_keys, len(self.active_by_key))
        return zone

    def active_zone_for(self, key: str, blocks: int) -> PhysicalZone | None:
        zone_id = self.active_by_key.get(key)
        zone = self.physical_zones.get(zone_id) if zone_id is not None else None
        if zone is not None and zone.free_blocks >= blocks:
            return zone
        if zone is not None and zone.free_blocks == 0:
            self.active_by_key.pop(key, None)
        return self.allocate_zone(key)

    def append(self, operation: dict[str, Any]) -> None:
        remaining = int(operation.get("blocks", 1))
        logical_zone_id = int(operation["zone_id"])
        is_secret = str(operation.get("intent", "UNKNOWN")) in SECRET_INTENTS
        is_gc = bool(operation.get("is_gc"))
        account_user = bool(operation.get("account_user", True))
        key = self.pack_key(operation)
        while remaining > 0 and not self.failed:
            chunk = min(remaining, self.physical_zone_capacity)
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
            remaining -= chunk

    def reset_physical_zone(self, physical_zone_id: int) -> None:
        zone = self.physical_zones.pop(physical_zone_id, None)
        if zone is None:
            return
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

    def try_reset_newly_invalid(self, touched_physical_zones: set[int]) -> int:
        resets = 0
        for physical_zone_id in list(touched_physical_zones):
            zone = self.physical_zones.get(physical_zone_id)
            if zone is not None and zone.is_resettable:
                self.reset_physical_zone(physical_zone_id)
                resets += 1
        return resets

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
        physical_resets = self.try_reset_newly_invalid(touched)
        if invalidated and physical_resets == 0:
            self.delayed_logical_resets += 1

    def run(self, operations: list[dict[str, Any]]) -> dict[str, Any]:
        for operation in operations:
            if operation["op"] == "append":
                self.append(operation)
            elif operation["op"] == "reset_zone":
                self.reset_logical_zone(operation)
            else:
                raise ValueError(operation["op"])
            if self.failed:
                break
        live_physical_zones = len(self.physical_zones)
        used_blocks = sum(zone.used_blocks for zone in self.physical_zones.values())
        live_blocks = sum(zone.live_blocks for zone in self.physical_zones.values())
        invalid_blocks = sum(zone.invalid_blocks for zone in self.physical_zones.values())
        return {
            "failed": self.failed,
            "failures": self.failures[:8],
            "packing": self.packing,
            "physical_zone_count": self.physical_zone_count,
            "physical_zone_capacity": self.physical_zone_capacity,
            "append_blocks": self.append_blocks,
            "user_blocks": self.user_blocks,
            "gc_blocks": self.gc_blocks,
            "prefill_blocks": self.prefill_blocks,
            "gc_copy_blocks": self.gc_copy_blocks,
            "logical_reset_commands": self.logical_reset_commands,
            "physical_reset_commands": self.physical_reset_commands,
            "delayed_logical_resets": self.delayed_logical_resets,
            "secret_logical_reset_blocks": self.secret_logical_reset_blocks,
            "secret_blocks_waiting_for_physical_reset": self.secret_blocks_waiting_for_physical_reset,
            "max_secret_blocks_waiting_for_physical_reset": self.max_secret_blocks_waiting_for_physical_reset,
            "live_physical_zones": live_physical_zones,
            "max_live_physical_zones": self.max_live_physical_zones,
            "max_active_pack_keys": self.max_active_pack_keys,
            "used_blocks_in_live_physical_zones": used_blocks,
            "live_blocks_in_live_physical_zones": live_blocks,
            "invalid_blocks_in_live_physical_zones": invalid_blocks,
            "space_utilization": (
                used_blocks / (live_physical_zones * self.physical_zone_capacity)
                if live_physical_zones
                else 0.0
            ),
        }


def analyze_operations(
    operations: list[dict[str, Any]],
    *,
    physical_zone_count: int,
    physical_zone_capacity: int,
    packing: str,
) -> dict[str, Any]:
    mapper = PackedMapper(
        physical_zone_count=physical_zone_count,
        physical_zone_capacity=physical_zone_capacity,
        packing=packing,
    )
    return mapper.run(operations)


def run_suite(args: argparse.Namespace) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for trace in replay_suite.load_trace_paths(args):
        for policy in args.policies:
            stats, operations = replay_suite.simulate_policy(trace, policy, args)
            for packing in args.packings:
                packed = analyze_operations(
                    operations,
                    physical_zone_count=args.physical_zones,
                    physical_zone_capacity=args.physical_zone_capacity,
                    packing=packing,
                )
                rows.append(
                    {
                        "workload": replay_suite.workload_name(trace),
                        "trace": str(trace),
                        "policy": policy,
                        "packing": packing,
                        "sim": stats,
                        "operation_count": len(operations),
                        "append_operation_count": sum(1 for op in operations if op["op"] == "append"),
                        "reset_operation_count": sum(1 for op in operations if op["op"] == "reset_zone"),
                        "packed": packed,
                    }
                )
    return {
        "suite": "packed-policy-replay-analysis",
        "physical_zones": args.physical_zones,
        "physical_zone_capacity": args.physical_zone_capacity,
        "logical_zone_capacity": args.zone_capacity,
        "policies": args.policies,
        "packings": args.packings,
        "traces": [str(path) for path in replay_suite.load_trace_paths(args)],
        "rows": rows,
        "summary": summarize(rows),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
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
                "logical_reset_commands": 0,
                "physical_reset_commands": 0,
                "delayed_logical_resets": 0,
                "secret_logical_reset_blocks": 0,
                "secret_blocks_waiting_for_physical_reset": 0,
                "max_secret_blocks_waiting_for_physical_reset": 0,
                "max_live_physical_zones": 0,
                "max_active_pack_keys": 0,
                "space_utilization_sum": 0.0,
            },
        )
        packed = row["packed"]
        sim = row["sim"]
        item["rows"] += 1
        item["failed_rows"] += int(bool(packed["failed"]))
        item["sim_user_blocks"] += int(sim.get("user_write_blocks", 0))
        item["sim_gc_blocks"] += int(sim.get("gc_write_blocks", 0))
        item["sim_stale_secret_blocks"] += int(sim.get("stale_secret_blocks_remaining", 0))
        for field_name in (
            "append_blocks",
            "user_blocks",
            "gc_blocks",
            "prefill_blocks",
            "logical_reset_commands",
            "physical_reset_commands",
            "delayed_logical_resets",
            "secret_logical_reset_blocks",
            "secret_blocks_waiting_for_physical_reset",
        ):
            item[field_name] += int(packed.get(field_name, 0))
        item["max_secret_blocks_waiting_for_physical_reset"] = max(
            item["max_secret_blocks_waiting_for_physical_reset"],
            int(packed.get("max_secret_blocks_waiting_for_physical_reset", 0)),
        )
        item["max_live_physical_zones"] = max(
            item["max_live_physical_zones"],
            int(packed.get("max_live_physical_zones", 0)),
        )
        item["max_active_pack_keys"] = max(
            item["max_active_pack_keys"],
            int(packed.get("max_active_pack_keys", 0)),
        )
        item["space_utilization_sum"] += float(packed.get("space_utilization", 0.0))
    for item in by_policy_packing.values():
        rows_count = max(1, int(item["rows"]))
        user = max(1, int(item["sim_user_blocks"]))
        item["sim_waf"] = (int(item["sim_user_blocks"]) + int(item["sim_gc_blocks"])) / user
        item["avg_space_utilization"] = item.pop("space_utilization_sum") / rows_count
        logical_resets = max(1, int(item["logical_reset_commands"]))
        item["delayed_reset_ratio"] = int(item["delayed_logical_resets"]) / logical_resets
    return {
        "row_count": len(rows),
        "failed_rows": sum(1 for row in rows if row["packed"]["failed"]),
        "by_policy_packing": by_policy_packing,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Packed Policy Replay Analysis",
        "",
        f"- Physical zones: `{report['physical_zones']}`",
        f"- Physical zone capacity: `{report['physical_zone_capacity']}` blocks",
        f"- Logical zone capacity: `{report['logical_zone_capacity']}` blocks",
        f"- Rows: `{report['summary']['row_count']}`",
        f"- Failed rows: `{report['summary']['failed_rows']}`",
        "",
        "| Policy | Packing | Rows | Sim WAF | Avg Util | Max Phys Zones | Max Pack Keys | Logical Resets | Physical Resets | Delayed Reset % | Secret Reset Blocks | Secret Waiting End | Max Secret Waiting | Sim Stale Secrets |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, item in sorted(report["summary"]["by_policy_packing"].items()):
        lines.append(
            "| `{policy}` | `{packing}` | {rows} | {sim_waf:.4f} | {avg_util:.3f} | {max_zones} | {max_keys} | {logical_resets} | {physical_resets} | {delayed:.2%} | {secret_reset} | {secret_waiting} | {max_secret_waiting} | {stale} |".format(
                policy=item["policy"],
                packing=item["packing"],
                rows=item["rows"],
                sim_waf=item["sim_waf"],
                avg_util=item["avg_space_utilization"],
                max_zones=item["max_live_physical_zones"],
                max_keys=item["max_active_pack_keys"],
                logical_resets=item["logical_reset_commands"],
                physical_resets=item["physical_reset_commands"],
                delayed=item["delayed_reset_ratio"],
                secret_reset=item["secret_logical_reset_blocks"],
                secret_waiting=item["secret_blocks_waiting_for_physical_reset"],
                max_secret_waiting=item["max_secret_blocks_waiting_for_physical_reset"],
                stale=item["sim_stale_secret_blocks"],
            )
        )
    lines.extend(
        [
            "",
            "Interpretation:",
            "",
            "```text",
            "Packing small logical zones into physical ZNS zones is necessary for realistic physical replay.",
            "The cost is that a logical reset does not imply a physical reset when unrelated live extents share the physical zone.",
            "Group/security-group packing is the deployment analogue of QUASAR's death-cohort separation.",
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
    parser.add_argument("--policies", type=replay_suite.parse_csv, default=replay_suite.DEFAULT_POLICIES)
    parser.add_argument("--packings", type=replay_suite.parse_csv, default=["any", "group", "security-group", "logical-zone"])
    parser.add_argument("--zones", type=int, default=1024)
    parser.add_argument("--zone-capacity", type=int, default=512)
    parser.add_argument("--min-free-zones", type=int, default=4)
    parser.add_argument("--physical-zones", type=int, default=905)
    parser.add_argument("--physical-zone-capacity", type=int, default=275712)
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
    parser.add_argument("--coalesce", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/packed-policy-replay-analysis.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/packed-policy-replay-analysis.md"))
    args = parser.parse_args()

    if not replay_suite.load_trace_paths(args):
        raise SystemExit("at least one --trace or --trace-list entry is required")
    report = run_suite(args)
    write_outputs(report, args.out, args.markdown_out)
    print(
        json.dumps(
            {
                "rows": report["summary"]["row_count"],
                "failed_rows": report["summary"]["failed_rows"],
                "physical_zones": report["physical_zones"],
                "physical_zone_capacity": report["physical_zone_capacity"],
            },
            sort_keys=True,
        )
    )
    return 1 if report["summary"]["failed_rows"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
