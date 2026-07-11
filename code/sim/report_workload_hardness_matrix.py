#!/usr/bin/env python3
"""Report whether the QUASAR workload suite is fair, hard, and hostile enough.

This report answers a specific reviewer concern: a clean PQC-only trace is too
easy, and low-pressure DOGI-shaped traces can make every policy look good on
WAF. The matrix separates negative controls, pressure workloads, and
QUASAR-hostile workloads so that the paper does not overclaim one axis.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def ycsb_negative_control(ycsb_curve: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in ycsb_curve.get("rows", []) if row.get("pqc_level") == 2000]
    row = rows[0] if rows else {}
    passed = bool(
        row
        and not row.get("waf_pressure", True)
        and row.get("semantic_gap", False)
        and row.get("dogi_gc_blocks", 1) == 0
        and row.get("hybrid_gc_blocks", 1) == 0
        and row.get("dogi_stale_secret_blocks", 0) > 0
        and row.get("hybrid_stale_secret_blocks", 1) == 0
    )
    return {
        "name": "YCSB p2000 negative WAF control",
        "tier": "negative-control",
        "passed": passed,
        "purpose": "Prove that easy DOGI-axis workloads are not WAF stress tests.",
        "evidence": {
            "workloads": row.get("workloads", []),
            "dogi_waf": row.get("dogi_waf"),
            "hybrid_waf": row.get("hybrid_waf"),
            "dogi_gc_blocks": row.get("dogi_gc_blocks"),
            "hybrid_gc_blocks": row.get("hybrid_gc_blocks"),
            "dogi_stale_secret_blocks": row.get("dogi_stale_secret_blocks"),
            "hybrid_stale_secret_blocks": row.get("hybrid_stale_secret_blocks"),
            "hybrid_semantic_resets": row.get("hybrid_semantic_resets"),
        },
        "paper_use": "Use as an honest negative control: WAF does not separate, but semantic reset does.",
    }


def dogi_favorable_control(eval_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Check that history-aware placement wins when there is no PQC signal.

    A fair QUASAR story should not claim that QUASAR is universally best. On
    DOGI-shaped traces with `pqc0000`, there is no cryptographic death cohort
    to exploit. In that regime, DOGI-style history placement and the
    QUASAR-DOGI hybrid should beat FIFO/pure-QUASAR on ordinary WAF.
    """

    by_workload: dict[str, dict[str, dict[str, Any]]] = {}
    for row in eval_rows:
        workload = str(row.get("workload", ""))
        if not workload.endswith("pqc0000"):
            continue
        by_workload.setdefault(workload, {})[str(row.get("policy"))] = row

    wins: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for workload, policies in sorted(by_workload.items()):
        dogi = policies.get("dogi-history")
        hybrid = policies.get("quasar-dogi-hybrid")
        fifo = policies.get("fifo")
        pure = policies.get("quasar")
        if not all([dogi, hybrid, fifo, pure]):
            missing.append(workload)
            continue
        dogi_waf = float(dogi.get("waf", 99.0))
        hybrid_waf = float(hybrid.get("waf", 99.0))
        fifo_waf = float(fifo.get("waf", 0.0))
        pure_waf = float(pure.get("waf", 0.0))
        dogi_good = dogi_waf <= fifo_waf and dogi_waf <= pure_waf
        hybrid_good = hybrid_waf <= fifo_waf and hybrid_waf <= pure_waf
        wins[workload] = {
            "dogi_waf": dogi_waf,
            "hybrid_waf": hybrid_waf,
            "fifo_waf": fifo_waf,
            "pure_quasar_waf": pure_waf,
            "dogi_history_wins": dogi_good,
            "hybrid_inherits_dogi_win": hybrid_good,
            "stale_secret_blocks": int(dogi.get("stale_secret_blocks_remaining", 0)),
        }

    passed_workloads = [
        workload
        for workload, row in wins.items()
        if row["dogi_history_wins"]
        and row["hybrid_inherits_dogi_win"]
        and row["stale_secret_blocks"] == 0
    ]
    passed = bool(
        len(passed_workloads) >= 5
        and not missing
        and len(passed_workloads) == len(wins)
    )
    return {
        "name": "DOGI-favorable non-PQC control",
        "tier": "negative-control",
        "passed": passed,
        "purpose": (
            "Prove that the evaluation does not cripple DOGI: when no PQC "
            "death-cohort signal exists, DOGI-style history placement is the right tool."
        ),
        "evidence": {
            "pqc0000_workloads": sorted(wins),
            "passed_workloads": passed_workloads,
            "missing_policy_workloads": missing,
            "comparisons": wins,
        },
        "paper_use": (
            "Use before the PQC-overlay results: QUASAR is not a universal "
            "history-placement replacement; the hybrid preserves DOGI's advantage."
        ),
    }


def ycsb_pressure(ycsb_curve: dict[str, Any]) -> dict[str, Any]:
    rows = ycsb_curve.get("rows", [])
    pressure = [row for row in rows if row.get("waf_pressure")]
    semantic = [row for row in rows if row.get("semantic_gap")]
    passed = bool(
        len(pressure) >= 3
        and len(semantic) == len(rows)
        and all(row.get("hybrid_stale_secret_blocks", 1) == 0 for row in rows)
    )
    return {
        "name": "YCSB p4000/p6000/p8000/p10000 DOGI-compatible pressure",
        "tier": "pressure",
        "passed": passed,
        "purpose": "Use DOGI/FAST YCSB axes with enough PQC density and zone pressure to create GC.",
        "evidence": {
            "row_count": ycsb_curve.get("row_count"),
            "failed_rows": ycsb_curve.get("failed_rows"),
            "waf_pressure_rows": ycsb_curve.get("waf_pressure_rows"),
            "semantic_gap_rows": ycsb_curve.get("semantic_gap_rows"),
            "pressure_workloads": [row.get("workloads", []) for row in pressure],
            "max_dogi_gc_blocks": max((row.get("dogi_gc_blocks", 0) for row in pressure), default=0),
            "max_dogi_stale_secret_blocks": max((row.get("dogi_stale_secret_blocks", 0) for row in rows), default=0),
        },
        "paper_use": "Use as the main DOGI-compatible WAF/GC pressure curve.",
    }


def sysbench_pressure(fast_db: dict[str, Any]) -> dict[str, Any]:
    comparison = fast_db.get("physical", {}).get("hybrid_vs_dogi_secret_group", {})
    passed = bool(
        fast_db.get("physical", {}).get("failed_rows", 1) == 0
        and comparison.get("gc_reduction", 0.0) >= 0.75
        and comparison.get("stale_secret_reduction_blocks", 0) > 0
    )
    return {
        "name": "Sysbench-OLTP FAST-style DB pressure",
        "tier": "pressure",
        "passed": passed,
        "purpose": "Show that the result is not only a synthetic YCSB artifact.",
        "evidence": {
            "rows": fast_db.get("physical", {}).get("rows"),
            "failed_rows": fast_db.get("physical", {}).get("failed_rows"),
            "gc_reduction": comparison.get("gc_reduction"),
            "waf_reduction": comparison.get("waf_reduction"),
            "stale_secret_reduction_blocks": comparison.get("stale_secret_reduction_blocks"),
        },
        "paper_use": "Label as FAST-style DB pressure, not a DOGI-paper workload.",
    }


def main_claim_eligibility(
    ycsb_curve: dict[str, Any],
    fast_db: dict[str, Any],
    dynamic_pressure: dict[str, Any],
) -> dict[str, Any]:
    """Gate the workloads that are allowed to support the headline WAF claim.

    Easy PQC overlays are still useful negative controls, but the main paper
    figure should only use rows where DOGI gets normal storage-visible locality
    and still pays GC/stale-secret cost because it cannot observe the PQC death
    cohort.
    """

    required_history_baselines = {"fifo", "sepbit-style", "midas-style", "dogi-history"}
    required_all_policies = required_history_baselines | {"quasar", "quasar-dogi-hybrid"}

    eligible_ycsb = []
    ycsb_baseline_complete_rows = 0
    for row in ycsb_curve.get("rows", []):
        baseline_failures = row.get("baseline_semantic_failures", {})
        baselines_present = required_history_baselines.issubset(baseline_failures)
        ycsb_baseline_complete_rows += int(baselines_present)
        if (
            row.get("waf_pressure")
            and row.get("semantic_gap")
            and baselines_present
            and row.get("dogi_gc_blocks", 0) > 0
            and row.get("dogi_stale_secret_blocks", 0) > 0
            and row.get("hybrid_stale_secret_blocks", 1) == 0
        ):
            eligible_ycsb.append(
                {
                    "workloads": row.get("workloads", []),
                    "pqc_level": row.get("pqc_level"),
                    "dogi_gc_blocks": row.get("dogi_gc_blocks"),
                    "dogi_stale_secret_blocks": row.get("dogi_stale_secret_blocks"),
                    "hybrid_gc_blocks": row.get("hybrid_gc_blocks"),
                    "hybrid_stale_secret_blocks": row.get("hybrid_stale_secret_blocks"),
                    "baselines_present": sorted(baseline_failures),
                }
            )

    db_comparison = fast_db.get("physical", {}).get("hybrid_vs_dogi_secret_group", {})
    db_eligible = bool(
        fast_db.get("physical", {}).get("failed_rows", 1) == 0
        and db_comparison.get("gc_reduction", 0.0) >= 0.75
        and db_comparison.get("stale_secret_reduction_blocks", 0) > 0
    )

    eligible_dynamic = []
    dynamic_baseline_complete_rows = 0
    for row in dynamic_pressure.get("physical", []):
        comparison = row.get("hybrid_vs_dogi", {})
        policies = row.get("policies", {})
        policies_present = required_all_policies.issubset(policies)
        dynamic_baseline_complete_rows += int(policies_present)
        dogi = policies.get("dogi-history", {})
        hybrid = policies.get("quasar-dogi-hybrid", {})
        if (
            row.get("failed_rows", 1) == 0
            and policies_present
            and comparison.get("gc_reduction", 0.0) >= 0.75
            and comparison.get("stale_secret_reduction_blocks", 0) > 0
            and dogi.get("sim_gc_blocks", 0) > 0
            and dogi.get("sim_stale_secret_blocks", 0) > 0
            and hybrid.get("sim_stale_secret_blocks", 1) == 0
        ):
            eligible_dynamic.append(
                {
                    "path": row.get("path"),
                    "dogi_waf": dogi.get("sim_waf"),
                    "hybrid_waf": hybrid.get("sim_waf"),
                    "dogi_gc_blocks": dogi.get("sim_gc_blocks"),
                    "hybrid_gc_blocks": hybrid.get("sim_gc_blocks"),
                    "gc_reduction": comparison.get("gc_reduction"),
                    "stale_secret_reduction_blocks": comparison.get("stale_secret_reduction_blocks"),
                    "policies_present": sorted(policies),
                }
            )

    passed = bool(
        len(eligible_ycsb) >= 3
        and ycsb_baseline_complete_rows >= 3
        and db_eligible
        and len(eligible_dynamic) >= 2
        and dynamic_baseline_complete_rows >= 2
    )
    return {
        "name": "Main WAF/GC claim eligibility gate",
        "tier": "claim-gate",
        "passed": passed,
        "purpose": (
            "Prevent easy negative-control workloads from being used as the "
            "headline WAF figure."
        ),
        "evidence": {
            "eligible_ycsb_pressure_rows": len(eligible_ycsb),
            "ycsb_baseline_complete_rows": ycsb_baseline_complete_rows,
            "db_pressure_eligible": db_eligible,
            "eligible_dynamic_rows": len(eligible_dynamic),
            "dynamic_baseline_complete_rows": dynamic_baseline_complete_rows,
            "required_history_baselines": sorted(required_history_baselines),
            "required_all_policies": sorted(required_all_policies),
            "minimum_rule": ">=3 YCSB pressure rows with all history baselines, DB pressure eligible, >=2 dynamic pressure rows with all policies",
            "eligible_ycsb_examples": eligible_ycsb[:3],
            "eligible_dynamic_examples": eligible_dynamic[:3],
        },
        "paper_use": (
            "Use only these eligible pressure rows for the headline WAF/GC "
            "claim; keep easy p2000 rows as negative controls."
        ),
    }


def fairness_matrix(fair: dict[str, Any]) -> dict[str, Any]:
    summary = fair.get("summary", {})
    rows = summary.get("by_policy_packing", {})
    dogi = rows.get("dogi-history::secret-group", {})
    hybrid = rows.get("quasar-dogi-hybrid::secret-group", {})
    passed = bool(
        fair.get("execute", False)
        and summary.get("failed_rows", 1) == 0
        and summary.get("row_count", 0) >= 72
        and dogi.get("sim_stale_secret_blocks", 0) > 0
        and dogi.get("physical_reset_commands", 1) == 0
        and hybrid.get("sim_stale_secret_blocks", 1) == 0
        and hybrid.get("physical_reset_commands", 0) > 0
    )
    return {
        "name": "DOGI six-axis fairness matrix",
        "tier": "fairness",
        "passed": passed,
        "purpose": "Match DOGI/FAST workload axes without pretending every row is a WAF stress test.",
        "evidence": {
            "rows": summary.get("row_count"),
            "failed_rows": summary.get("failed_rows"),
            "dogi_waf": dogi.get("sim_waf"),
            "hybrid_waf": hybrid.get("sim_waf"),
            "dogi_stale_secret_blocks": dogi.get("sim_stale_secret_blocks"),
            "hybrid_stale_secret_blocks": hybrid.get("sim_stale_secret_blocks"),
            "hybrid_semantic_resets": hybrid.get("physical_reset_commands"),
        },
        "paper_use": "Use for fairness and semantic-exposure evidence; do not oversell WAF here.",
    }


def multitenant_pressure(multitenant: dict[str, Any]) -> dict[str, Any]:
    comparison = multitenant.get("physical", {}).get("tenant_isolation_vs_current", {})
    passed = bool(
        multitenant.get("physical", {}).get("failed_rows", 1) == 0
        and comparison.get("reset_secret_tenant_impurity_reduction", 0.0) >= 1.0
        and multitenant.get("decision") == "add-tenant-isolation-mode"
    )
    return {
        "name": "Multi-tenant PQC pressure",
        "tier": "hostile-robustness",
        "passed": passed,
        "purpose": "Attack QUASAR's open-zone/family count assumptions with many tenants.",
        "evidence": {
            "decision": multitenant.get("decision"),
            "failed_rows": multitenant.get("physical", {}).get("failed_rows"),
            "waf_increase": comparison.get("waf_increase"),
            "gc_extra_blocks": comparison.get("gc_extra_blocks"),
            "physical_reset_extra_commands": comparison.get("physical_reset_extra_commands"),
            "reset_secret_tenant_impurity_reduction": comparison.get("reset_secret_tenant_impurity_reduction"),
        },
        "paper_use": "Use to justify a tenant-isolation mode rather than one universal allocator setting.",
    }


def hint_and_straggler_robustness(robustness: dict[str, Any]) -> dict[str, Any]:
    missing = robustness.get("missing_hint_5pct", {}).get("hybrid", {})
    wrong = robustness.get("wrong_epoch_5pct", {}).get("hybrid", {})
    straggler_exact = robustness.get("straggler_5pct_exact_secret_group", {}).get("hybrid", {})
    fallback = robustness.get("straggler_5pct_epoch_bin_5_residual_12288", {}).get("hybrid", {})
    passed = bool(
        robustness.get("missing_hint_5pct", {}).get("failed_rows", 1) == 0
        and robustness.get("wrong_epoch_5pct", {}).get("failed_rows", 1) == 0
        and robustness.get("straggler_5pct_exact_secret_group", {}).get("failed_rows", 0) > 0
        and robustness.get("straggler_5pct_epoch_bin_5_residual_12288", {}).get("failed_rows", 1) == 0
        and fallback.get("secret_waiting_end", 1) == 0
    )
    return {
        "name": "Bad-hint and straggler robustness",
        "tier": "hostile-robustness",
        "passed": passed,
        "purpose": "Show that QUASAR has boundaries and needs fallback under imperfect lifetimes.",
        "evidence": {
            "decision": robustness.get("decision"),
            "missing_hint_failed_rows": robustness.get("missing_hint_5pct", {}).get("failed_rows"),
            "missing_hint_secret_waiting_end": missing.get("secret_waiting_end"),
            "wrong_epoch_failed_rows": robustness.get("wrong_epoch_5pct", {}).get("failed_rows"),
            "wrong_epoch_secret_waiting_end": wrong.get("secret_waiting_end"),
            "straggler_exact_failed_rows": robustness.get("straggler_5pct_exact_secret_group", {}).get("failed_rows"),
            "straggler_exact_secret_waiting_end": straggler_exact.get("secret_waiting_end"),
            "fallback_failed_rows": robustness.get("straggler_5pct_epoch_bin_5_residual_12288", {}).get("failed_rows"),
            "fallback_secret_waiting_end": fallback.get("secret_waiting_end"),
            "fallback_physical_waf": fallback.get("physical_waf"),
            "fallback_residual_migrated_blocks": fallback.get("residual_migrated_blocks"),
        },
        "paper_use": "Use as the design-boundary figure: exact cohorting is not enough under stragglers.",
    }


def residual_frontier(residual: dict[str, Any]) -> dict[str, Any]:
    physical_rows = residual.get("physical_rows", [])
    workloads = {row.get("workload") for row in physical_rows}
    ycsb_strict = next(
        (
            row
            for row in physical_rows
            if row.get("workload") == "ycsb-f-pqc8000" and row.get("profile") == "strict_zero_wait"
        ),
        {},
    )
    passed = bool(
        residual.get("decision")
        in {
            "use-profiled-residual-controller",
            "use-residual-fallback-as-strict-exposure-mode",
        }
        and {"exchange-pqc2000", "sysbench-oltp-pqc4000", "ycsb-a-pqc4000", "ycsb-f-pqc8000"}.issubset(workloads)
        and ycsb_strict.get("secret_waiting_end") == 0
        and ycsb_strict.get("physical_waf", 0.0) >= 3.0
    )
    return {
        "name": "Residual fallback frontier",
        "tier": "hostile-robustness",
        "passed": passed,
        "purpose": "Measure when strict zero-wait exposure is affordable and when it is too expensive.",
        "evidence": {
            "decision": residual.get("decision"),
            "physical_workloads": sorted(workloads),
            "ycsb_f_strict_zero_wait_waf": ycsb_strict.get("physical_waf"),
            "ycsb_f_strict_zero_wait_residual_blocks": ycsb_strict.get("residual_migrated_blocks"),
            "ycsb_f_strict_zero_wait_secret_waiting_end": ycsb_strict.get("secret_waiting_end"),
        },
        "paper_use": "Use to present low-overhead, balanced, and strict-zero-wait modes.",
    }


def summarize(
    fair: dict[str, Any],
    dogi_eval_rows: list[dict[str, Any]],
    ycsb_curve: dict[str, Any],
    fast_db: dict[str, Any],
    dynamic_pressure: dict[str, Any],
    multitenant: dict[str, Any],
    robustness: dict[str, Any],
    residual: dict[str, Any],
) -> dict[str, Any]:
    entries = [
        fairness_matrix(fair),
        dogi_favorable_control(dogi_eval_rows),
        ycsb_negative_control(ycsb_curve),
        ycsb_pressure(ycsb_curve),
        sysbench_pressure(fast_db),
        main_claim_eligibility(ycsb_curve, fast_db, dynamic_pressure),
        multitenant_pressure(multitenant),
        hint_and_straggler_robustness(robustness),
        residual_frontier(residual),
    ]
    by_tier: dict[str, dict[str, int]] = {}
    for entry in entries:
        tier = entry["tier"]
        by_tier.setdefault(tier, {"passed": 0, "total": 0})
        by_tier[tier]["total"] += 1
        by_tier[tier]["passed"] += int(entry["passed"])
    return {
        "scope": "DOGI/FAST-compatible workload hardness matrix for QUASAR evaluation",
        "passed": all(entry["passed"] for entry in entries),
        "passed_entries": sum(1 for entry in entries if entry["passed"]),
        "total_entries": len(entries),
        "by_tier": by_tier,
        "entries": entries,
        "main_takeaway": (
            "The suite now contains a DOGI-favorable non-PQC control, a negative WAF "
            "control, DOGI-compatible pressure rows, FAST-style DB pressure, dynamic "
            "service pressure, an explicit main-claim eligibility gate, and QUASAR-hostile "
            "robustness cases. This prevents the paper from relying on an overly easy "
            "PQC-only workload."
        ),
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# QUASAR Workload Hardness Matrix",
        "",
        summary["main_takeaway"],
        "",
        f"- Passed: `{summary['passed_entries']}/{summary['total_entries']}`",
        f"- By tier: `{summary['by_tier']}`",
        "",
        "| Entry | Tier | Pass | Purpose | Key Evidence | Paper Use |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry in summary["entries"]:
        evidence = "<br>".join(f"- `{key}`: {fmt(value)}" for key, value in entry["evidence"].items())
        lines.append(
            "| {name} | `{tier}` | `{passed}` | {purpose} | {evidence} | {paper_use} |".format(
                name=entry["name"],
                tier=entry["tier"],
                passed="yes" if entry["passed"] else "no",
                purpose=entry["purpose"],
                evidence=evidence,
                paper_use=entry["paper_use"],
            )
        )
    lines.extend(
        [
            "",
            "## Reviewer Answer",
            "",
            "The clean PQC epoch trace is intentionally not the main evidence. It is a sanity check.",
            "",
            "The main evaluation uses DOGI/FAST-compatible macro workloads with PQC lifecycle overlays:",
            "",
            "- DOGI-favorable `pqc0000` controls show that history placement is strong when no PQC death cohort exists.",
            "- YCSB p2000 is the negative WAF control.",
            "- YCSB p4000/p6000/p8000/p10000 is the DOGI-compatible WAF/GC pressure curve.",
            "- Sysbench-OLTP is the FAST-style DB pressure extension.",
            "- Dynamic service pressure checks Exchange/Varmail/Alibaba-like DOGI axes.",
            "- The main-claim gate marks which rows are allowed to support the headline WAF/GC figure.",
            "- Multi-tenant, bad-hint, and straggler cases attack QUASAR itself.",
            "",
            "Therefore the paper should claim pressure-dependent WAF/GC gains and broad stale-secret exposure reduction, not universal WAF dominance.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fair",
        type=Path,
        default=Path("artifacts/results/packed-physical-zonefs-replay-dogi-paper-pqc2000-z512-secret-group-helper.json"),
    )
    parser.add_argument(
        "--ycsb-curve",
        type=Path,
        default=Path("artifacts/results/fast-ycsb-pressure/ycsb-actual-zns-pressure-curve.json"),
    )
    parser.add_argument(
        "--dogi-eval",
        type=Path,
        default=Path("artifacts/results/dogi-paper-ratio-sweep-50k/eval.json"),
    )
    parser.add_argument(
        "--fast-db",
        type=Path,
        default=Path("artifacts/results/fast-db-pressure/sysbench-pressure-summary.json"),
    )
    parser.add_argument(
        "--dynamic-pressure",
        type=Path,
        default=Path("artifacts/results/fast-dynamic-pressure/dynamic-pressure-summary.json"),
    )
    parser.add_argument(
        "--multitenant",
        type=Path,
        default=Path("artifacts/results/multitenant-pressure/multitenant-pressure-summary.json"),
    )
    parser.add_argument(
        "--robustness",
        type=Path,
        default=Path("artifacts/results/physical-robustness-ycsb-a-pqc4000/summary.json"),
    )
    parser.add_argument(
        "--residual",
        type=Path,
        default=Path("artifacts/results/residual-fallback-sweep/summary.json"),
    )
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/workload-hardness-matrix.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/workload-hardness-matrix.md"))
    args = parser.parse_args()

    summary = summarize(
        load_json(args.fair),
        load_json(args.dogi_eval),
        load_json(args.ycsb_curve),
        load_json(args.fast_db),
        load_json(args.dynamic_pressure),
        load_json(args.multitenant),
        load_json(args.robustness),
        load_json(args.residual),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "passed": summary["passed"]}, sort_keys=True))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
