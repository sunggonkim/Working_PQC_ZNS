#!/usr/bin/env python3
"""Run a multi-seed DOGI-paper-shaped PQC ratio sweep.

This is a confidence-interval companion to the larger single-seed 50k ratio
sweep. Defaults are intentionally smaller so the check can be rerun often.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_SEEDS = [53, 59, 61]
DEFAULT_RATIOS = [0.0, 0.05, 0.20]


def run_command(args: list[str]) -> None:
    print("$ " + " ".join(args))
    subprocess.run(args, check=True)


def ratio_tag(ratio: float) -> str:
    return f"pqc{int(round(ratio * 10000)):04d}"


def parse_workload(name: str) -> tuple[str, float]:
    if "-pqc" not in name:
        return name, -1.0
    base, raw = name.rsplit("-pqc", 1)
    return base, int(raw) / 10000.0


def safe_reduction(before: float, after: float) -> float | None:
    if before <= 0:
        return None
    return (before - after) / before


def mean_ci95(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "stdev": None, "ci95": None}
    mean = statistics.fmean(values)
    if len(values) == 1:
        return {"n": 1, "mean": mean, "stdev": 0.0, "ci95": 0.0}
    stdev = statistics.stdev(values)
    return {"n": len(values), "mean": mean, "stdev": stdev, "ci95": 1.96 * stdev / math.sqrt(len(values))}


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def fmt_float(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.3f}"


def fmt_ci(stat: dict[str, Any], pct: bool = False) -> str:
    mean = stat.get("mean")
    ci = stat.get("ci95")
    if mean is None or ci is None:
        return "N/A"
    if pct:
        return f"{mean * 100:.1f}% +/- {ci * 100:.1f}%"
    return f"{mean:.1f} +/- {ci:.1f}"


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def load_eval_pairs(path: Path, seed: int) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    by_workload: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        by_workload[str(row["workload"])][str(row["policy"])] = row

    pairs: list[dict[str, Any]] = []
    for workload, policies in sorted(by_workload.items()):
        dogi = policies.get("dogi-history")
        hybrid = policies.get("quasar-dogi-hybrid")
        if dogi is None or hybrid is None:
            continue
        base, ratio = parse_workload(workload)
        pair = {
            "seed": seed,
            "workload": workload,
            "base": base,
            "ratio": ratio,
            "dogi_waf": dogi["waf"],
            "hybrid_waf": hybrid["waf"],
            "waf_reduction_vs_dogi": safe_reduction(dogi["waf"], hybrid["waf"]),
            "dogi_gc": dogi["gc_write_blocks"],
            "hybrid_gc": hybrid["gc_write_blocks"],
            "gc_reduction_vs_dogi": safe_reduction(dogi["gc_write_blocks"], hybrid["gc_write_blocks"]),
            "dogi_stale": dogi.get("stale_secret_blocks_remaining", 0),
            "hybrid_stale": hybrid.get("stale_secret_blocks_remaining", 0),
            "stale_avoided": dogi.get("stale_secret_blocks_remaining", 0)
            - hybrid.get("stale_secret_blocks_remaining", 0),
        }
        pairs.append(pair)
    return pairs


def summarize(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    by_ratio: dict[float, list[dict[str, Any]]] = defaultdict(list)
    by_workload: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_seed_ratio: dict[tuple[int, float], list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        by_ratio[pair["ratio"]].append(pair)
        by_workload[pair["base"]].append(pair)
        by_seed_ratio[(pair["seed"], pair["ratio"])].append(pair)

    ratio_summary = []
    for ratio, rows in sorted(by_ratio.items()):
        seed_totals = []
        for (_seed, seed_ratio), seed_rows in sorted(by_seed_ratio.items()):
            if seed_ratio != ratio:
                continue
            seed_totals.append(sum(row["stale_avoided"] for row in seed_rows))
        ratio_summary.append(
            {
                "ratio": ratio,
                "comparisons": len(rows),
                "waf_reduction_vs_dogi": mean_ci95(
                    [row["waf_reduction_vs_dogi"] for row in rows if row["waf_reduction_vs_dogi"] is not None]
                ),
                "gc_reduction_vs_dogi": mean_ci95(
                    [row["gc_reduction_vs_dogi"] for row in rows if row["gc_reduction_vs_dogi"] is not None]
                ),
                "stale_avoided_per_seed": mean_ci95([float(value) for value in seed_totals]),
            }
        )

    workload_summary = []
    for workload, rows in sorted(by_workload.items()):
        workload_summary.append(
            {
                "workload": workload,
                "comparisons": len(rows),
                "waf_reduction_vs_dogi": mean_ci95(
                    [row["waf_reduction_vs_dogi"] for row in rows if row["waf_reduction_vs_dogi"] is not None]
                ),
                "stale_avoided": sum(row["stale_avoided"] for row in rows),
            }
        )

    break_even = None
    for row in ratio_summary:
        mean = row["waf_reduction_vs_dogi"]["mean"]
        if mean is not None and mean > 0:
            break_even = row["ratio"]
            break

    return {
        "comparison_count": len(pairs),
        "seed_count": len({row["seed"] for row in pairs}),
        "break_even_ratio": break_even,
        "ratio_summary": ratio_summary,
        "workload_summary": workload_summary,
        "pairs": pairs,
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    ratio_rows = []
    for row in summary["ratio_summary"]:
        ratio_rows.append(
            [
                fmt_pct(row["ratio"]),
                str(row["comparisons"]),
                fmt_ci(row["waf_reduction_vs_dogi"], pct=True),
                fmt_ci(row["gc_reduction_vs_dogi"], pct=True),
                fmt_ci(row["stale_avoided_per_seed"]),
            ]
        )

    workload_rows = []
    for row in summary["workload_summary"]:
        workload_rows.append(
            [
                f"`{row['workload']}`",
                str(row["comparisons"]),
                fmt_ci(row["waf_reduction_vs_dogi"], pct=True),
                f"{int(row['stale_avoided']):,}",
            ]
        )

    pair_rows = []
    for row in summary["pairs"]:
        pair_rows.append(
            [
                str(row["seed"]),
                f"`{row['workload']}`",
                fmt_float(row["dogi_waf"]),
                fmt_float(row["hybrid_waf"]),
                fmt_pct(row["waf_reduction_vs_dogi"]),
                fmt_pct(row["gc_reduction_vs_dogi"]),
                f"{int(row['stale_avoided']):,}",
            ]
        )

    lines = [
        "# Multi-Seed PQC Ratio Sweep",
        "",
        f"- Seeds: {summary['seed_count']}",
        f"- Comparisons: {summary['comparison_count']}",
        f"- Break-even PQC ratio by mean WAF reduction: {fmt_pct(summary['break_even_ratio'])}",
        "",
        "## By PQC Ratio",
        "",
        markdown_table(
            [
                "PQC Ratio",
                "N",
                "WAF vs DOGI Mean +/- 95% CI",
                "GC vs DOGI Mean +/- 95% CI",
                "Stale Avoided/Seed Mean +/- 95% CI",
            ],
            ratio_rows,
        ),
        "",
        "## By Workload",
        "",
        markdown_table(
            ["Workload", "N", "WAF vs DOGI Mean +/- 95% CI", "Total Stale Avoided"],
            workload_rows,
        ),
        "",
        "## Per Trace",
        "",
        markdown_table(
            ["Seed", "Trace", "DOGI WAF", "Hybrid WAF", "WAF vs DOGI", "GC vs DOGI", "Stale Avoided"],
            pair_rows,
        ),
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run_seed(args: argparse.Namespace, seed: int) -> Path:
    trace_dir = args.trace_root / f"seed-{seed}"
    summary_dir = args.result_root / f"seed-{seed}" / "trace-summaries"
    eval_out = args.result_root / f"seed-{seed}" / "eval.json"

    ratios = ",".join(str(value) for value in args.ratios)
    run_command(
        [
            "python3",
            "code/tracegen/generate_dogi_paper_workloads.py",
            "--events",
            str(args.events),
            "--ratios",
            ratios,
            "--out-dir",
            str(trace_dir),
            "--summary-dir",
            str(summary_dir),
            "--seed",
            str(seed),
        ]
    )
    run_command(
        [
            "python3",
            "code/sim/run_workload_suite.py",
            "--trace-dir",
            str(trace_dir),
            "--auto-zones",
            "--auto-op-ratio",
            str(args.auto_op_ratio),
            "--zone-capacity",
            str(args.zone_capacity),
            "--min-free-zones",
            str(args.min_free_zones),
            "--policies",
            "dogi-history",
            "quasar-dogi-hybrid",
            "--out",
            str(eval_out),
        ]
    )
    return eval_out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, default=DEFAULT_SEEDS)
    parser.add_argument("--ratios", nargs="+", type=float, default=DEFAULT_RATIOS)
    parser.add_argument("--events", type=int, default=10_000)
    parser.add_argument("--trace-root", type=Path, default=Path("artifacts/traces/dogi-paper-seed-sweep"))
    parser.add_argument("--result-root", type=Path, default=Path("artifacts/results/dogi-paper-seed-sweep"))
    parser.add_argument("--json-out", type=Path, default=Path("artifacts/results/dogi-paper-seed-sweep/summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/dogi-paper-seed-sweep/summary.md"))
    parser.add_argument("--auto-op-ratio", type=float, default=0.10)
    parser.add_argument("--zone-capacity", type=int, default=512)
    parser.add_argument("--min-free-zones", type=int, default=8)
    parser.add_argument("--reuse", action="store_true")
    args = parser.parse_args()

    pairs: list[dict[str, Any]] = []
    for seed in args.seeds:
        eval_out = args.result_root / f"seed-{seed}" / "eval.json"
        if not args.reuse or not eval_out.exists():
            eval_out = run_seed(args, seed)
        pairs.extend(load_eval_pairs(eval_out, seed))

    summary = summarize(pairs)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(summary, args.markdown_out)
    print(
        json.dumps(
            {
                "seed_count": summary["seed_count"],
                "comparison_count": summary["comparison_count"],
                "break_even_ratio": summary["break_even_ratio"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
