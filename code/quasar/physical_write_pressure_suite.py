#!/usr/bin/env python3
"""Replay simulator-derived write pressure on a physical zonefs mount.

This is intentionally different from trace-level QUASAR replay.  The simulator
already decides how many user and GC-copy blocks each policy would write.  This
tool translates that accounting into actual bytes written to a real ZNS device:

    physical blocks = scale * (user_write_blocks + gc_write_blocks)

The result is an apples-to-apples physical pressure test: if a policy has a
lower WAF in the simulator, the physical device receives fewer append bytes in
the same workload/policy row.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import physical_zonefs_replay as zonefs
except ModuleNotFoundError:  # pragma: no cover - package test path
    from quasar import physical_zonefs_replay as zonefs


DEFAULT_POLICIES = [
    "fifo",
    "midas-style",
    "dogi-history",
    "quasar",
    "quasar-dogi-hybrid",
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def workload_base(workload: str) -> str:
    if "-pqc" in workload:
        return workload.rsplit("-pqc", 1)[0]
    return workload


def workload_ratio_tag(workload: str) -> str:
    if "-pqc" in workload:
        return "pqc" + workload.rsplit("-pqc", 1)[1]
    return "unknown"


def select_rows(
    rows: list[dict[str, Any]],
    *,
    ratio_tag: str,
    policies: list[str],
    workloads: list[str],
) -> list[dict[str, Any]]:
    policy_set = set(policies)
    workload_set = set(workloads)
    selected = []
    for row in rows:
        workload = str(row["workload"])
        if ratio_tag != "all" and workload_ratio_tag(workload) != ratio_tag:
            continue
        if workload_set and workload_base(workload) not in workload_set and workload not in workload_set:
            continue
        if str(row["policy"]) not in policy_set:
            continue
        selected.append(row)
    return sorted(selected, key=lambda row: (workload_base(str(row["workload"])), str(row["policy"])))


def pressure_blocks(row: dict[str, Any], scale: int) -> int:
    user = int(row.get("user_write_blocks", 0))
    gc = int(row.get("gc_write_blocks", 0))
    return scale * (user + gc)


def mib(blocks: int) -> float:
    return blocks * 4096 / (1024 * 1024)


def reset_zone_files(zone_files: list[Path], *, execute: bool, fail_fast: bool) -> tuple[list[dict[str, Any]], list[int]]:
    rows = []
    latencies = []
    if not execute:
        return rows, latencies
    for zone_file in zone_files:
        result = zonefs.run_truncate_reset(zone_file)
        rows.append(result)
        latencies.append(int(result["latency_ns"]))
        if not result["succeeded"] and fail_fast:
            raise RuntimeError(f"zonefs reset failed: {json.dumps(result, sort_keys=True)}")
    return rows, latencies


def append_blocks_across_zones(
    zone_files: list[Path],
    *,
    blocks: int,
    zone_capacity_blocks: int,
    max_blocks_per_dd: int,
    execute: bool,
    fail_fast: bool,
) -> dict[str, Any]:
    remaining = blocks
    zone_index = 0
    dd_ops = 0
    bytes_written = 0
    append_latencies: list[int] = []
    append_rows: list[dict[str, Any]] = []
    started = time.perf_counter_ns()

    while remaining > 0:
        if zone_index >= len(zone_files):
            failure = {
                "succeeded": False,
                "stderr": "not enough selected zone files for planned physical blocks",
                "remaining_blocks": remaining,
                "zone_files": [str(path) for path in zone_files],
            }
            if fail_fast:
                raise RuntimeError(json.dumps(failure, sort_keys=True))
            return {
                "failed": True,
                "failures": [failure],
                "executed_blocks": blocks - remaining,
                "bytes_written": bytes_written,
                "dd_ops": dd_ops,
                "append_latency": zonefs.latency_summary(append_latencies),
                "append_rows": append_rows,
                "wall_time_ns": time.perf_counter_ns() - started,
            }

        target = zone_files[zone_index]
        current_blocks = target.stat().st_size // 4096 if execute else 0
        free_blocks = max(0, zone_capacity_blocks - current_blocks)
        if free_blocks <= 0:
            zone_index += 1
            continue
        chunk = min(remaining, free_blocks)
        if max_blocks_per_dd > 0:
            chunk = min(chunk, max_blocks_per_dd)

        if execute:
            result = zonefs.run_dd_append(target, chunk)
            append_rows.append(result)
            if not result["succeeded"]:
                if fail_fast:
                    raise RuntimeError(f"zonefs append failed: {json.dumps(result, sort_keys=True)}")
                return {
                    "failed": True,
                    "failures": [result],
                    "executed_blocks": blocks - remaining,
                    "bytes_written": bytes_written,
                    "dd_ops": dd_ops,
                    "append_latency": zonefs.latency_summary(append_latencies),
                    "append_rows": append_rows,
                    "wall_time_ns": time.perf_counter_ns() - started,
                }
            append_latencies.append(int(result["latency_ns"]))
            bytes_written += int(result["bytes_requested"])
        else:
            bytes_written += chunk * 4096
        dd_ops += 1
        remaining -= chunk

    return {
        "failed": False,
        "failures": [],
        "executed_blocks": blocks,
        "bytes_written": bytes_written,
        "dd_ops": dd_ops,
        "append_latency": zonefs.latency_summary(append_latencies),
        "append_rows": append_rows[:8],
        "wall_time_ns": time.perf_counter_ns() - started,
        "zone_files_touched": min(len(zone_files), zone_index + 1),
    }


def execute_suite(rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    zone_files = zonefs.select_zone_files(
        args.mount,
        start_index=args.start_zone_index,
        max_zone_files=args.max_zone_files,
        require_empty=False,
    )
    suite_started = time.perf_counter_ns()
    row_reports: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    reset_latencies: list[int] = []

    for row in rows:
        planned_blocks = pressure_blocks(row, args.scale)
        reset_rows, row_reset_latencies = reset_zone_files(
            zone_files,
            execute=args.execute,
            fail_fast=args.fail_fast,
        )
        reset_latencies.extend(row_reset_latencies)
        result = append_blocks_across_zones(
            zone_files,
            blocks=planned_blocks,
            zone_capacity_blocks=args.zone_capacity_blocks,
            max_blocks_per_dd=args.max_blocks_per_dd,
            execute=args.execute,
            fail_fast=args.fail_fast,
        )
        wall_s = result["wall_time_ns"] / 1_000_000_000
        report = {
            "workload": row["workload"],
            "workload_base": workload_base(str(row["workload"])),
            "ratio_tag": workload_ratio_tag(str(row["workload"])),
            "policy": row["policy"],
            "source_trace": row.get("trace"),
            "source_waf": row.get("waf"),
            "source_user_write_blocks": int(row.get("user_write_blocks", 0)),
            "source_gc_write_blocks": int(row.get("gc_write_blocks", 0)),
            "source_stale_secret_blocks_remaining": int(row.get("stale_secret_blocks_remaining", 0)),
            "scale": args.scale,
            "planned_physical_blocks": planned_blocks,
            "planned_physical_mib": mib(planned_blocks),
            "executed_blocks": int(result["executed_blocks"]),
            "bytes_written": int(result["bytes_written"]),
            "dd_ops": int(result["dd_ops"]),
            "wall_time_s": wall_s,
            "throughput_mib_s": (result["bytes_written"] / (1024 * 1024) / wall_s) if wall_s and args.execute else 0.0,
            "append_latency": result["append_latency"],
            "zone_files_touched": result.get("zone_files_touched", 0),
            "reset_count": len(reset_rows),
            "failed": bool(result["failed"]),
            "failures": result["failures"][:4],
        }
        row_reports.append(report)
        if report["failed"]:
            failures.extend(report["failures"])
            break

    wall_time_ns = time.perf_counter_ns() - suite_started
    return {
        "suite": "physical-zonefs-write-pressure",
        "execute": args.execute,
        "source_eval": str(args.eval),
        "mount": str(args.mount),
        "ratio_tag": args.ratio_tag,
        "policies": args.policies,
        "workloads": args.workloads,
        "scale": args.scale,
        "zone_capacity_blocks": args.zone_capacity_blocks,
        "max_blocks_per_dd": args.max_blocks_per_dd,
        "zone_files": [str(path) for path in zone_files],
        "failed": bool(failures),
        "failures": failures[:8],
        "rows": row_reports,
        "summary": summarize(row_reports, wall_time_ns, reset_latencies),
        "notes": [
            "This is a simulator-derived physical write-pressure replay, not exact DOGI device firmware execution.",
            "Each row resets the selected zonefs files before appending the row's user+GC physical blocks.",
            "Lower simulated WAF appears here as fewer physical bytes written for the same workload.",
        ],
    }


def summarize(row_reports: list[dict[str, Any]], wall_time_ns: int, reset_latencies: list[int]) -> dict[str, Any]:
    by_policy: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "rows": 0,
        "source_user_write_blocks": 0,
        "source_gc_write_blocks": 0,
        "planned_physical_blocks": 0,
        "bytes_written": 0,
        "wall_time_s": 0.0,
        "dd_ops": 0,
    })
    by_workload: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    all_append_latencies: list[int] = []
    for row in row_reports:
        policy = str(row["policy"])
        item = by_policy[policy]
        item["rows"] += 1
        item["source_user_write_blocks"] += int(row["source_user_write_blocks"])
        item["source_gc_write_blocks"] += int(row["source_gc_write_blocks"])
        item["planned_physical_blocks"] += int(row["planned_physical_blocks"])
        item["bytes_written"] += int(row["bytes_written"])
        item["wall_time_s"] += float(row["wall_time_s"])
        item["dd_ops"] += int(row["dd_ops"])
        latency = row.get("append_latency", {})
        if latency.get("count"):
            all_append_latencies.append(int(latency.get("p99_ns", 0)))
        by_workload[str(row["workload_base"])][policy] = row

    policy_summary = {}
    for policy, item in sorted(by_policy.items()):
        user = max(1, int(item["source_user_write_blocks"]))
        policy_summary[policy] = {
            **item,
            "derived_waf": (item["source_user_write_blocks"] + item["source_gc_write_blocks"]) / user,
            "planned_physical_mib": mib(int(item["planned_physical_blocks"])),
            "throughput_mib_s": (
                item["bytes_written"] / (1024 * 1024) / item["wall_time_s"]
                if item["wall_time_s"]
                else 0.0
            ),
        }

    comparisons = []
    total_dogi_blocks = 0
    total_hybrid_blocks = 0
    total_dogi_stale = 0
    total_hybrid_stale = 0
    for workload, policies in sorted(by_workload.items()):
        dogi = policies.get("dogi-history")
        hybrid = policies.get("quasar-dogi-hybrid")
        if not dogi or not hybrid:
            continue
        dogi_blocks = int(dogi["planned_physical_blocks"])
        hybrid_blocks = int(hybrid["planned_physical_blocks"])
        total_dogi_blocks += dogi_blocks
        total_hybrid_blocks += hybrid_blocks
        total_dogi_stale += int(dogi["source_stale_secret_blocks_remaining"])
        total_hybrid_stale += int(hybrid["source_stale_secret_blocks_remaining"])
        comparisons.append(
            {
                "workload": workload,
                "dogi_physical_blocks": dogi_blocks,
                "hybrid_physical_blocks": hybrid_blocks,
                "hybrid_block_reduction_vs_dogi": (
                    (dogi_blocks - hybrid_blocks) / dogi_blocks if dogi_blocks else 0.0
                ),
                "dogi_stale_secret_blocks": int(dogi["source_stale_secret_blocks_remaining"]),
                "hybrid_stale_secret_blocks": int(hybrid["source_stale_secret_blocks_remaining"]),
            }
        )

    return {
        "all_passed": not any(row.get("failed") for row in row_reports),
        "row_count": len(row_reports),
        "total_bytes_written": sum(int(row["bytes_written"]) for row in row_reports),
        "total_planned_physical_blocks": sum(int(row["planned_physical_blocks"]) for row in row_reports),
        "total_wall_time_s": wall_time_ns / 1_000_000_000,
        "append_p99_latency_summary": zonefs.latency_summary(all_append_latencies),
        "reset_latency": zonefs.latency_summary(reset_latencies),
        "by_policy": policy_summary,
        "dogi_vs_hybrid": {
            "comparisons": comparisons,
            "total_dogi_physical_blocks": total_dogi_blocks,
            "total_hybrid_physical_blocks": total_hybrid_blocks,
            "hybrid_block_reduction_vs_dogi": (
                (total_dogi_blocks - total_hybrid_blocks) / total_dogi_blocks if total_dogi_blocks else 0.0
            ),
            "total_dogi_stale_secret_blocks": total_dogi_stale,
            "total_hybrid_stale_secret_blocks": total_hybrid_stale,
            "stale_secret_blocks_avoided": total_dogi_stale - total_hybrid_stale,
        },
    }


def fmt_int(value: int | float) -> str:
    return f"{int(value):,}"


def fmt_float(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Physical Zonefs Write-Pressure Suite",
        "",
        f"- Executed: `{report['execute']}`",
        f"- Source eval: `{report['source_eval']}`",
        f"- Mount: `{report['mount']}`",
        f"- Ratio filter: `{report['ratio_tag']}`",
        f"- Scale: `{report['scale']}x`",
        f"- Failed: `{report['failed']}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| rows | {summary['row_count']} |",
        f"| total planned physical blocks | {fmt_int(summary['total_planned_physical_blocks'])} |",
        f"| total bytes written | {fmt_int(summary['total_bytes_written'])} |",
        f"| total GiB written | {summary['total_bytes_written'] / (1024 ** 3):.3f} |",
        f"| wall time s | {summary['total_wall_time_s']:.3f} |",
        f"| reset p99 latency ns | {summary['reset_latency']['p99_ns']} |",
        "",
        "## By Policy",
        "",
        "| Policy | Rows | Derived WAF | Physical MiB | GC Blocks | Throughput MiB/s |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for policy, item in sorted(summary["by_policy"].items()):
        lines.append(
            "| `{policy}` | {rows} | {waf} | {mib_value} | {gc} | {thr} |".format(
                policy=policy,
                rows=item["rows"],
                waf=fmt_float(item["derived_waf"], 4),
                mib_value=fmt_float(item["planned_physical_mib"], 1),
                gc=fmt_int(item["source_gc_write_blocks"]),
                thr=fmt_float(item["throughput_mib_s"], 1),
            )
        )
    comparison = summary["dogi_vs_hybrid"]
    lines.extend(
        [
            "",
            "## DOGI vs QUASAR Hybrid",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| DOGI physical blocks | {fmt_int(comparison['total_dogi_physical_blocks'])} |",
            f"| Hybrid physical blocks | {fmt_int(comparison['total_hybrid_physical_blocks'])} |",
            f"| Hybrid block reduction vs DOGI | {100.0 * comparison['hybrid_block_reduction_vs_dogi']:.2f}% |",
            f"| stale secret blocks avoided | {fmt_int(comparison['stale_secret_blocks_avoided'])} |",
            "",
            "## Per Workload: DOGI vs Hybrid",
            "",
            "| Workload | DOGI Blocks | Hybrid Blocks | Reduction | DOGI Stale | Hybrid Stale |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in comparison["comparisons"]:
        lines.append(
            "| `{workload}` | {dogi} | {hybrid} | {reduction:.2f}% | {dogi_stale} | {hybrid_stale} |".format(
                workload=item["workload"],
                dogi=fmt_int(item["dogi_physical_blocks"]),
                hybrid=fmt_int(item["hybrid_physical_blocks"]),
                reduction=100.0 * item["hybrid_block_reduction_vs_dogi"],
                dogi_stale=fmt_int(item["dogi_stale_secret_blocks"]),
                hybrid_stale=fmt_int(item["hybrid_stale_secret_blocks"]),
            )
        )
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in report["notes"])
    if report.get("failures"):
        lines.extend(["", "## First Failure", ""])
        first = report["failures"][0]
        lines.append("```json")
        lines.append(json.dumps(first, indent=2, sort_keys=True))
        lines.append("```")
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], json_out: Path, markdown_out: Path) -> None:
    json_out.parent.mkdir(parents=True, exist_ok=True)
    markdown_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_out.write_text(markdown(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval", type=Path, default=Path("artifacts/results/dogi-paper-workloads-quick/pqc2000-eval-rf0.json"))
    parser.add_argument("--mount", type=Path, default=Path("/mnt/zn540"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ratio-tag", default="pqc2000")
    parser.add_argument("--policies", default=",".join(DEFAULT_POLICIES))
    parser.add_argument("--workloads", default="")
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--zone-capacity-blocks", type=int, default=275712)
    parser.add_argument("--max-blocks-per-dd", type=int, default=8192)
    parser.add_argument("--max-zone-files", type=int, default=8)
    parser.add_argument("--start-zone-index", type=int, default=10)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/physical-zonefs-write-pressure.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/physical-zonefs-write-pressure.md"))
    args = parser.parse_args()

    if args.scale <= 0:
        raise SystemExit("--scale must be positive")
    if args.zone_capacity_blocks <= 0:
        raise SystemExit("--zone-capacity-blocks must be positive")
    if args.max_blocks_per_dd < 0:
        raise SystemExit("--max-blocks-per-dd must be non-negative")
    args.policies = parse_csv(args.policies)
    args.workloads = parse_csv(args.workloads)

    rows = load_json(args.eval)
    selected = select_rows(rows, ratio_tag=args.ratio_tag, policies=args.policies, workloads=args.workloads)
    if not selected:
        raise SystemExit("no rows selected")
    report = execute_suite(selected, args)
    write_outputs(report, args.out, args.markdown_out)
    print(
        json.dumps(
            {
                "execute": report["execute"],
                "failed": report["failed"],
                "rows": report["summary"]["row_count"],
                "total_gib_written": report["summary"]["total_bytes_written"] / (1024 ** 3),
                "hybrid_block_reduction_vs_dogi": report["summary"]["dogi_vs_hybrid"]["hybrid_block_reduction_vs_dogi"],
            },
            sort_keys=True,
        )
    )
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
