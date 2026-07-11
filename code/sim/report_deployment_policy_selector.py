#!/usr/bin/env python3
"""Build a deployable QUASAR policy selector from measured artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def fmt_float(value: float | None, digits: int = 4) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def fmt_int(value: int | float | None) -> str:
    return "N/A" if value is None else f"{int(value):,}"


def current_hybrid_evidence(adaptive: dict[str, Any]) -> dict[str, Any]:
    ycsb = adaptive.get("ycsb_pressure", {})
    sysbench = adaptive.get("sysbench_pressure", {})
    current_wins = int(ycsb.get("current_wins", 0)) + int(sysbench.get("current_wins", 0))
    adaptive_wins = int(ycsb.get("adaptive_wins", 0)) + int(sysbench.get("adaptive_wins", 0))
    return {
        "mode": "default",
        "policy": "quasar-dogi-hybrid",
        "when": "single-tenant or normal PQC pressure without tenant isolation requirement",
        "rule": "Use exact PQC death-cohort placement for secrets and DOGI-style fallback for payload.",
        "passed": adaptive.get("decision") == "keep-current-hybrid" and current_wins >= 6 and adaptive_wins == 0,
        "evidence": {
            "adaptive_decision": adaptive.get("decision"),
            "current_wins": current_wins,
            "adaptive_wins": adaptive_wins,
            "ycsb_workloads": len(ycsb.get("workloads", {})),
            "sysbench_workloads": len(sysbench.get("workloads", {})),
        },
    }


def tenant_isolation_evidence(multitenant: dict[str, Any]) -> dict[str, Any]:
    comparison = multitenant.get("physical", {}).get("tenant_isolation_vs_current", {})
    return {
        "mode": "tenant-isolation",
        "policy": "quasar-adaptive-hybrid tenant-local bins",
        "when": "multi-tenant secret reset must not mix tenant cohorts",
        "rule": "Add tenant-local death-cohort bins only when reset-time tenant impurity is a security/isolation concern.",
        "passed": (
            multitenant.get("decision") == "add-tenant-isolation-mode"
            and comparison.get("reset_secret_tenant_impurity_reduction", 0.0) >= 1.0
        ),
        "evidence": {
            "decision": multitenant.get("decision"),
            "waf_increase": comparison.get("waf_increase"),
            "gc_extra_blocks": comparison.get("gc_extra_blocks"),
            "physical_reset_extra_commands": comparison.get("physical_reset_extra_commands"),
            "reset_secret_tenant_impurity_reduction": comparison.get("reset_secret_tenant_impurity_reduction"),
        },
    }


def residual_profile_evidence(residual: dict[str, Any]) -> dict[str, Any]:
    decisions = residual.get("controller_decisions", [])
    by_profile: dict[str, list[dict[str, Any]]] = {}
    for row in decisions:
        by_profile.setdefault(row.get("profile", ""), []).append(row)
    strict_rows = by_profile.get("strict_zero_wait", [])
    selected_strict = [row.get("selected", {}) for row in strict_rows if row.get("selected")]
    zero_wait_count = sum(1 for row in selected_strict if row.get("secret_waiting_end") == 0)
    max_waf = max((float(row.get("physical_waf", 0.0)) for row in selected_strict), default=0.0)
    return {
        "mode": "strict-residual",
        "policy": "epoch-bin residual-migration controller",
        "when": "delayed expiry or stragglers would otherwise leave secret bytes waiting",
        "rule": "Select low-overhead, balanced, or strict-zero-wait residual budget based on exposure objective.",
        "passed": bool(strict_rows) and zero_wait_count >= 3 and max_waf >= 3.0,
        "evidence": {
            "decision": residual.get("decision"),
            "profiles": [profile.get("profile") for profile in residual.get("controller_profiles", [])],
            "strict_zero_wait_rows": len(strict_rows),
            "strict_zero_wait_successes": zero_wait_count,
            "strict_zero_wait_max_waf": max_waf,
        },
    }


def bad_hint_evidence(robustness: dict[str, Any]) -> dict[str, Any]:
    missing = robustness.get("missing_hint_5pct", {})
    wrong = robustness.get("wrong_epoch_5pct", {})
    fallback = robustness.get("straggler_5pct_epoch_bin_5_residual_12288", {})
    return {
        "mode": "fallback-overflow",
        "policy": "overflow and conservative reset confirmation",
        "when": "hint confidence is low, missing, or inconsistent",
        "rule": "Route uncertain data away from exact secret zones and reset only after epoch-manager confirmation.",
        "passed": (
            missing.get("failed_rows", 1) == 0
            and wrong.get("failed_rows", 1) == 0
            and fallback.get("failed_rows", 1) == 0
        ),
        "evidence": {
            "missing_hint_failed_rows": missing.get("failed_rows"),
            "wrong_epoch_failed_rows": wrong.get("failed_rows"),
            "fallback_failed_rows": fallback.get("failed_rows"),
            "fallback_secret_waiting_end": fallback.get("hybrid", {}).get("secret_waiting_end"),
            "fallback_physical_waf": fallback.get("hybrid", {}).get("physical_waf"),
        },
    }


def summarize(
    adaptive: dict[str, Any],
    multitenant: dict[str, Any],
    residual: dict[str, Any],
    robustness: dict[str, Any],
    hardness: dict[str, Any],
) -> dict[str, Any]:
    modes = [
        current_hybrid_evidence(adaptive),
        tenant_isolation_evidence(multitenant),
        residual_profile_evidence(residual),
        bad_hint_evidence(robustness),
    ]
    return {
        "scope": "QUASAR deployment policy selector derived from actual-ZNS and simulator pressure artifacts",
        "passed": all(mode["passed"] for mode in modes) and hardness.get("passed", False),
        "passed_modes": sum(1 for mode in modes if mode["passed"]),
        "total_modes": len(modes),
        "hardness_passed": hardness.get("passed"),
        "default_policy": "quasar-dogi-hybrid",
        "modes": modes,
        "selector": [
            {
                "condition": "tenant isolation required",
                "select": "tenant-isolation",
                "otherwise": "continue",
            },
            {
                "condition": "strict zero stale-secret waiting required under stragglers",
                "select": "strict-residual",
                "otherwise": "continue",
            },
            {
                "condition": "hint confidence is low or missing",
                "select": "fallback-overflow",
                "otherwise": "continue",
            },
            {
                "condition": "normal single-tenant PQC pressure",
                "select": "default",
                "otherwise": "default",
            },
        ],
        "main_takeaway": (
            "The improved deployable design is not a single universal knob. The default remains "
            "QUASAR-DOGI hybrid; tenant isolation and residual migration are explicit modes enabled "
            "only when the workload/security objective requires their overhead."
        ),
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# QUASAR Deployment Policy Selector",
        "",
        summary["main_takeaway"],
        "",
        f"- Passed modes: `{summary['passed_modes']}/{summary['total_modes']}`",
        f"- Workload hardness passed: `{summary['hardness_passed']}`",
        f"- Default policy: `{summary['default_policy']}`",
        "",
        "## Selector",
        "",
        "| Condition | Select | Else |",
        "| --- | --- | --- |",
    ]
    for rule in summary["selector"]:
        lines.append(f"| {rule['condition']} | `{rule['select']}` | {rule['otherwise']} |")
    lines.extend(
        [
            "",
            "## Modes",
            "",
            "| Mode | Policy | Pass | When | Rule | Key Evidence |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for mode in summary["modes"]:
        evidence = "<br>".join(f"- `{key}`: {value}" for key, value in mode["evidence"].items())
        lines.append(
            "| {mode} | `{policy}` | `{passed}` | {when} | {rule} | {evidence} |".format(
                mode=mode["mode"],
                policy=mode["policy"],
                passed="yes" if mode["passed"] else "no",
                when=mode["when"],
                rule=mode["rule"],
                evidence=evidence,
            )
        )
    lines.extend(
        [
            "",
            "## Paper Positioning",
            "",
            "- Do not present adaptive binning as the default: it loses to the current hybrid on the measured single-tenant pressure suite.",
            "- Present tenant isolation as an optional security/isolation mode with measured WAF/reset overhead.",
            "- Present residual migration as an exposure objective knob, not as a free optimization.",
            "- Keep DOGI-style placement for payload; QUASAR supplies the missing PQC death-cohort signal.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adaptive", type=Path, default=Path("artifacts/results/adaptive-policy-comparison.json"))
    parser.add_argument(
        "--multitenant",
        type=Path,
        default=Path("artifacts/results/multitenant-pressure/multitenant-pressure-summary.json"),
    )
    parser.add_argument("--residual", type=Path, default=Path("artifacts/results/residual-fallback-sweep/summary.json"))
    parser.add_argument(
        "--robustness",
        type=Path,
        default=Path("artifacts/results/physical-robustness-ycsb-a-pqc4000/summary.json"),
    )
    parser.add_argument("--hardness", type=Path, default=Path("artifacts/results/workload-hardness-matrix.json"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/quasar-deployment-policy-selector.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/quasar-deployment-policy-selector.md"))
    args = parser.parse_args()

    summary = summarize(
        load_json(args.adaptive),
        load_json(args.multitenant),
        load_json(args.residual),
        load_json(args.robustness),
        load_json(args.hardness),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "passed": summary["passed"]}, sort_keys=True))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
