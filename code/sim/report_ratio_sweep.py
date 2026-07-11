#!/usr/bin/env python3
"""Summarize the DOGI-paper-shaped PQC-ratio sweep."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def parse_workload(name: str) -> tuple[str, float]:
    if "-pqc" not in name:
        return name, -1.0
    base, raw = name.rsplit("-pqc", 1)
    return base, int(raw) / 10000.0


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def fmt_float(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.3f}"


def fmt_int(value: float | int | None) -> str:
    if value is None:
        return "N/A"
    return f"{int(value):,}"


def safe_reduction(before: float, after: float) -> float | None:
    if before <= 0:
        return None
    return (before - after) / before


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def load_pairs(path: Path) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    by_workload: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        by_workload[str(row["workload"])][str(row["policy"])] = row

    pairs = []
    for workload, policies in sorted(by_workload.items()):
        if "dogi-history" not in policies or "quasar-dogi-hybrid" not in policies:
            continue
        dogi = policies["dogi-history"]
        hybrid = policies["quasar-dogi-hybrid"]
        base, ratio = parse_workload(workload)
        best_history_waf = min(
            policies[name]["waf"]
            for name in ("sepbit-style", "midas-style", "dogi-history")
            if name in policies
        )
        pair = {
            "workload": workload,
            "base": base,
            "ratio": ratio,
            "dogi_waf": dogi["waf"],
            "hybrid_waf": hybrid["waf"],
            "best_history_waf": best_history_waf,
            "waf_reduction_vs_dogi": safe_reduction(dogi["waf"], hybrid["waf"]),
            "waf_reduction_vs_best_history": safe_reduction(best_history_waf, hybrid["waf"]),
            "dogi_gc": dogi["gc_write_blocks"],
            "hybrid_gc": hybrid["gc_write_blocks"],
            "gc_reduction_vs_dogi": safe_reduction(dogi["gc_write_blocks"], hybrid["gc_write_blocks"]),
            "dogi_p99": dogi.get("write_latency_p99_ns", 0),
            "hybrid_p99": hybrid.get("write_latency_p99_ns", 0),
            "p99_reduction_vs_dogi": safe_reduction(
                dogi.get("write_latency_p99_ns", 0),
                hybrid.get("write_latency_p99_ns", 0),
            ),
            "dogi_stale": dogi.get("stale_secret_blocks_remaining", 0),
            "hybrid_stale": hybrid.get("stale_secret_blocks_remaining", 0),
            "stale_avoided": dogi.get("stale_secret_blocks_remaining", 0)
            - hybrid.get("stale_secret_blocks_remaining", 0),
        }
        pairs.append(pair)
    return pairs


def avg(values: list[float | None]) -> float | None:
    vals = [value for value in values if value is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def summarize(pairs: list[dict]) -> dict:
    by_ratio: dict[float, list[dict]] = defaultdict(list)
    by_base: dict[str, list[dict]] = defaultdict(list)
    for pair in pairs:
        by_ratio[pair["ratio"]].append(pair)
        by_base[pair["base"]].append(pair)

    ratio_summary = []
    for ratio, rows in sorted(by_ratio.items()):
        dogi_gc = sum(row["dogi_gc"] for row in rows)
        hybrid_gc = sum(row["hybrid_gc"] for row in rows)
        ratio_summary.append(
            {
                "ratio": ratio,
                "n": len(rows),
                "avg_waf_reduction_vs_dogi": avg([row["waf_reduction_vs_dogi"] for row in rows]),
                "avg_waf_reduction_vs_best_history": avg(
                    [row["waf_reduction_vs_best_history"] for row in rows]
                ),
                "aggregate_gc_reduction_vs_dogi": safe_reduction(dogi_gc, hybrid_gc),
                "avg_p99_reduction_vs_dogi": avg([row["p99_reduction_vs_dogi"] for row in rows]),
                "stale_avoided": sum(row["stale_avoided"] for row in rows),
                "dogi_gc": dogi_gc,
                "hybrid_gc": hybrid_gc,
            }
        )

    workload_summary = []
    for base, rows in sorted(by_base.items()):
        workload_summary.append(
            {
                "workload": base,
                "n": len(rows),
                "avg_waf_reduction_vs_dogi": avg([row["waf_reduction_vs_dogi"] for row in rows]),
                "stale_avoided": sum(row["stale_avoided"] for row in rows),
            }
        )

    break_even = None
    for row in ratio_summary:
        if row["avg_waf_reduction_vs_dogi"] is not None and row["avg_waf_reduction_vs_dogi"] > 0:
            break_even = row["ratio"]
            break

    return {
        "comparison_count": len(pairs),
        "break_even_ratio": break_even,
        "ratio_summary": ratio_summary,
        "workload_summary": workload_summary,
        "pairs": pairs,
    }


def write_markdown(summary: dict, path: Path) -> None:
    ratio_rows = []
    for row in summary["ratio_summary"]:
        ratio_rows.append(
            [
                fmt_pct(row["ratio"]),
                fmt_int(row["n"]),
                fmt_pct(row["avg_waf_reduction_vs_dogi"]),
                fmt_pct(row["avg_waf_reduction_vs_best_history"]),
                fmt_pct(row["aggregate_gc_reduction_vs_dogi"]),
                fmt_pct(row["avg_p99_reduction_vs_dogi"]),
                fmt_int(row["stale_avoided"]),
            ]
        )

    workload_rows = []
    for row in summary["workload_summary"]:
        workload_rows.append(
            [
                f"`{row['workload']}`",
                fmt_int(row["n"]),
                fmt_pct(row["avg_waf_reduction_vs_dogi"]),
                fmt_int(row["stale_avoided"]),
            ]
        )

    pair_rows = []
    for row in summary["pairs"]:
        pair_rows.append(
            [
                f"`{row['workload']}`",
                fmt_float(row["dogi_waf"]),
                fmt_float(row["hybrid_waf"]),
                fmt_pct(row["waf_reduction_vs_dogi"]),
                fmt_pct(row["gc_reduction_vs_dogi"]),
                fmt_pct(row["p99_reduction_vs_dogi"]),
                fmt_int(row["stale_avoided"]),
            ]
        )

    lines = [
        "# PQC Ratio Sweep Summary",
        "",
        f"- Comparisons: {summary['comparison_count']}",
        f"- Break-even PQC ratio: {fmt_pct(summary['break_even_ratio'])}",
        "",
        "## By PQC Ratio",
        "",
        markdown_table(
            [
                "PQC Ratio",
                "N",
                "Avg WAF vs DOGI",
                "Avg WAF vs Best History",
                "Aggregate GC vs DOGI",
                "Avg p99 Latency vs DOGI",
                "Stale Secrets Avoided",
            ],
            ratio_rows,
        ),
        "",
        "## By Workload",
        "",
        markdown_table(["Workload", "N", "Avg WAF vs DOGI", "Stale Secrets Avoided"], workload_rows),
        "",
        "## Per Trace",
        "",
        markdown_table(
            [
                "Trace",
                "DOGI WAF",
                "Hybrid WAF",
                "WAF vs DOGI",
                "GC vs DOGI",
                "p99 Latency vs DOGI",
                "Stale Avoided",
            ],
            pair_rows,
        ),
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--markdown-out", type=Path, required=True)
    args = parser.parse_args()

    summary = summarize(load_pairs(args.results))
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(summary, args.markdown_out)
    print(json.dumps({k: v for k, v in summary.items() if k != "pairs"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
