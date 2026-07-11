#!/usr/bin/env python3
"""Summarize DOGI-paper-shaped workload-suite results."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


KEY_POLICIES = ["midas-style", "dogi-history", "quasar", "quasar-dogi-hybrid"]


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def ratio_tag_from_workload(workload: str) -> tuple[str, str]:
    if "-pqc" not in workload:
        return workload, "unknown"
    name, raw = workload.rsplit("-pqc", 1)
    try:
        ratio = int(raw) / 10000.0
        return name, f"{ratio:.2%}"
    except ValueError:
        return name, "unknown"


def fmt_float(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def fmt_pct(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def fmt_int(value: int | float) -> str:
    return f"{int(value):,}"


def markdown_table(header: list[str], body: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def build_summary(rows: list[dict]) -> tuple[dict, str]:
    grouped: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        grouped[row["workload"]][row["policy"]] = row

    table = []
    improvements = []
    by_ratio: dict[str, list[float]] = defaultdict(list)
    by_workload: dict[str, list[float]] = defaultdict(list)
    stale_reductions = []

    for workload in sorted(grouped):
        base_name, ratio = ratio_tag_from_workload(workload)
        policies = grouped[workload]
        dogi = policies.get("dogi-history")
        hybrid = policies.get("quasar-dogi-hybrid")
        quasar = policies.get("quasar")
        midas = policies.get("midas-style")
        if not dogi or not hybrid:
            continue
        reduction = (dogi["waf"] - hybrid["waf"]) / dogi["waf"]
        improvements.append(reduction)
        by_ratio[ratio].append(reduction)
        by_workload[base_name].append(reduction)
        stale_reduction = dogi["stale_secret_blocks_remaining"] - hybrid["stale_secret_blocks_remaining"]
        stale_reductions.append(stale_reduction)
        best_history = min(
            [row for row in [midas, dogi] if row is not None],
            key=lambda row: row["waf"],
        )
        best_reduction = (best_history["waf"] - hybrid["waf"]) / best_history["waf"]
        table.append(
            [
                f"`{base_name}`",
                ratio,
                fmt_float(midas["waf"]) if midas else "N/A",
                fmt_float(dogi["waf"]),
                fmt_float(quasar["waf"]) if quasar else "N/A",
                fmt_float(hybrid["waf"]),
                fmt_pct(reduction),
                fmt_pct(best_reduction),
                fmt_int(dogi["stale_secret_blocks_remaining"]),
                fmt_int(hybrid["stale_secret_blocks_remaining"]),
            ]
        )

    ratio_rows = []
    for ratio in sorted(by_ratio, key=lambda item: float(item.strip("%")) if item != "unknown" else -1):
        vals = by_ratio[ratio]
        ratio_rows.append([ratio, fmt_pct(sum(vals) / len(vals)), fmt_int(len(vals))])

    workload_rows = []
    for workload in sorted(by_workload):
        vals = by_workload[workload]
        workload_rows.append([f"`{workload}`", fmt_pct(sum(vals) / len(vals)), fmt_int(len(vals))])

    summary = {
        "workload_count": len(grouped),
        "comparison_count": len(improvements),
        "avg_hybrid_waf_reduction_vs_dogi": sum(improvements) / max(1, len(improvements)),
        "max_hybrid_waf_reduction_vs_dogi": max(improvements) if improvements else 0.0,
        "min_hybrid_waf_reduction_vs_dogi": min(improvements) if improvements else 0.0,
        "total_stale_secret_blocks_avoided_vs_dogi": sum(stale_reductions),
        "avg_by_ratio": {
            ratio: sum(vals) / len(vals)
            for ratio, vals in sorted(by_ratio.items())
        },
        "avg_by_workload": {
            workload: sum(vals) / len(vals)
            for workload, vals in sorted(by_workload.items())
        },
    }

    md = [
        "# DOGI-Paper Workload Suite Summary",
        "",
        "This suite is DOGI-paper-shaped, not a claim of exact reproduction for private YCSB/Varmail/Alibaba/Exchange traces.",
        "",
        f"- Comparisons: {summary['comparison_count']}",
        f"- Average WAF reduction of `quasar-dogi-hybrid` vs `dogi-history`: {fmt_pct(summary['avg_hybrid_waf_reduction_vs_dogi'])}",
        f"- Range vs `dogi-history`: {fmt_pct(summary['min_hybrid_waf_reduction_vs_dogi'])} to {fmt_pct(summary['max_hybrid_waf_reduction_vs_dogi'])}",
        f"- Stale secret blocks avoided vs `dogi-history`: {fmt_int(summary['total_stale_secret_blocks_avoided_vs_dogi'])}",
        "",
        "## Per Workload And PQC Ratio",
        "",
        markdown_table(
            [
                "Workload",
                "PQC Ratio",
                "MiDAS WAF",
                "DOGI WAF",
                "Plain QUASAR WAF",
                "Hybrid WAF",
                "Hybrid vs DOGI",
                "Hybrid vs Best History",
                "DOGI Stale Secrets",
                "Hybrid Stale Secrets",
            ],
            table,
        ),
        "",
        "## Average By PQC Ratio",
        "",
        markdown_table(["PQC Ratio", "Avg Hybrid vs DOGI", "N"], ratio_rows),
        "",
        "## Average By DOGI Workload Axis",
        "",
        markdown_table(["Workload", "Avg Hybrid vs DOGI", "N"], workload_rows),
        "",
    ]
    return summary, "\n".join(md)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=Path("artifacts/results/dogi-paper-workloads/eval.json"))
    parser.add_argument("--json-out", type=Path, default=Path("artifacts/results/dogi-paper-workloads/summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/dogi-paper-workloads/summary.md"))
    args = parser.parse_args()

    rows = load_json(args.results)
    summary, markdown = build_summary(rows)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown, encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
