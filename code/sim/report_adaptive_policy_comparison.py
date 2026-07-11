#!/usr/bin/env python3
"""Summarize whether adaptive QUASAR should replace the current hybrid."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CURRENT = "quasar-dogi-hybrid"
ADAPTIVE = "quasar-adaptive-hybrid"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def fmt_float(value: float | None, digits: int = 4) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def fmt_int(value: int | float | None) -> str:
    return "N/A" if value is None else f"{int(value):,}"


def workload_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(row["workload"], {})[row["policy"]] = row
    return out


def compare_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    workloads: dict[str, Any] = {}
    current_wins = 0
    adaptive_wins = 0
    ties = 0
    for workload, policies in sorted(workload_rows(rows).items()):
        current = policies.get(CURRENT)
        adaptive = policies.get(ADAPTIVE)
        if current is None or adaptive is None:
            continue
        current_score = (
            float(current.get("waf", 99.0)),
            int(current.get("gc_write_blocks", 999999999)),
            int(current.get("stale_secret_blocks_remaining", 999999999)),
            int(current.get("quasar_family_count", 999999999)),
        )
        adaptive_score = (
            float(adaptive.get("waf", 99.0)),
            int(adaptive.get("gc_write_blocks", 999999999)),
            int(adaptive.get("stale_secret_blocks_remaining", 999999999)),
            int(adaptive.get("quasar_family_count", 999999999)),
        )
        if current_score < adaptive_score:
            winner = CURRENT
            current_wins += 1
        elif adaptive_score < current_score:
            winner = ADAPTIVE
            adaptive_wins += 1
        else:
            winner = "tie"
            ties += 1
        workloads[workload] = {
            "zones": current.get("zones"),
            "winner": winner,
            "current": {
                "waf": current.get("waf"),
                "gc_write_blocks": current.get("gc_write_blocks"),
                "stale_secret_blocks_remaining": current.get("stale_secret_blocks_remaining"),
                "quasar_family_count": current.get("quasar_family_count"),
                "zone_utilization": current.get("zone_utilization"),
            },
            "adaptive": {
                "waf": adaptive.get("waf"),
                "gc_write_blocks": adaptive.get("gc_write_blocks"),
                "stale_secret_blocks_remaining": adaptive.get("stale_secret_blocks_remaining"),
                "quasar_family_count": adaptive.get("quasar_family_count"),
                "zone_utilization": adaptive.get("zone_utilization"),
                "tenant_bin_writes": adaptive.get("quasar_tenant_bin_writes"),
                "coarse_bin_writes": adaptive.get("quasar_coarse_bin_writes"),
            },
        }
    return {
        "workloads": workloads,
        "current_wins": current_wins,
        "adaptive_wins": adaptive_wins,
        "ties": ties,
    }


def summarize(ycsb_rows: list[dict[str, Any]], sysbench_rows: list[dict[str, Any]]) -> dict[str, Any]:
    ycsb = compare_rows(ycsb_rows)
    sysbench = compare_rows(sysbench_rows)
    adaptive_wins = ycsb["adaptive_wins"] + sysbench["adaptive_wins"]
    return {
        "default_policy": CURRENT,
        "candidate_policy": ADAPTIVE,
        "decision": "keep-current-hybrid" if adaptive_wins == 0 else "investigate-adaptive",
        "decision_reason": (
            "Adaptive binning did not beat the current hybrid on WAF, GC blocks, stale-secret blocks, "
            "or family count in the current single-tenant pressure suite."
            if adaptive_wins == 0
            else "Adaptive won at least one pressure workload; inspect the workload-level rows before changing defaults."
        ),
        "ycsb_pressure": ycsb,
        "sysbench_pressure": sysbench,
    }


def section(lines: list[str], title: str, data: dict[str, Any]) -> None:
    lines.extend(
        [
            f"## {title}",
            "",
            "| Workload | Zones | Winner | Hybrid WAF | Adaptive WAF | Hybrid GC | Adaptive GC | Hybrid Stale | Adaptive Stale | Hybrid Families | Adaptive Families |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for workload, item in data["workloads"].items():
        current = item["current"]
        adaptive = item["adaptive"]
        lines.append(
            "| `{workload}` | {zones} | `{winner}` | {cwaf} | {awaf} | {cgc} | {agc} | {cstale} | {astale} | {cfam} | {afam} |".format(
                workload=workload,
                zones=fmt_int(item["zones"]),
                winner=item["winner"],
                cwaf=fmt_float(current["waf"]),
                awaf=fmt_float(adaptive["waf"]),
                cgc=fmt_int(current["gc_write_blocks"]),
                agc=fmt_int(adaptive["gc_write_blocks"]),
                cstale=fmt_int(current["stale_secret_blocks_remaining"]),
                astale=fmt_int(adaptive["stale_secret_blocks_remaining"]),
                cfam=fmt_int(current["quasar_family_count"]),
                afam=fmt_int(adaptive["quasar_family_count"]),
            )
        )
    lines.extend(
        [
            "",
            f"- Current hybrid wins: `{data['current_wins']}`",
            f"- Adaptive hybrid wins: `{data['adaptive_wins']}`",
            f"- Ties: `{data['ties']}`",
            "",
        ]
    )


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Adaptive QUASAR Policy Comparison",
        "",
        f"- Default policy: `{summary['default_policy']}`",
        f"- Candidate policy: `{summary['candidate_policy']}`",
        f"- Decision: `{summary['decision']}`",
        "",
        summary["decision_reason"],
        "",
    ]
    section(lines, "FAST/YCSB Pressure", summary["ycsb_pressure"])
    section(lines, "FAST-Style Sysbench Pressure", summary["sysbench_pressure"])
    lines.extend(
        [
            "## Interpretation",
            "",
            "- Do not switch the default to adaptive binning for the current single-tenant pressure workloads.",
            "- Keep adaptive QUASAR as an experimental knob for future multi-tenant/open-zone-budget stress.",
            "- The current deployable design remains QUASAR-DOGI hybrid with exact secret death cohorts and DOGI-style payload fallback.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ycsb",
        type=Path,
        default=Path("artifacts/results/fast-ycsb-pressure/ycsb-adaptive-comparison-op005.json"),
    )
    parser.add_argument(
        "--sysbench",
        type=Path,
        default=Path("artifacts/results/fast-db-pressure/sysbench-adaptive-comparison-op01.json"),
    )
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/adaptive-policy-comparison.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/adaptive-policy-comparison.md"))
    args = parser.parse_args()

    summary = summarize(load_json(args.ycsb), load_json(args.sysbench))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "markdown_out": str(args.markdown_out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
