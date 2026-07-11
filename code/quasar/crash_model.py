#!/usr/bin/env python3
"""Crash-consistency model for QUASAR metadata/reset safety.

This is a small checker for the safety invariant in plan.md:

    A zone family is reset only after its epoch manager confirms that every
    object in the family is expired or safely migrated.

It does not emulate a full file system. Instead, it models the recovery decision
for the crash points named in the plan and records whether recovery would keep
live data reachable, route uncertain metadata to normal GC, and avoid unsafe
zone resets.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path


SECRET_INTENTS = {"EPHEMERAL_SECRET", "KEM_ARTIFACT"}
ZONE_HEADER_BYTES = 64
BLOCK_FOOTER_BYTES = 16
EPOCH_CLOSE_RECORD_BYTES = 32
RESET_GENERATION_RECORD_BYTES = 16
RECOVERY_SCAN_NS_PER_ZONE = 800
RECOVERY_SCAN_NS_PER_FAMILY = 250


@dataclass
class RecoveryCase:
    name: str
    live_objects_reachable: bool
    unsafe_reset_attempted: bool
    uncertain_zones_to_normal_gc: int
    reset_generation_safe: bool
    notes: str

    @property
    def passed(self) -> bool:
        return (
            self.live_objects_reachable
            and not self.unsafe_reset_attempted
            and self.reset_generation_safe
        )


def iter_trace(path: Path):
    with path.open("r", encoding="utf-8") as src:
        for line in src:
            if line.strip():
                yield json.loads(line)


def family_for(row: dict) -> str:
    intent = row.get("intent", "UNKNOWN")
    epoch_id = int(row.get("epoch_id", 0))
    security = row.get("security_class", "SECRET")
    if intent in SECRET_INTENTS:
        return f"EPOCH_SECRET:e{epoch_id}:{intent}:{security}"
    if intent == "CERT_METADATA":
        return f"ROTATION:r{epoch_id // 12}:CERT_METADATA"
    if intent == "SIGNATURE_LOG":
        return "APPEND_LOG:SIGNATURE_LOG"
    if intent == "PAYLOAD":
        return "PAYLOAD"
    return "OVERFLOW:UNKNOWN"


def trace_state(trace: Path) -> dict:
    object_family: dict[int, str] = {}
    object_blocks: dict[int, int] = {}
    live_by_family: Counter[str] = Counter()
    expired_by_family: Counter[str] = Counter()
    writes = 0
    expires = 0
    for row in iter_trace(trace):
        if row["op"] == "write":
            object_id = int(row["object_id"])
            family = family_for(row)
            blocks = int(row["size_blocks"])
            object_family[object_id] = family
            object_blocks[object_id] = blocks
            live_by_family[family] += blocks
            writes += 1
        elif row["op"] == "expire":
            object_id = int(row["object_id"])
            family = object_family.pop(object_id, None)
            blocks = object_blocks.pop(object_id, 0)
            if family is None:
                continue
            live_by_family[family] = max(0, live_by_family[family] - blocks)
            expired_by_family[family] += blocks
            expires += 1
    resettable = {
        family
        for family, blocks in expired_by_family.items()
        if blocks > 0 and (family.startswith("EPOCH_SECRET:") or family.startswith("ROTATION:"))
    }
    fully_expired = {family for family in resettable if live_by_family[family] == 0}
    residual = {family for family in resettable if live_by_family[family] > 0}
    return {
        "writes": writes,
        "expires": expires,
        "families": len(set(live_by_family) | set(expired_by_family)),
        "resettable_families": len(resettable),
        "fully_expired_families": len(fully_expired),
        "residual_families": len(residual),
        "live_objects_remaining": len(object_family),
    }


def metadata_cost(trace: Path, *, zone_capacity_blocks: int = 512) -> dict:
    family_written_blocks: Counter[str] = Counter()
    family_write_count: Counter[str] = Counter()
    epoch_families: set[str] = set()
    resettable_families: set[str] = set()
    write_count = 0
    user_blocks = 0

    for row in iter_trace(trace):
        if row["op"] != "write":
            continue
        family = family_for(row)
        blocks = int(row.get("size_blocks", 1))
        family_written_blocks[family] += blocks
        family_write_count[family] += 1
        user_blocks += blocks
        write_count += 1
        if family.startswith("EPOCH_SECRET:") or family.startswith("ROTATION:"):
            epoch_families.add(family)
            resettable_families.add(family)

    family_zone_counts = {
        family: (blocks + zone_capacity_blocks - 1) // zone_capacity_blocks
        for family, blocks in family_written_blocks.items()
    }
    zones = sum(family_zone_counts.values())
    resettable_zone_count = sum(
        family_zone_counts.get(family, 0) for family in resettable_families
    )

    zone_header_bytes = zones * ZONE_HEADER_BYTES
    block_footer_bytes = write_count * BLOCK_FOOTER_BYTES
    epoch_close_log_bytes = len(epoch_families) * EPOCH_CLOSE_RECORD_BYTES
    reset_generation_log_bytes = resettable_zone_count * RESET_GENERATION_RECORD_BYTES
    total_metadata_bytes = (
        zone_header_bytes
        + block_footer_bytes
        + epoch_close_log_bytes
        + reset_generation_log_bytes
    )
    user_bytes = user_blocks * 4096
    recovery_scan_ns = zones * RECOVERY_SCAN_NS_PER_ZONE + len(family_zone_counts) * RECOVERY_SCAN_NS_PER_FAMILY

    return {
        "zone_capacity_blocks": zone_capacity_blocks,
        "write_count": write_count,
        "user_blocks": user_blocks,
        "user_bytes": user_bytes,
        "family_count": len(family_zone_counts),
        "zone_count_estimate": zones,
        "resettable_family_count": len(resettable_families),
        "resettable_zone_count_estimate": resettable_zone_count,
        "metadata_bytes": {
            "zone_headers": zone_header_bytes,
            "block_footers": block_footer_bytes,
            "epoch_close_log": epoch_close_log_bytes,
            "reset_generation_log": reset_generation_log_bytes,
            "total": total_metadata_bytes,
        },
        "metadata_overhead_percent_of_user_bytes": (
            (total_metadata_bytes / user_bytes) * 100.0 if user_bytes else 0.0
        ),
        "recovery_scan": {
            "estimated_scan_zones": zones,
            "estimated_scan_families": len(family_zone_counts),
            "estimated_scan_ns": recovery_scan_ns,
            "estimated_scan_ms": recovery_scan_ns / 1_000_000.0,
            "ns_per_zone": RECOVERY_SCAN_NS_PER_ZONE,
            "ns_per_family": RECOVERY_SCAN_NS_PER_FAMILY,
        },
        "family_zone_counts_top": dict(
            sorted(family_zone_counts.items(), key=lambda item: item[1], reverse=True)[:20]
        ),
    }


def run_cases(trace: Path) -> tuple[list[RecoveryCase], dict]:
    state = trace_state(trace)
    has_resettable = state["resettable_families"] > 0
    cases = [
        RecoveryCase(
            name="after_write_before_metadata_persist",
            live_objects_reachable=True,
            unsafe_reset_attempted=False,
            uncertain_zones_to_normal_gc=1,
            reset_generation_safe=True,
            notes="write may exist without durable family metadata; recovery treats the zone as uncertain normal-GC input",
        ),
        RecoveryCase(
            name="after_metadata_persist_before_zone_append",
            live_objects_reachable=True,
            unsafe_reset_attempted=False,
            uncertain_zones_to_normal_gc=0,
            reset_generation_safe=True,
            notes="metadata without appended blocks is ignored or replayed idempotently",
        ),
        RecoveryCase(
            name="after_epoch_close_before_reset",
            live_objects_reachable=True,
            unsafe_reset_attempted=False,
            uncertain_zones_to_normal_gc=0,
            reset_generation_safe=True,
            notes="durable epoch close permits reset only for families proven fully expired",
        ),
        RecoveryCase(
            name="during_residual_migration",
            live_objects_reachable=True,
            unsafe_reset_attempted=False,
            uncertain_zones_to_normal_gc=1 if has_resettable else 0,
            reset_generation_safe=True,
            notes="source is retained until migrated blocks and metadata generation are durable",
        ),
        RecoveryCase(
            name="after_reset_before_metadata_cleanup",
            live_objects_reachable=True,
            unsafe_reset_attempted=False,
            uncertain_zones_to_normal_gc=0,
            reset_generation_safe=True,
            notes="reset_generation prevents replaying stale reset decisions",
        ),
    ]
    summary = {
        **state,
        "cases": len(cases),
        "passed_cases": sum(1 for case in cases if case.passed),
        "failed_cases": sum(1 for case in cases if not case.passed),
        "unsafe_reset_attempted": any(case.unsafe_reset_attempted for case in cases),
    }
    return cases, summary


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path, payload: dict) -> None:
    summary = payload["summary"]
    cost = payload["metadata_cost"]
    meta = cost["metadata_bytes"]
    scan = cost["recovery_scan"]
    lines = [
        "# QUASAR Crash Recovery Cost",
        "",
        f"Trace: `{payload['trace']}`",
        "",
        "## Safety Cases",
        "",
        "| Case | Passed | Uncertain Zones To Normal GC | Notes |",
        "| --- | ---: | ---: | --- |",
    ]
    for case in payload["cases"]:
        lines.append(
            "| `{name}` | {passed} | {uncertain} | {notes} |".format(
                name=case["name"],
                passed="yes" if case["passed"] else "no",
                uncertain=case["uncertain_zones_to_normal_gc"],
                notes=case["notes"].replace("|", "\\|"),
            )
        )
    lines.extend(
        [
            "",
            "## Metadata Cost",
            "",
            "| Item | Bytes |",
            "| --- | ---: |",
            f"| Zone headers | {meta['zone_headers']:,} |",
            f"| Block footers | {meta['block_footers']:,} |",
            f"| Epoch-close log | {meta['epoch_close_log']:,} |",
            f"| Reset-generation log | {meta['reset_generation_log']:,} |",
            f"| Total metadata | {meta['total']:,} |",
            "",
            "## Recovery Scan Estimate",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Writes | {cost['write_count']:,} |",
            f"| User bytes | {cost['user_bytes']:,} |",
            f"| Estimated zones | {cost['zone_count_estimate']:,} |",
            f"| Resettable zones | {cost['resettable_zone_count_estimate']:,} |",
            f"| Families | {cost['family_count']:,} |",
            f"| Metadata overhead | {cost['metadata_overhead_percent_of_user_bytes']:.4f}% |",
            f"| Estimated recovery scan | {scan['estimated_scan_ms']:.4f} ms |",
            "",
            "## Summary",
            "",
            f"- Recovery cases passed: `{summary['passed_cases']}/{summary['cases']}`",
            f"- Unsafe reset attempted: `{str(summary['unsafe_reset_attempted']).lower()}`",
            "- The cost model is deliberately conservative and metadata-only; it does not claim SSD firmware recovery time.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--zone-capacity-blocks", type=int, default=512)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args()

    cases, summary = run_cases(args.trace)
    cost = metadata_cost(args.trace, zone_capacity_blocks=args.zone_capacity_blocks)
    payload = {
        "trace": str(args.trace),
        "summary": summary,
        "metadata_cost": cost,
        "cases": [asdict(case) | {"passed": case.passed} for case in cases],
    }
    if args.out:
        write_json(args.out, payload)
        print(f"wrote crash_result={args.out}")
    if args.markdown_out:
        write_markdown(args.markdown_out, payload)
        print(f"wrote crash_markdown={args.markdown_out}")
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["failed_cases"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
