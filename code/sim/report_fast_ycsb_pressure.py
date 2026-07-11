#!/usr/bin/env python3
"""Summarize FAST/YCSB pressure experiments for QUASAR."""

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
    "epoch-oracle",
]

PHYSICAL_POLICIES = [
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


def fmt_float(value: float | None, digits: int = 4) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def fmt_int(value: int | float | None) -> str:
    return "N/A" if value is None else f"{int(value):,}"


def fmt_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def summarize_sim(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_workload: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        by_workload.setdefault(row["workload"], {})[row["policy"]] = row

    workloads: dict[str, Any] = {}
    for workload, policy_rows in sorted(by_workload.items()):
        dogi = policy_rows.get("dogi-history", {})
        hybrid = policy_rows.get("quasar-dogi-hybrid", {})
        workloads[workload] = {
            "zones": hybrid.get("zones") or dogi.get("zones"),
            "policies": {
                policy: {
                    "waf": policy_rows[policy]["waf"],
                    "gc_write_blocks": policy_rows[policy]["gc_write_blocks"],
                    "stale_secret_blocks_remaining": policy_rows[policy]["stale_secret_blocks_remaining"],
                    "epoch_impurity": policy_rows[policy]["epoch_impurity"],
                    "intent_impurity": policy_rows[policy]["intent_impurity"],
                    "zone_utilization": policy_rows[policy]["zone_utilization"],
                }
                for policy in POLICIES
                if policy in policy_rows
            },
            "hybrid_vs_dogi": {
                "waf_reduction": pct_reduction(float(dogi.get("waf", 0.0)), float(hybrid.get("waf", 0.0))),
                "gc_reduction": pct_reduction(
                    float(dogi.get("gc_write_blocks", 0)),
                    float(hybrid.get("gc_write_blocks", 0)),
                ),
                "stale_secret_reduction_blocks": int(dogi.get("stale_secret_blocks_remaining", 0))
                - int(hybrid.get("stale_secret_blocks_remaining", 0)),
            },
        }
    return workloads


def summarize_one_physical(report: dict[str, Any]) -> dict[str, Any]:
    rows = report.get("summary", {}).get("by_policy_packing", {})
    by_policy: dict[str, Any] = {}
    for policy in PHYSICAL_POLICIES:
        item = rows.get(f"{policy}::secret-group", {})
        by_policy[policy] = {
            "sim_waf": item.get("sim_waf"),
            "sim_gc_blocks": item.get("sim_gc_blocks"),
            "sim_stale_secret_blocks": item.get("sim_stale_secret_blocks"),
            "physical_reset_commands": item.get("physical_reset_commands"),
            "secret_blocks_waiting_for_physical_reset": item.get("secret_blocks_waiting_for_physical_reset"),
            "max_secret_blocks_waiting_for_physical_reset": item.get("max_secret_blocks_waiting_for_physical_reset"),
            "avg_space_utilization": item.get("avg_space_utilization"),
            "max_live_physical_zones": item.get("max_live_physical_zones"),
        }
    dogi = rows.get("dogi-history::secret-group", {})
    hybrid = rows.get("quasar-dogi-hybrid::secret-group", {})
    return {
        "scope": "representative physical packed ZNS replay",
        "traces": report.get("traces", []),
        "logical_zones": report.get("logical_zones"),
        "rows": report.get("summary", {}).get("row_count"),
        "failed_rows": report.get("summary", {}).get("failed_rows"),
        "wall_time_s": report.get("summary", {}).get("wall_time_s"),
        "append_engine": report.get("append_engine"),
        "helper_chunk_blocks": report.get("helper_chunk_blocks"),
        "total_physical_gib": sum(float(item.get("physical_bytes_written", 0)) for item in rows.values()) / (1024**3),
        "by_policy": by_policy,
        "hybrid_vs_dogi": {
            "waf_reduction": pct_reduction(float(dogi.get("sim_waf", 0.0)), float(hybrid.get("sim_waf", 0.0))),
            "gc_reduction": pct_reduction(
                float(dogi.get("sim_gc_blocks", 0)),
                float(hybrid.get("sim_gc_blocks", 0)),
            ),
            "stale_secret_reduction_blocks": int(dogi.get("sim_stale_secret_blocks", 0))
            - int(hybrid.get("sim_stale_secret_blocks", 0)),
        },
    }


def summarize_physical(paths: list[Path]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for path in paths:
        report = load_json(path)
        traces = report.get("traces", [])
        workload = Path(traces[0]).stem if traces else path.stem
        out[workload] = summarize_one_physical(report)
    return out


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# FAST/YCSB Pressure Summary",
        "",
        "This experiment answers the workload concern directly: the original DOGI-paper-shaped p2000 YCSB traces were too easy for WAF because several policies saw little or no GC. Here, YCSB-A/F are replayed with higher PQC ratios, including larger p10000 actual-ZNS checks, and tight free-zone margins.",
        "",
        "Boundary: these are DOGI-style YCSB axes with synthetic PQC metadata overlays, not the private original traces from the DOGI paper.",
        "",
        "## Simulator Sweep",
        "",
        "| Workload | Zones | DOGI WAF | Hybrid WAF | WAF Reduction | DOGI GC Blocks | Hybrid GC Blocks | GC Reduction | DOGI Stale Secrets | Hybrid Stale Secrets |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for workload, item in summary["simulator"].items():
        dogi = item["policies"]["dogi-history"]
        hybrid = item["policies"]["quasar-dogi-hybrid"]
        comparison = item["hybrid_vs_dogi"]
        lines.append(
            "| `{workload}` | {zones} | {dogi_waf} | {hybrid_waf} | {waf_red} | {dogi_gc} | {hybrid_gc} | {gc_red} | {dogi_stale} | {hybrid_stale} |".format(
                workload=workload,
                zones=item["zones"],
                dogi_waf=fmt_float(float(dogi["waf"])),
                hybrid_waf=fmt_float(float(hybrid["waf"])),
                waf_red=fmt_pct(comparison["waf_reduction"]),
                dogi_gc=fmt_int(dogi["gc_write_blocks"]),
                hybrid_gc=fmt_int(hybrid["gc_write_blocks"]),
                gc_red=fmt_pct(comparison["gc_reduction"]),
                dogi_stale=fmt_int(dogi["stale_secret_blocks_remaining"]),
                hybrid_stale=fmt_int(hybrid["stale_secret_blocks_remaining"]),
            )
        )

    lines.extend(
        [
            "",
            "## Representative Physical ZNS Replays",
            "",
        ]
    )
    for workload, item in summary["physical"].items():
        lines.extend(
            [
                f"### `{workload}`",
                "",
                f"- Rows: `{item['rows']}`, failed rows: `{item['failed_rows']}`",
                f"- Logical zones: `{item['logical_zones']}`",
                f"- Wall time: `{item['wall_time_s']:.3f}` s",
                f"- Append engine: `{item['append_engine']}`, helper chunk blocks: `{item['helper_chunk_blocks']}`",
                f"- Total physical writes: `{item['total_physical_gib']:.2f}` GiB",
                "",
                "| Policy | Sim WAF | GC Blocks | Stale Secrets | Semantic Physical Resets | Secret Waiting End | Max Secret Waiting | Avg Util | Max Live Phys Zones |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for policy in PHYSICAL_POLICIES:
            row = item["by_policy"][policy]
            lines.append(
                "| `{policy}` | {waf} | {gc} | {stale} | {resets} | {wait} | {max_wait} | {util} | {max_z} |".format(
                    policy=policy,
                    waf=fmt_float(row["sim_waf"]),
                    gc=fmt_int(row["sim_gc_blocks"]),
                    stale=fmt_int(row["sim_stale_secret_blocks"]),
                    resets=fmt_int(row["physical_reset_commands"]),
                    wait=fmt_int(row["secret_blocks_waiting_for_physical_reset"]),
                    max_wait=fmt_int(row["max_secret_blocks_waiting_for_physical_reset"]),
                    util=fmt_float(row["avg_space_utilization"], 3),
                    max_z=fmt_int(row["max_live_physical_zones"]),
                )
            )
        comparison = item["hybrid_vs_dogi"]
        lines.extend(
            [
                "",
                f"Hybrid vs DOGI-style: WAF reduction `{fmt_pct(comparison['waf_reduction'])}`, GC reduction `{fmt_pct(comparison['gc_reduction'])}`, stale secret blocks removed `{fmt_int(comparison['stale_secret_reduction_blocks'])}`.",
                "",
            ]
        )

    lines.extend(
        [
            "## Interpretation",
            "",
            "- The earlier p2000 YCSB traces were indeed too easy for WAF; YCSB-A/F pressure sweeps are necessary.",
            "- YCSB-A p4000/p6000/p8000/p10000 and YCSB-F p6000/p8000/p10000 create real WAF/GC separation. YCSB-F p4000 remains mostly a stale-secret exposure test.",
            "- The p10000 rows are important because they keep DOGI's normal YCSB locality and still show the PQC-specific gap: history baselines may keep WAF close to 1.0, but they do not make expired secrets physically resettable.",
            "- SepBIT/MiDAS-style policies can look strong on WAF while leaving many stale secret blocks, which is exactly why QUASAR should not be evaluated on WAF alone.",
            "- The deployable policy remains QUASAR-DOGI hybrid: DOGI-like history for nonsecret payload, QUASAR death-cohort placement for PQC secrets.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sim", type=Path, default=Path("artifacts/results/fast-ycsb-pressure/ycsb-pressure-op005.json"))
    parser.add_argument(
        "--physical",
        type=Path,
        action="append",
        default=[],
        help="physical packed replay JSON artifact; may be repeated",
    )
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/fast-ycsb-pressure/ycsb-pressure-summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/fast-ycsb-pressure/ycsb-pressure-summary.md"))
    args = parser.parse_args()

    physical_paths = args.physical or [
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc4000-z560-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc6000-z712-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc8000-z733-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc6000-z733-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc10000-z1024-helper.json"),
        Path("artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc10000-z900-helper.json"),
    ]
    summary = {
        "simulator": summarize_sim(load_json(args.sim)),
        "physical": summarize_physical(physical_paths),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "markdown_out": str(args.markdown_out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
