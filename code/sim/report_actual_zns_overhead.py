#!/usr/bin/env python3
"""Summarize actual-ZNS replay overhead for baseline-vs-QUASAR reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


POLICIES = ["fifo", "sepbit-style", "midas-style", "dogi-history", "quasar", "quasar-dogi-hybrid"]
POLICY_CPU_LABEL = {
    "dogi-history": "dogi-mlp",
    "quasar": "quasar-hint",
    "quasar-dogi-hybrid": "quasar-dogi-hybrid",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def fmt_float(value: float | None, digits: int = 3) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def fmt_int(value: int | float | None) -> str:
    return "N/A" if value is None else f"{int(value):,}"


def fmt_ms(ns: float | int | None) -> str:
    return "N/A" if ns is None else f"{float(ns) / 1_000_000:.3f}"


def weighted_avg(total_ns: float, count: int) -> float | None:
    if count <= 0:
        return None
    return total_ns / count


def cpu_overhead_by_policy(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {}
    aggregate = data.get("aggregate", {})
    out = {}
    for policy, label in POLICY_CPU_LABEL.items():
        item = aggregate.get(label, {})
        if item:
            out[policy] = {
                "label": label,
                "median_ns_per_write": item.get("median_ns_per_write"),
                "min_ns_per_write": item.get("min_ns_per_write"),
                "max_ns_per_write": item.get("max_ns_per_write"),
            }
    return out


def add_latency(acc: dict[str, Any], latency: dict[str, Any], prefix: str) -> None:
    count = int(latency.get("count") or 0)
    avg = float(latency.get("avg_ns") or 0.0)
    acc[f"{prefix}_count"] += count
    acc[f"{prefix}_weighted_total_ns"] += avg * count
    acc[f"{prefix}_worst_p95_ns"] = max(acc[f"{prefix}_worst_p95_ns"], int(latency.get("p95_ns") or 0))
    acc[f"{prefix}_worst_p99_ns"] = max(acc[f"{prefix}_worst_p99_ns"], int(latency.get("p99_ns") or 0))
    acc[f"{prefix}_max_ns"] = max(acc[f"{prefix}_max_ns"], int(latency.get("max_ns") or 0))


def empty_policy_row(policy: str) -> dict[str, Any]:
    return {
        "policy": policy,
        "rows": 0,
        "failed_rows": 0,
        "physical_bytes_written": 0,
        "physical_append_commands": 0,
        "physical_reset_commands": 0,
        "semantic_physical_reset_commands": 0,
        "total_wall_time_s": 0.0,
        "max_live_physical_zones": 0,
        "append_count": 0,
        "append_weighted_total_ns": 0.0,
        "append_worst_p95_ns": 0,
        "append_worst_p99_ns": 0,
        "append_max_ns": 0,
        "reset_count": 0,
        "reset_weighted_total_ns": 0.0,
        "reset_worst_p95_ns": 0,
        "reset_worst_p99_ns": 0,
        "reset_max_ns": 0,
    }


def summarize_artifacts(paths: list[Path], c_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    by_policy = {policy: empty_policy_row(policy) for policy in POLICIES}
    workload_rows = []
    for path in paths:
        report = load_json(path)
        for row in report.get("rows", []):
            if row.get("packing") != "secret-group":
                continue
            policy = row.get("policy")
            if policy not in by_policy:
                continue
            physical = row.get("physical", {})
            acc = by_policy[policy]
            acc["rows"] += 1
            acc["failed_rows"] += int(bool(physical.get("failed")))
            acc["physical_bytes_written"] += int(physical.get("physical_bytes_written") or 0)
            acc["physical_append_commands"] += int(physical.get("physical_append_commands") or 0)
            acc["physical_reset_commands"] += int(physical.get("cleanup_reset_zones") or 0) + int(
                physical.get("initial_reset_zones") or 0
            ) + int(physical.get("physical_reset_commands") or 0)
            acc["semantic_physical_reset_commands"] += int(physical.get("physical_reset_commands") or 0)
            acc["total_wall_time_s"] += float(physical.get("wall_time_s") or 0.0)
            acc["max_live_physical_zones"] = max(
                acc["max_live_physical_zones"], int(physical.get("max_live_physical_zones") or 0)
            )
            add_latency(acc, physical.get("append_latency", {}), "append")
            add_latency(acc, physical.get("reset_latency", {}), "reset")
            workload_rows.append(
                {
                    "artifact": str(path),
                    "workload": row.get("workload"),
                    "policy": policy,
                    "failed": bool(physical.get("failed")),
                    "append_p99_ns": physical.get("append_latency", {}).get("p99_ns"),
                    "reset_p99_ns": physical.get("reset_latency", {}).get("p99_ns"),
                    "wall_time_s": physical.get("wall_time_s"),
                    "throughput_mib_s": physical.get("throughput_mib_s"),
                    "semantic_physical_resets": physical.get("physical_reset_commands"),
                }
            )

    cpu = cpu_overhead_by_policy(c_policy)
    for policy, acc in by_policy.items():
        acc["append_avg_ns"] = weighted_avg(acc.pop("append_weighted_total_ns"), acc["append_count"])
        acc["reset_avg_ns"] = weighted_avg(acc.pop("reset_weighted_total_ns"), acc["reset_count"])
        acc["physical_mib_written"] = acc["physical_bytes_written"] / (1024 * 1024)
        acc["throughput_mib_s"] = (
            acc["physical_mib_written"] / acc["total_wall_time_s"] if acc["total_wall_time_s"] > 0 else None
        )
        acc["cpu_policy"] = cpu.get(policy, {})

    dogi = by_policy["dogi-history"]
    hybrid = by_policy["quasar-dogi-hybrid"]
    return {
        "scope": "actual ZNS replay overhead plus C-level policy-decision overhead",
        "artifact_count": len(paths),
        "row_count": len(workload_rows),
        "failed_rows": sum(1 for row in workload_rows if row["failed"]),
        "by_policy": by_policy,
        "workload_rows": workload_rows,
        "hybrid_vs_dogi": {
            "append_avg_ratio": (
                hybrid["append_avg_ns"] / dogi["append_avg_ns"]
                if hybrid["append_avg_ns"] and dogi["append_avg_ns"]
                else None
            ),
            "throughput_ratio": (
                hybrid["throughput_mib_s"] / dogi["throughput_mib_s"]
                if hybrid["throughput_mib_s"] and dogi["throughput_mib_s"]
                else None
            ),
            "semantic_reset_delta": hybrid["semantic_physical_reset_commands"]
            - dogi["semantic_physical_reset_commands"],
            "cpu_median_ns_ratio": (
                hybrid.get("cpu_policy", {}).get("median_ns_per_write")
                / dogi.get("cpu_policy", {}).get("median_ns_per_write")
                if hybrid.get("cpu_policy", {}).get("median_ns_per_write")
                and dogi.get("cpu_policy", {}).get("median_ns_per_write")
                else None
            ),
        },
        "caveat": (
            "Actual-ZNS latency is measured through zonefs helper appends/truncates and includes user-space helper overhead. "
            "C-level CPU numbers isolate only placement-decision cost."
        ),
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Actual-ZNS Overhead Summary",
        "",
        f"- Scope: {summary['scope']}",
        f"- Artifacts: `{summary['artifact_count']}`",
        f"- Rows: `{summary['row_count']}`, failed rows: `{summary['failed_rows']}`",
        f"- Caveat: {summary['caveat']}",
        "",
        "| Policy | Rows | Append Commands | Semantic Resets | Total Resets incl. cleanup | Physical MiB | Throughput MiB/s | Append Avg ms | Worst Append p99 ms | Reset Avg ms | Worst Reset p99 ms | Max Live Zones | CPU Median ns/write |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for policy in POLICIES:
        row = summary["by_policy"][policy]
        cpu = row.get("cpu_policy", {})
        lines.append(
            "| `{policy}` | {rows} | {append_cmds} | {semantic_resets} | {resets} | {mib} | {throughput} | {append_avg} | {append_p99} | {reset_avg} | {reset_p99} | {zones} | {cpu_ns} |".format(
                policy=policy,
                rows=fmt_int(row["rows"]),
                append_cmds=fmt_int(row["physical_append_commands"]),
                semantic_resets=fmt_int(row["semantic_physical_reset_commands"]),
                resets=fmt_int(row["physical_reset_commands"]),
                mib=fmt_float(row["physical_mib_written"], 1),
                throughput=fmt_float(row["throughput_mib_s"], 2),
                append_avg=fmt_ms(row["append_avg_ns"]),
                append_p99=fmt_ms(row["append_worst_p99_ns"]),
                reset_avg=fmt_ms(row["reset_avg_ns"]),
                reset_p99=fmt_ms(row["reset_worst_p99_ns"]),
                zones=fmt_int(row["max_live_physical_zones"]),
                cpu_ns=fmt_float(cpu.get("median_ns_per_write"), 1),
            )
        )
    comparison = summary["hybrid_vs_dogi"]
    lines.extend(
        [
            "",
            "Hybrid vs DOGI-history:",
            "",
            f"- Append average latency ratio: `{fmt_float(comparison['append_avg_ratio'], 3)}`",
            f"- Throughput ratio: `{fmt_float(comparison['throughput_ratio'], 3)}`",
            f"- Semantic reset command delta: `{fmt_int(comparison['semantic_reset_delta'])}`",
            f"- C-level policy-decision median ratio: `{fmt_float(comparison['cpu_median_ns_ratio'], 3)}`",
            "",
            "Reading:",
            "",
            "- QUASAR-DOGI hybrid pays extra semantic reset work because it actually makes secret cohorts reset-eligible.",
            "- The helper-based actual-ZNS path is useful for relative append/reset feasibility, but not a final low-overhead latency number.",
            "- The C-level policy benchmark isolates the allocator decision cost: DOGI-style MLP is much more expensive than QUASAR hint routing, while the hybrid sits between them because it preserves DOGI-style payload handling.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--physical",
        type=Path,
        action="append",
        default=[],
        help="packed physical actual-ZNS replay JSON; may be repeated",
    )
    parser.add_argument("--c-policy-overhead", type=Path, default=Path("artifacts/results/c-policy-overhead.json"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/actual-zns-overhead-summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/actual-zns-overhead-summary.md"))
    args = parser.parse_args()
    paths = args.physical or [
        Path("artifacts/results/packed-physical-zonefs-replay-dogi-paper-pqc2000-z512-secret-group-helper.json"),
        Path("artifacts/results/fast-db-pressure/packed-physical-zonefs-sysbench-p20-p40-z404-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-pqc2000-z512-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc4000-z560-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc8000-z863-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc4000-z733-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc8000-z733-helper.json"),
    ]
    c_policy = load_json(args.c_policy_overhead) if args.c_policy_overhead.exists() else None
    summary = summarize_artifacts(paths, c_policy)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "markdown_out": str(args.markdown_out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
