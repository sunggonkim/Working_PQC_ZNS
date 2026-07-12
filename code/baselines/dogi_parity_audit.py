#!/usr/bin/env python3
"""Build a reviewer-facing audit of public DOGI parity evidence.

The paper uses same-path DOGI-style placement for apples-to-apples replay, but
also keeps exact public DOGI prototype runs separate.  This audit makes that
boundary explicit so the result cannot be presented as an exact end-to-end
QUASAR-vs-DOGI comparison unless the exact-stack parity gaps are closed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_INPUTS = {
    "nullblk": Path("artifacts/results/dogi-nullblk-full-run.json"),
    "compact_suite": Path("artifacts/results/dogi-physical-zns-full-pqc2000-compact-lg2/summary.json"),
    "dynamic_dogi": Path("artifacts/results/dogi-exact/alibaba-pqc8000-dogi.json"),
    "dynamic_suite": Path("artifacts/results/dogi-exact/alibaba-pqc8000-suite.json"),
    "original_lba_run": Path("artifacts/results/dogi-exact/alibaba-pqc8000-original-lba-dogi-cwd-app.json"),
    "original_lba_adapter": Path("artifacts/results/fast-dynamic-pressure/alibaba-pqc8000-original-lba-dogi-adapter.json"),
    "original_lba_preflight": Path(
        "artifacts/results/fast-dynamic-pressure/alibaba-pqc8000-original-lba-dogi-preflight-nvme0n1.json"
    ),
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def fmt_float(value: Any, digits: int = 3) -> str:
    return "N/A" if value is None else f"{float(value):.{digits}f}"


def row_completed(row: dict[str, Any]) -> bool:
    return bool(row.get("completed") and row.get("saw_zenfs_mount") and row.get("waf", 0) > 1.0)


def audit(inputs: dict[str, Path]) -> dict[str, Any]:
    data = {name: load_json(path) for name, path in inputs.items()}
    nullblk = data["nullblk"]
    compact_suite = data["compact_suite"]
    dynamic_dogi = data["dynamic_dogi"]
    dynamic_suite = data["dynamic_suite"]
    original_lba_run = data["original_lba_run"]
    original_lba_adapter = data["original_lba_adapter"]
    original_lba_preflight = data["original_lba_preflight"]

    compact_rows = compact_suite.get("rows", [])
    dynamic_rows = dynamic_suite.get("rows", [])
    evidence = [
        {
            "name": "nullblk_zenfs_dogi",
            "passed": bool(
                nullblk.get("completed")
                and nullblk.get("saw_zenfs_mount")
                and nullblk.get("saw_dogi_select")
                and nullblk.get("saw_mlp_status")
            ),
            "waf": nullblk.get("waf"),
            "scope": "public DOGI prototype on null_blk/ZenFS",
        },
        {
            "name": "six_workload_physical_compact",
            "passed": bool(
                compact_suite.get("completed")
                and compact_suite.get("workloads", 0) >= 6
                and all(row.get("saw_dogi_select") and row_completed(row) for row in compact_rows)
            ),
            "waf": compact_suite.get("aggregate_waf"),
            "scope": "public DOGI prototype on physical ZNS over six DOGI-shaped compact traces",
        },
        {
            "name": "dynamic_pressure_dogi",
            "passed": bool(dynamic_dogi.get("saw_dogi_select") and row_completed(dynamic_dogi)),
            "waf": dynamic_dogi.get("waf"),
            "scope": "public DOGI prototype on Alibaba-like p8000 compact pressure trace",
        },
        {
            "name": "dynamic_pressure_selector_suite",
            "passed": bool(
                dynamic_suite.get("completed_runs") == dynamic_suite.get("total_runs")
                and dynamic_suite.get("total_runs", 0) >= 3
                and all(row_completed(row) for row in dynamic_rows)
            ),
            "waf": dynamic_suite.get("best_waf"),
            "scope": "public DOGI prototype DOGI/Greedy/CostBenefit selector variants",
        },
        {
            "name": "original_lba_dynamic_dogi",
            "passed": bool(
                original_lba_run.get("saw_dogi_select")
                and row_completed(original_lba_run)
                and original_lba_adapter.get("logical_size_gb", 0) >= 40
                and original_lba_preflight.get("trace", {}).get("all_lines_usable")
            ),
            "waf": original_lba_run.get("waf"),
            "scope": "public DOGI prototype on original-LBA Alibaba-like p8000 span",
        },
    ]
    passed = sum(1 for item in evidence if item["passed"])
    total = len(evidence)
    return {
        "audit_status": "substantial-direct-evidence-not-full-parity" if passed == total else "incomplete",
        "passed_evidence": passed,
        "total_evidence": total,
        "fatal_if_overclaimed": True,
        "reviewer_answer": (
            "The headline same-path DOGI-style baseline is not the public DOGI prototype. "
            "The paper therefore keeps exact public DOGI evidence separate: null_blk/ZenFS, "
            "six compact physical-ZNS workloads, a dynamic p8000 pressure run, selector variants, "
            "and an original-LBA p8000 run all complete. This is substantial direct evidence, "
            "but not full end-to-end parity with QUASAR's packed replay."
        ),
        "paper_rule": (
            "Use same-path baselines for apples-to-apples QUASAR/FIFO/SepBIT/MiDAS/DOGI-style replay. "
            "Use exact public DOGI runs only as sanity evidence and never unit-mix their internal GiB "
            "counters with packed-ZNS replay WAF or latency."
        ),
        "remaining_parity_gaps": [
            "QUASAR is not implemented inside the public DOGI/ZenFS stack.",
            "The exact public DOGI counters and QUASAR packed-replay counters use different units and stack boundaries.",
            "Compact-LBA DOGI runs are feasibility evidence; the original-LBA run exists for one hard dynamic trace only.",
            "A full production comparison would need the same app/ZenFS/SPDK path for DOGI and QUASAR.",
        ],
        "evidence": evidence,
        "sources": {name: str(path) for name, path in inputs.items()},
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Public DOGI Parity Audit",
        "",
        f"- Status: `{summary['audit_status']}`",
        f"- Evidence passed: `{summary['passed_evidence']}/{summary['total_evidence']}`",
        f"- Fatal if overclaimed: `{str(summary['fatal_if_overclaimed']).lower()}`",
        "",
        summary["reviewer_answer"],
        "",
        "Paper rule:",
        "",
        f"> {summary['paper_rule']}",
        "",
        "| Evidence | Passed | WAF | Scope |",
        "| --- | ---: | ---: | --- |",
    ]
    for item in summary["evidence"]:
        lines.append(
            f"| `{item['name']}` | `{str(item['passed']).lower()}` | {fmt_float(item['waf'])} | {item['scope']} |"
        )
    lines.extend(["", "Remaining parity gaps:", ""])
    for gap in summary["remaining_parity_gaps"]:
        lines.append(f"- {gap}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/dogi-public-parity-audit.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/dogi-public-parity-audit.md"))
    args = parser.parse_args()
    summary = audit(DEFAULT_INPUTS)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "status": summary["audit_status"]}, sort_keys=True))
    return 0 if summary["passed_evidence"] == summary["total_evidence"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
