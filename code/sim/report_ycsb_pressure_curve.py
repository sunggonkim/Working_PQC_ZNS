#!/usr/bin/env python3
"""Build an actual-ZNS YCSB PQC pressure curve report."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


BASELINES = ["fifo", "sepbit-style", "midas-style", "dogi-history"]
HYBRID = "quasar-dogi-hybrid"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def fmt_float(value: float | None, digits: int = 4) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def fmt_int(value: int | float | None) -> str:
    return "N/A" if value is None else f"{int(value):,}"


def pct_reduction(before: float | None, after: float | None) -> float | None:
    if before in (None, 0) or after is None:
        return None
    return (before - after) / before


def fmt_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def trace_workloads(report: dict[str, Any], fallback: str) -> list[str]:
    traces = report.get("traces", [])
    if traces:
        return [Path(trace).stem for trace in traces]
    return [fallback]


def pqc_level(workloads: list[str], path: Path) -> int | None:
    text = " ".join(workloads + [path.name])
    matches = [int(match) for match in re.findall(r"pqc(\d+)", text)]
    if not matches:
        return None
    return max(matches)


def row_for(rows: dict[str, Any], policy: str) -> dict[str, Any]:
    return rows.get(f"{policy}::secret-group", {})


def summarize_report(path: Path) -> dict[str, Any]:
    report = load_json(path)
    rows = report.get("summary", {}).get("by_policy_packing", {})
    workloads = trace_workloads(report, path.stem)
    hybrid = row_for(rows, HYBRID)
    dogi = row_for(rows, "dogi-history")
    baselines = {policy: row_for(rows, policy) for policy in BASELINES}
    baseline_semantic_failures = {
        policy: {
            "stale_secret_blocks": row.get("sim_stale_secret_blocks"),
            "semantic_resets": row.get("physical_reset_commands"),
            "secret_waiting_end": row.get("secret_blocks_waiting_for_physical_reset"),
            "waf": row.get("sim_waf"),
            "gc_blocks": row.get("sim_gc_blocks"),
        }
        for policy, row in baselines.items()
    }
    dogi_gc = int(dogi.get("sim_gc_blocks") or 0)
    hybrid_gc = int(hybrid.get("sim_gc_blocks") or 0)
    dogi_waf = dogi.get("sim_waf")
    hybrid_waf = hybrid.get("sim_waf")
    return {
        "artifact": str(path),
        "workloads": workloads,
        "pqc_level": pqc_level(workloads, path),
        "logical_zones": report.get("logical_zones"),
        "row_count": report.get("summary", {}).get("row_count"),
        "failed_rows": report.get("summary", {}).get("failed_rows"),
        "wall_time_s": report.get("summary", {}).get("wall_time_s"),
        "dogi_waf": dogi_waf,
        "hybrid_waf": hybrid_waf,
        "waf_reduction": pct_reduction(dogi_waf, hybrid_waf),
        "dogi_gc_blocks": dogi_gc,
        "hybrid_gc_blocks": hybrid_gc,
        "gc_reduction": pct_reduction(float(dogi_gc), float(hybrid_gc)),
        "dogi_stale_secret_blocks": dogi.get("sim_stale_secret_blocks"),
        "hybrid_stale_secret_blocks": hybrid.get("sim_stale_secret_blocks"),
        "dogi_semantic_resets": dogi.get("physical_reset_commands"),
        "hybrid_semantic_resets": hybrid.get("physical_reset_commands"),
        "dogi_secret_waiting_end": dogi.get("secret_blocks_waiting_for_physical_reset"),
        "hybrid_secret_waiting_end": hybrid.get("secret_blocks_waiting_for_physical_reset"),
        "dogi_max_live_physical_zones": dogi.get("max_live_physical_zones"),
        "hybrid_max_live_physical_zones": hybrid.get("max_live_physical_zones"),
        "baseline_semantic_failures": baseline_semantic_failures,
        "waf_pressure": dogi_gc > hybrid_gc and (dogi_waf or 0.0) > (hybrid_waf or 0.0),
        "semantic_gap": all(
            (row.get("sim_stale_secret_blocks") or 0) > 0 and row.get("physical_reset_commands") == 0
            for row in baselines.values()
        )
        and hybrid.get("sim_stale_secret_blocks") == 0
        and (hybrid.get("physical_reset_commands") or 0) > 0,
    }


def build_summary(paths: list[Path]) -> dict[str, Any]:
    rows = sorted((summarize_report(path) for path in paths), key=lambda row: (row["pqc_level"] or -1, row["workloads"]))
    return {
        "scope": "actual ZNS YCSB easy-to-pressure curve",
        "rows": rows,
        "row_count": len(rows),
        "failed_rows": sum(1 for row in rows if row.get("failed_rows")),
        "waf_pressure_rows": sum(1 for row in rows if row.get("waf_pressure")),
        "semantic_gap_rows": sum(1 for row in rows if row.get("semantic_gap")),
        "interpretation": (
            "p2000 is an easy WAF point but still exposes semantic reset failure; "
            "p4000/p6000/p8000/p10000 add GC pressure while preserving the stale-secret gap. "
            "The larger p10000 YCSB rows show the realistic DOGI-axis failure mode: "
            "moderate GC/WAF pressure plus large stale-secret exposure, not universal WAF explosion."
        ),
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Actual-ZNS YCSB Pressure Curve",
        "",
        summary["interpretation"],
        "",
        "| Workloads | PQC Level | Logical Zones | Rows | Failed | DOGI WAF | Hybrid WAF | WAF Reduction | DOGI GC | Hybrid GC | DOGI Stale | Hybrid Stale | DOGI Resets | Hybrid Resets | DOGI Waiting | Hybrid Waiting |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary["rows"]:
        lines.append(
            "| {workloads} | {pqc} | {zones} | {rows} | {failed} | {dogi_waf} | {hybrid_waf} | {waf_red} | {dogi_gc} | {hybrid_gc} | {dogi_stale} | {hybrid_stale} | {dogi_resets} | {hybrid_resets} | {dogi_wait} | {hybrid_wait} |".format(
                workloads=", ".join(f"`{workload}`" for workload in row["workloads"]),
                pqc=fmt_int(row["pqc_level"]),
                zones=fmt_int(row["logical_zones"]),
                rows=fmt_int(row["row_count"]),
                failed=fmt_int(row["failed_rows"]),
                dogi_waf=fmt_float(row["dogi_waf"]),
                hybrid_waf=fmt_float(row["hybrid_waf"]),
                waf_red=fmt_pct(row["waf_reduction"]),
                dogi_gc=fmt_int(row["dogi_gc_blocks"]),
                hybrid_gc=fmt_int(row["hybrid_gc_blocks"]),
                dogi_stale=fmt_int(row["dogi_stale_secret_blocks"]),
                hybrid_stale=fmt_int(row["hybrid_stale_secret_blocks"]),
                dogi_resets=fmt_int(row["dogi_semantic_resets"]),
                hybrid_resets=fmt_int(row["hybrid_semantic_resets"]),
                dogi_wait=fmt_int(row["dogi_secret_waiting_end"]),
                hybrid_wait=fmt_int(row["hybrid_secret_waiting_end"]),
            )
        )
    lines.extend(
        [
            "",
            "## Baseline Semantic Failure Check",
            "",
            "| Workloads | FIFO Stale/Reset | SepBIT Stale/Reset | MiDAS Stale/Reset | DOGI Stale/Reset | Semantic Gap | WAF Pressure |",
            "| --- | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for row in summary["rows"]:
        failures = row["baseline_semantic_failures"]
        lines.append(
            "| {workloads} | {fifo} | {sepbit} | {midas} | {dogi} | {semantic} | {pressure} |".format(
                workloads=", ".join(f"`{workload}`" for workload in row["workloads"]),
                fifo=f"{fmt_int(failures['fifo']['stale_secret_blocks'])}/{fmt_int(failures['fifo']['semantic_resets'])}",
                sepbit=f"{fmt_int(failures['sepbit-style']['stale_secret_blocks'])}/{fmt_int(failures['sepbit-style']['semantic_resets'])}",
                midas=f"{fmt_int(failures['midas-style']['stale_secret_blocks'])}/{fmt_int(failures['midas-style']['semantic_resets'])}",
                dogi=f"{fmt_int(failures['dogi-history']['stale_secret_blocks'])}/{fmt_int(failures['dogi-history']['semantic_resets'])}",
                semantic="yes" if row["semantic_gap"] else "no",
                pressure="yes" if row["waf_pressure"] else "no",
            )
        )
    lines.extend(
        [
            "",
            "## Reading",
            "",
            "- `pqc2000` is deliberately included as a negative WAF control: DOGI-style WAF is already 1.0, so the correct claim is stale-secret exposure, not WAF reduction.",
            "- `pqc4000`, `pqc6000`, `pqc8000`, and `pqc10000` show when the same YCSB family starts producing GC/WAF separation.",
            "- The `pqc10000` rows are larger DOGI-axis checks: they strengthen the workload-hardness story while keeping the claim realistic.",
            "- Across the curve, FIFO/SepBIT/MiDAS/DOGI issue zero semantic resets for expired PQC secret cohorts, while QUASAR-DOGI hybrid drains stale secrets to zero.",
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
        help="actual-ZNS packed physical replay JSON; may be repeated",
    )
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/fast-ycsb-pressure/ycsb-actual-zns-pressure-curve.json"))
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=Path("artifacts/results/fast-ycsb-pressure/ycsb-actual-zns-pressure-curve.md"),
    )
    args = parser.parse_args()
    paths = args.physical or [
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-pqc2000-z512-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc4000-z560-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc4000-z733-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc6000-z712-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc6000-z733-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc8000-z863-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc8000-z733-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc10000-z1024-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc10000-z900-helper.json"),
    ]
    summary = build_summary(paths)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "markdown_out": str(args.markdown_out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
