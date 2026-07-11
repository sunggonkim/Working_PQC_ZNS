#!/usr/bin/env python3
"""Summarize exact public DOGI prototype placement runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_RUNS = {
    "DOGI": Path("artifacts/results/dogi-exact/alibaba-pqc8000-dogi.json"),
    "Greedy": Path("artifacts/results/dogi-exact/alibaba-pqc8000-greedy.json"),
    "CostBenefit": Path("artifacts/results/dogi-exact/alibaba-pqc8000-costbenefit.json"),
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def fmt_float(value: float | None, digits: int = 3) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def summarize(runs: dict[str, Path]) -> dict[str, Any]:
    rows = []
    for name, path in runs.items():
        data = load_json(path)
        rows.append(
            {
                "placement": name,
                "path": str(path),
                "completed": data.get("completed"),
                "waf": data.get("waf"),
                "user_write_gib": data.get("user_write_gib"),
                "gc_write_gib": data.get("gc_write_gib"),
                "trace_path": data.get("trace_path"),
                "placement_algorithm": data.get("placement_algorithm"),
                "selection_algorithm": data.get("selection_algorithm"),
                "saw_zenfs_mount": data.get("saw_zenfs_mount"),
            }
        )
    completed = [row for row in rows if row.get("completed")]
    best = min(completed, key=lambda row: float(row["waf"])) if completed else None
    dogi = next((row for row in rows if row["placement"] == "DOGI"), {})
    return {
        "scope": "exact public DOGI prototype placement variants on physical ZNS",
        "trace": dogi.get("trace_path") or (rows[0].get("trace_path") if rows else None),
        "device": "/dev/nvme0n1",
        "logical_size_gb": 2,
        "scheduler": "mq-deadline",
        "completed_runs": len(completed),
        "total_runs": len(rows),
        "best_placement": best["placement"] if best else None,
        "best_waf": best["waf"] if best else None,
        "dogi_waf": dogi.get("waf"),
        "rows": rows,
        "caveat": (
            "These are public DOGI prototype internal GiB counters on a compacted trace. "
            "They are exact DOGI-stack evidence but should not be mixed as apples-to-apples "
            "numbers with QUASAR's packed replay metrics."
        ),
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Exact Public DOGI Prototype Suite",
        "",
        f"- Scope: {summary['scope']}",
        f"- Trace: `{summary['trace']}`",
        f"- Device: `{summary['device']}`",
        f"- Logical size: `{summary['logical_size_gb']} GiB`",
        f"- Scheduler: `{summary['scheduler']}`",
        f"- Completed runs: `{summary['completed_runs']}/{summary['total_runs']}`",
        f"- Best placement: `{summary['best_placement']}`, WAF `{fmt_float(summary['best_waf'])}`",
        "",
        "| Placement | Completed | WAF | UserWrite GiB | GCWrite GiB | Selection | ZenFS Mount |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for row in summary["rows"]:
        lines.append(
            "| `{placement}` | {completed} | {waf} | {user} | {gc} | `{selection}` | {zenfs} |".format(
                placement=row["placement"],
                completed=str(bool(row["completed"])).lower(),
                waf=fmt_float(row["waf"]),
                user=fmt_float(row["user_write_gib"]),
                gc=fmt_float(row["gc_write_gib"]),
                selection=row["selection_algorithm"],
                zenfs=str(bool(row["saw_zenfs_mount"])).lower(),
            )
        )
    lines.extend(["", "Caveat:", "", f"> {summary['caveat']}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/dogi-exact/alibaba-pqc8000-suite.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/dogi-exact/alibaba-pqc8000-suite.md"))
    args = parser.parse_args()
    summary = summarize(DEFAULT_RUNS)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "completed": summary["completed_runs"]}, sort_keys=True))
    return 0 if summary["completed_runs"] == summary["total_runs"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
