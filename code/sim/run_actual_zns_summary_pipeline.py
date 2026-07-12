#!/usr/bin/env python3
"""Regenerate the actual-ZNS comparison summaries in a stable order.

This runner is intentionally non-destructive: it does not replay traffic on the
physical ZNS device. It consumes existing actual-ZNS experiment artifacts and
regenerates the derived paper summaries, claim matrix, acceptance report, and
reproducibility manifest/hash validation.

The order matters because the reproducibility manifest hashes derived artifacts
such as acceptance/readiness/unified reports. Running the steps here keeps those
hashes stable without requiring the user to remember the dependency chain.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Step:
    name: str
    cmd: list[str]


def py(*args: str) -> list[str]:
    return [sys.executable, *args]


def pipeline_steps(*, include_tests: bool = False) -> list[Step]:
    steps = [
        Step("ycsb-pressure-curve", py("code/sim/report_ycsb_pressure_curve.py")),
        Step("fast-ycsb-pressure-summary", py("code/sim/report_fast_ycsb_pressure.py")),
        Step("fast-dynamic-pressure-summary", py("code/sim/report_fast_dynamic_pressure.py")),
        Step("workload-hardness", py("code/sim/report_workload_hardness_matrix.py")),
        Step("deployment-selector", py("code/sim/report_deployment_policy_selector.py")),
        Step("actual-zns-figures", py("code/sim/plot_actual_zns_comparison.py")),
        Step(
            "per-cohort-key-erase",
            py(
                "code/quasar/per_cohort_key_erase.py",
                "--cohorts",
                "8",
                "--records-per-cohort",
                "32",
                "--payload-bytes",
                "4096",
                "--tenants",
                "4",
                "--destroy-cohort",
                "epoch-4",
            ),
        ),
        Step("unified-report-initial", py("code/sim/report_unified_comparison.py")),
        Step("claim-matrix", py("code/sim/report_claim_matrix.py")),
        Step("unified-report-after-claims", py("code/sim/report_unified_comparison.py")),
        Step("goal-completion-audit-initial", py("code/sim/report_goal_completion_audit.py")),
        Step("reproducibility-manifest-initial", py("code/sim/report_reproducibility_manifest.py")),
        Step("reproducibility-validation-initial", py("code/sim/validate_reproducibility_manifest.py")),
        Step("acceptance-after-validation", py("code/sim/acceptance_check.py")),
        Step("dogi-exact-suite-summary", py("code/baselines/dogi_exact_suite_summary.py")),
        Step("external-readiness-after-validation", py("code/baselines/external_readiness.py")),
        Step("claim-matrix-final", py("code/sim/report_claim_matrix.py")),
        Step("unified-report-final", py("code/sim/report_unified_comparison.py")),
        Step("goal-completion-audit", py("code/sim/report_goal_completion_audit.py")),
        Step("reproducibility-manifest-final", py("code/sim/report_reproducibility_manifest.py")),
        Step("reproducibility-validation-final", py("code/sim/validate_reproducibility_manifest.py")),
    ]
    if include_tests:
        steps.append(Step("unit-tests", py("-m", "unittest", "discover", "-s", "code", "-p", "test*.py")))
    return steps


def selected_steps(steps: list[Step], only: set[str]) -> list[Step]:
    if not only:
        return steps
    known = {step.name for step in steps}
    missing = sorted(only.difference(known))
    if missing:
        raise SystemExit(f"unknown step(s): {', '.join(missing)}")
    return [step for step in steps if step.name in only]


def run_step(step: Step, *, dry_run: bool) -> dict:
    print(f"== {step.name} ==")
    print(" ".join(step.cmd))
    if dry_run:
        return {"name": step.name, "cmd": step.cmd, "returncode": None, "dry_run": True}
    proc = subprocess.run(step.cmd, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    return {"name": step.name, "cmd": step.cmd, "returncode": proc.returncode, "dry_run": False}


def write_manifest(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scope": "actual-ZNS derived-summary pipeline",
        "non_destructive": True,
        "passed": all(record["dry_run"] or record["returncode"] == 0 for record in records),
        "steps": records,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote manifest={path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-tests", action="store_true")
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("artifacts/results/actual-zns-summary-pipeline-manifest.json"),
    )
    args = parser.parse_args()

    steps = selected_steps(pipeline_steps(include_tests=args.include_tests), set(args.only))
    records = [run_step(step, dry_run=args.dry_run) for step in steps]
    write_manifest(args.manifest, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
