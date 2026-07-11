#!/usr/bin/env python3
"""Summarize FAST-style DB pressure experiments for QUASAR."""

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


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def pct_reduction(before: float, after: float) -> float | None:
    if before == 0:
        return None
    return (before - after) / before


def fmt_float(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}f}"


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
                    "write_latency_p99_ns": policy_rows[policy]["write_latency_p99_ns"],
                }
                for policy in POLICIES
                if policy in policy_rows
            },
            "hybrid_vs_dogi": {
                "waf_reduction": pct_reduction(dogi.get("waf", 0.0), hybrid.get("waf", 0.0)),
                "gc_reduction": pct_reduction(
                    float(dogi.get("gc_write_blocks", 0)),
                    float(hybrid.get("gc_write_blocks", 0)),
                ),
                "stale_secret_reduction_blocks": int(dogi.get("stale_secret_blocks_remaining", 0))
                - int(hybrid.get("stale_secret_blocks_remaining", 0)),
            },
        }
    return workloads


def summarize_physical(report: dict[str, Any]) -> dict[str, Any]:
    rows = report.get("summary", {}).get("by_policy_packing", {})
    items: dict[str, Any] = {}
    for key in [
        "fifo::secret-group",
        "sepbit-style::secret-group",
        "midas-style::secret-group",
        "dogi-history::secret-group",
        "quasar::secret-group",
        "quasar-dogi-hybrid::group",
        "quasar-dogi-hybrid::secret-group",
    ]:
        item = rows.get(key, {})
        items[key] = {
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
        "rows": report.get("summary", {}).get("row_count"),
        "failed_rows": report.get("summary", {}).get("failed_rows"),
        "wall_time_s": report.get("summary", {}).get("wall_time_s"),
        "append_engine": report.get("append_engine"),
        "helper_chunk_blocks": report.get("helper_chunk_blocks"),
        "total_physical_gib": sum(
            float(item.get("physical_bytes_written", 0)) for item in rows.values()
        )
        / (1024**3),
        "by_policy_packing": items,
        "hybrid_vs_dogi_secret_group": {
            "waf_reduction": pct_reduction(float(dogi.get("sim_waf", 0.0)), float(hybrid.get("sim_waf", 0.0))),
            "gc_reduction": pct_reduction(
                float(dogi.get("sim_gc_blocks", 0)),
                float(hybrid.get("sim_gc_blocks", 0)),
            ),
            "stale_secret_reduction_blocks": int(dogi.get("sim_stale_secret_blocks", 0))
            - int(hybrid.get("sim_stale_secret_blocks", 0)),
        },
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# FAST-Style DB Pressure Summary",
        "",
        "This is a Sysbench-OLTP-like DB stress profile. It is not a DOGI paper workload; DOGI uses FIO Zipf, YCSB-A/F, Varmail, Alibaba, and Exchange. The point of this profile is to test a common FAST-style DB overwrite workload with PQC authentication metadata and short cryptographic epochs.",
        "",
        "## Simulator",
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

    physical = summary["physical"]
    rows = physical["by_policy_packing"]
    lines.extend(
        [
            "",
            "## Physical ZNS Packed Replay",
            "",
            f"- Rows: `{physical['rows']}`",
            f"- Failed rows: `{physical['failed_rows']}`",
            f"- Wall time: `{physical['wall_time_s']:.3f}` s",
            f"- Append engine: `{physical['append_engine']}`",
            f"- Helper chunk blocks: `{physical['helper_chunk_blocks']}`",
            f"- Total physical writes: `{physical['total_physical_gib']:.2f}` GiB",
            "",
            "| Policy / Packing | Sim WAF | GC Blocks | Stale Secrets | Semantic Physical Resets | Secret Waiting End | Max Secret Waiting | Avg Util | Max Live Phys Zones |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for key in [
        "fifo::secret-group",
        "sepbit-style::secret-group",
        "midas-style::secret-group",
        "dogi-history::secret-group",
        "quasar::secret-group",
        "quasar-dogi-hybrid::secret-group",
        "quasar-dogi-hybrid::group",
    ]:
        item = rows[key]
        lines.append(
            "| `{key}` | {waf} | {gc} | {stale} | {resets} | {wait} | {max_wait} | {util} | {max_z} |".format(
                key=key,
                waf=fmt_float(float(item["sim_waf"])),
                gc=fmt_int(item["sim_gc_blocks"]),
                stale=fmt_int(item["sim_stale_secret_blocks"]),
                resets=fmt_int(item["physical_reset_commands"]),
                wait=fmt_int(item["secret_blocks_waiting_for_physical_reset"]),
                max_wait=fmt_int(item["max_secret_blocks_waiting_for_physical_reset"]),
                util=fmt_float(float(item["avg_space_utilization"]), 3),
                max_z=fmt_int(item["max_live_physical_zones"]),
            )
        )

    comparison = physical["hybrid_vs_dogi_secret_group"]
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This workload is intentionally harder than the earlier DOGI-paper-shaped p2000 replay: it is update-heavy, DB-like, and PQC-heavy enough for lifetime placement to affect GC.",
            f"- In the physical packed replay, QUASAR-DOGI hybrid reduces DOGI-style GC blocks by `{fmt_pct(comparison['gc_reduction'])}` and removes `{fmt_int(comparison['stale_secret_reduction_blocks'])}` stale secret blocks.",
            "- The result should be used as a pressure/stress figure, not as a claim that DOGI itself evaluated Sysbench.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sim", type=Path, default=Path("artifacts/results/fast-db-pressure/sysbench-oltp-p20-p40-op01.json"))
    parser.add_argument(
        "--physical",
        type=Path,
        default=Path("artifacts/results/fast-db-pressure/packed-physical-zonefs-sysbench-p20-p40-z404-helper.json"),
    )
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/fast-db-pressure/sysbench-pressure-summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/fast-db-pressure/sysbench-pressure-summary.md"))
    args = parser.parse_args()

    summary = {
        "simulator": summarize_sim(load_json(args.sim)),
        "physical": summarize_physical(load_json(args.physical)),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "markdown_out": str(args.markdown_out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
