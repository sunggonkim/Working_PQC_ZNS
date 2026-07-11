#!/usr/bin/env python3
"""Summarize DOGI/FAST dynamic-service pressure experiments for QUASAR."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


POLICIES = [
    "fifo",
    "sepbit-style",
    "midas-style",
    "dogi-history",
    "quasar",
    "quasar-dogi-hybrid",
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def pct_reduction(before: float, after: float) -> float | None:
    if before == 0:
        return None
    return (before - after) / before


def fmt_float(value: float | int | None, digits: int = 4) -> str:
    return "N/A" if value is None else f"{float(value):.{digits}f}"


def fmt_int(value: int | float | None) -> str:
    return "N/A" if value is None else f"{int(value):,}"


def fmt_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def policy_rows(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = report.get("summary", {}).get("by_policy_packing", {})
    out: dict[str, dict[str, Any]] = {}
    for policy in POLICIES:
        item = rows.get(f"{policy}::secret-group", {})
        out[policy] = {
            "sim_waf": item.get("sim_waf"),
            "physical_waf": item.get("physical_waf"),
            "sim_gc_blocks": item.get("sim_gc_blocks"),
            "sim_stale_secret_blocks": item.get("sim_stale_secret_blocks"),
            "physical_reset_commands": item.get("physical_reset_commands"),
            "secret_blocks_waiting_for_physical_reset": item.get("secret_blocks_waiting_for_physical_reset"),
            "max_secret_blocks_waiting_for_physical_reset": item.get("max_secret_blocks_waiting_for_physical_reset"),
            "avg_space_utilization": item.get("avg_space_utilization"),
            "max_live_physical_zones": item.get("max_live_physical_zones"),
            "failed_rows": item.get("failed_rows"),
        }
    return out


def summarize_physical(path: Path) -> dict[str, Any]:
    report = load_json(path)
    rows = policy_rows(report)
    dogi = rows["dogi-history"]
    hybrid = rows["quasar-dogi-hybrid"]
    dogi_waf = float(dogi.get("sim_waf") or 0.0)
    hybrid_waf = float(hybrid.get("sim_waf") or 0.0)
    dogi_gc = float(dogi.get("sim_gc_blocks") or 0)
    hybrid_gc = float(hybrid.get("sim_gc_blocks") or 0)
    dogi_stale = int(dogi.get("sim_stale_secret_blocks") or 0)
    hybrid_stale = int(hybrid.get("sim_stale_secret_blocks") or 0)
    return {
        "path": str(path),
        "scope": "actual-ZNS packed replay for DOGI dynamic workload axis",
        "traces": report.get("traces", []),
        "logical_zones": report.get("logical_zones"),
        "logical_zone_capacity": report.get("logical_zone_capacity"),
        "rows": report.get("summary", {}).get("row_count"),
        "failed_rows": report.get("summary", {}).get("failed_rows"),
        "wall_time_s": report.get("summary", {}).get("wall_time_s"),
        "append_engine": report.get("append_engine"),
        "helper_chunk_blocks": report.get("helper_chunk_blocks"),
        "policies": rows,
        "hybrid_vs_dogi": {
            "waf_reduction": pct_reduction(dogi_waf, hybrid_waf),
            "gc_reduction": pct_reduction(dogi_gc, hybrid_gc),
            "stale_secret_reduction_blocks": dogi_stale - hybrid_stale,
            "dogi_completed": int(dogi.get("failed_rows") or 0) == 0,
            "hybrid_completed": int(hybrid.get("failed_rows") or 0) == 0,
        },
    }


def summarize_dryrun(path: Path) -> dict[str, Any]:
    report = load_json(path)
    rows = policy_rows(report)
    return {
        "path": str(path),
        "logical_zones": report.get("logical_zones"),
        "failed_rows": report.get("summary", {}).get("failed_rows"),
        "dogi_failed_rows": rows["dogi-history"].get("failed_rows"),
        "hybrid_failed_rows": rows["quasar-dogi-hybrid"].get("failed_rows"),
        "hybrid_waf": rows["quasar-dogi-hybrid"].get("sim_waf"),
        "hybrid_gc_blocks": rows["quasar-dogi-hybrid"].get("sim_gc_blocks"),
    }


def workload_label(physical: dict[str, Any]) -> str:
    traces = physical.get("traces", [])
    if not traces:
        return "unknown"
    return Path(traces[0]).stem


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# FAST Dynamic-Service Pressure Summary",
        "",
        "This experiment answers the workload-hardness concern on DOGI dynamic axes. The traces use Exchange-like, Varmail-like, and Alibaba-like workloads from the DOGI/FAST workload family with high PQC overlays (`pqc8000`) and tight logical-zone pressure.",
        "",
        "Boundary: these are DOGI-paper-shaped synthetic dynamic-service traces with PQC lifecycle overlays, not the private original Microsoft Exchange, Varmail, Alibaba, or other traces used by the DOGI paper.",
        "",
        "## Actual ZNS Replays",
        "",
    ]
    for physical in summary["physical"]:
        comparison = physical["hybrid_vs_dogi"]
        lines.extend(
            [
                f"### `{workload_label(physical)}`",
                "",
                f"- Artifact: `{physical['path']}`",
                f"- Trace: `{physical['traces'][0] if physical['traces'] else 'N/A'}`",
                f"- Rows: `{physical['rows']}`, failed rows: `{physical['failed_rows']}`",
                f"- Logical zones: `{physical['logical_zones']}`",
                f"- Wall time: `{physical['wall_time_s']:.3f}` s",
                f"- Append engine: `{physical['append_engine']}`, helper chunk blocks: `{physical['helper_chunk_blocks']}`",
                "",
                "| Policy | Sim WAF | Physical WAF | GC Blocks | Stale Secrets | Semantic Physical Resets | Secret Waiting End | Max Secret Waiting | Avg Util | Max Live Phys Zones |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for policy in POLICIES:
            row = physical["policies"][policy]
            lines.append(
                "| `{policy}` | {sim_waf} | {phys_waf} | {gc} | {stale} | {resets} | {wait} | {max_wait} | {util} | {max_z} |".format(
                    policy=policy,
                    sim_waf=fmt_float(row["sim_waf"]),
                    phys_waf=fmt_float(row["physical_waf"]),
                    gc=fmt_int(row["sim_gc_blocks"]),
                    stale=fmt_int(row["sim_stale_secret_blocks"]),
                    resets=fmt_int(row["physical_reset_commands"]),
                    wait=fmt_int(row["secret_blocks_waiting_for_physical_reset"]),
                    max_wait=fmt_int(row["max_secret_blocks_waiting_for_physical_reset"]),
                    util=fmt_float(row["avg_space_utilization"], 3),
                    max_z=fmt_int(row["max_live_physical_zones"]),
                )
            )
        lines.extend(
            [
                "",
                "Hybrid vs DOGI-style:",
                "",
                f"- WAF reduction: `{fmt_pct(comparison['waf_reduction'])}`",
                f"- GC reduction: `{fmt_pct(comparison['gc_reduction'])}`",
                f"- Stale secret blocks removed: `{fmt_int(comparison['stale_secret_reduction_blocks'])}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Tight-Budget Dry-Run Frontier",
            "",
            "| Dry Run | Logical Zones | Failed Rows | DOGI Failed Rows | Hybrid Failed Rows | Hybrid WAF | Hybrid GC Blocks |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in summary["dryrun_frontier"]:
        lines.append(
            "| `{path}` | {zones} | {failed} | {dogi_failed} | {hybrid_failed} | {hybrid_waf} | {hybrid_gc} |".format(
                path=Path(item["path"]).name,
                zones=fmt_int(item["logical_zones"]),
                failed=fmt_int(item["failed_rows"]),
                dogi_failed=fmt_int(item["dogi_failed_rows"]),
                hybrid_failed=fmt_int(item["hybrid_failed_rows"]),
                hybrid_waf=fmt_float(item["hybrid_waf"]),
                hybrid_gc=fmt_int(item["hybrid_gc_blocks"]),
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- These rows are stronger than the easy p2000 fairness matrix: all non-QUASAR baselines complete but pay visible GC/WAF and leave stale PQC secrets.",
            "- DOGI-style remains a fair baseline because the base workloads are dynamic service-style storage traffic, not clean PQC-only epoch traces.",
            "- The result should be presented as dynamic-service pressure evidence, alongside YCSB and Sysbench pressure, not as proof that QUASAR wins on every workload.",
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
        help="actual-ZNS dynamic pressure JSON artifact; may be repeated",
    )
    parser.add_argument(
        "--dryrun",
        type=Path,
        action="append",
        default=[],
        help="tight-budget dry-run frontier JSON artifact; may be repeated",
    )
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/fast-dynamic-pressure/dynamic-pressure-summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/fast-dynamic-pressure/dynamic-pressure-summary.md"))
    args = parser.parse_args()

    dryrun_paths = args.dryrun or [
        Path("artifacts/results/fast-dynamic-pressure/dryrun-exchange-pqc8000-z404.json"),
        Path("artifacts/results/fast-dynamic-pressure/dryrun-exchange-pqc8000-z512.json"),
        Path("artifacts/results/fast-dynamic-pressure/dryrun-exchange-pqc8000-z640.json"),
        Path("artifacts/results/fast-dynamic-pressure/dryrun-exchange-pqc8000-z768.json"),
        Path("artifacts/results/fast-dynamic-pressure/dryrun-alibaba-pqc8000-z768.json"),
        Path("artifacts/results/fast-dynamic-pressure/dryrun-varmail-pqc8000-z768.json"),
    ]
    physical_paths = args.physical or [
        Path("artifacts/results/fast-dynamic-pressure/packed-physical-zonefs-exchange-pqc8000-z768-helper.json"),
        Path("artifacts/results/fast-dynamic-pressure/packed-physical-zonefs-varmail-pqc8000-z768-helper.json"),
        Path("artifacts/results/fast-dynamic-pressure/packed-physical-zonefs-alibaba-pqc8000-z768-helper.json"),
    ]
    summary = {
        "physical": [summarize_physical(path) for path in physical_paths],
        "dryrun_frontier": [summarize_dryrun(path) for path in dryrun_paths if path.exists()],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "markdown_out": str(args.markdown_out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
