#!/usr/bin/env python3
"""Create a unified baseline-vs-QUASAR comparison report.

The project now has several kinds of evidence:

* same-path physical ZNS packed replay, where FIFO/SepBIT-style/MiDAS-style/
  DOGI-style/QUASAR all run through the same QUASAR replay model;
* FAST-style DB pressure replay on the physical ZNS SSD;
* FAST/YCSB pressure replay on the physical ZNS SSD;
* adaptive QUASAR policy comparison against the current deployable hybrid;
* multi-tenant tenant-isolation pressure replay;
* exact external DOGI/MiDAS/SepBIT artifacts, whose units and stacks differ.

This report keeps those regimes separate so the paper can be strong without
accidentally comparing incompatible numbers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


STYLE_POLICIES = [
    "fifo",
    "sepbit-style",
    "midas-style",
    "dogi-history",
    "quasar",
    "quasar-dogi-hybrid",
]


LABELS = {
    "fifo": "FIFO",
    "sepbit-style": "SepBIT-style",
    "midas-style": "MiDAS-style",
    "dogi-history": "DOGI-style",
    "quasar": "QUASAR",
    "quasar-dogi-hybrid": "QUASAR-DOGI hybrid",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def pct_reduction(before: float, after: float) -> float | None:
    if before == 0:
        return None
    return (before - after) / before


def fmt_float(value: float | None, digits: int = 4) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def fmt_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def fmt_int(value: int | float | None) -> str:
    return "N/A" if value is None else f"{int(value):,}"


def row_for(rows: dict[str, Any], policy: str, packing: str = "secret-group") -> dict[str, Any]:
    return rows.get(f"{policy}::{packing}", {})


def summarize_physical_fairness(report: dict[str, Any]) -> dict[str, Any]:
    rows = report.get("summary", {}).get("by_policy_packing", {})
    by_policy = {}
    for policy in STYLE_POLICIES:
        item = row_for(rows, policy)
        by_policy[policy] = {
            "sim_waf": item.get("sim_waf"),
            "sim_gc_blocks": item.get("sim_gc_blocks"),
            "sim_stale_secret_blocks": item.get("sim_stale_secret_blocks"),
            "physical_reset_commands": item.get("physical_reset_commands"),
            "secret_waiting_end": item.get("secret_blocks_waiting_for_physical_reset"),
            "max_secret_waiting": item.get("max_secret_blocks_waiting_for_physical_reset"),
            "avg_space_utilization": item.get("avg_space_utilization"),
            "max_live_physical_zones": item.get("max_live_physical_zones"),
        }
    dogi = by_policy["dogi-history"]
    hybrid = by_policy["quasar-dogi-hybrid"]
    return {
        "artifact": "packed-physical-zonefs-replay-dogi-paper-pqc2000-z512-secret-group-helper",
        "scope": "same physical ZNS packed replay over six DOGI-paper workload axes at pqc2000",
        "rows": report.get("summary", {}).get("row_count"),
        "failed_rows": report.get("summary", {}).get("failed_rows"),
        "wall_time_s": report.get("summary", {}).get("wall_time_s"),
        "append_engine": report.get("append_engine"),
        "helper_chunk_blocks": report.get("helper_chunk_blocks"),
        "physical_zone_capacity": report.get("physical_zone_capacity"),
        "by_policy": by_policy,
        "hybrid_vs_dogi": {
            "waf_reduction": pct_reduction(float(dogi.get("sim_waf") or 0.0), float(hybrid.get("sim_waf") or 0.0)),
            "gc_reduction": pct_reduction(
                float(dogi.get("sim_gc_blocks") or 0),
                float(hybrid.get("sim_gc_blocks") or 0),
            ),
            "stale_secret_reduction_blocks": int(dogi.get("sim_stale_secret_blocks") or 0)
            - int(hybrid.get("sim_stale_secret_blocks") or 0),
        },
    }


def summarize_fast_db(data: dict[str, Any]) -> dict[str, Any]:
    physical = data["physical"]
    rows = physical["by_policy_packing"]
    return {
        "scope": "FAST-style Sysbench-OLTP pressure stress, not a DOGI paper workload",
        "rows": physical["rows"],
        "failed_rows": physical["failed_rows"],
        "wall_time_s": physical["wall_time_s"],
        "total_physical_gib": physical["total_physical_gib"],
        "append_engine": physical["append_engine"],
        "by_policy": rows,
        "hybrid_vs_dogi": physical["hybrid_vs_dogi_secret_group"],
    }


def summarize_fast_ycsb(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": "FAST/YCSB-A/F pressure stress with higher PQC ratios and tight free-zone margins",
        "simulator": data["simulator"],
        "physical": data["physical"],
    }


def summarize_ycsb_pressure_curve(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": data.get("scope"),
        "row_count": data.get("row_count"),
        "failed_rows": data.get("failed_rows"),
        "waf_pressure_rows": data.get("waf_pressure_rows"),
        "semantic_gap_rows": data.get("semantic_gap_rows"),
        "rows": data.get("rows", []),
    }


def summarize_actual_zns_overhead(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": data.get("scope"),
        "artifact_count": data.get("artifact_count"),
        "row_count": data.get("row_count"),
        "failed_rows": data.get("failed_rows"),
        "by_policy": data.get("by_policy", {}),
        "hybrid_vs_dogi": data.get("hybrid_vs_dogi", {}),
        "caveat": data.get("caveat"),
    }


def summarize_xnvme_zns_latency(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "backend": data.get("backend"),
        "completed": data.get("completed"),
        "device": data.get("device"),
        "append_count": data.get("append_count"),
        "append_avg_ns": data.get("append_avg_ns"),
        "append_p50_ns": data.get("append_p50_ns"),
        "append_p95_ns": data.get("append_p95_ns"),
        "append_p99_ns": data.get("append_p99_ns"),
        "append_max_ns": data.get("append_max_ns"),
        "reset_before_ns": data.get("reset_before_ns"),
        "reset_after_ns": data.get("reset_after_ns"),
        "throughput_mib_s": data.get("throughput_mib_s"),
        "mounted_after": data.get("mounted_after"),
        "nonempty_after_lines": data.get("nonempty_after_lines"),
        "caveat": (
            "Raw xNVMe/Linux NVMe ioctl Zone Append probe. This bypasses zonefs helper overhead, "
            "but it is not an SPDK poll-mode result because the local build lacks a new enough "
            "liburing/SPDK backend."
        ),
    }


def summarize_security_capability(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "device_model": data.get("device_model"),
        "firmware": data.get("firmware"),
        "sanicap_hex": data.get("sanicap_hex"),
        "sanitize_supported": data.get("sanitize_supported"),
        "sanitize_operations_supported": data.get("sanitize_operations_supported", {}),
        "sanitize_log_status": data.get("sanitize_log_status"),
        "sanitize_progress": data.get("sanitize_progress"),
        "sanitize_cdw10_info": data.get("sanitize_cdw10_info"),
        "sanitize_completed": data.get("sanitize_completed"),
        "crypto_erase_executed": data.get("crypto_erase_executed"),
        "sanitize_execution_validated": data.get("sanitize_execution_validated"),
        "claim_boundary": data.get("claim_boundary"),
    }


def summarize_claim_matrix(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_count": data.get("claim_count"),
        "by_status": data.get("by_status", {}),
        "claims": data.get("claims", []),
    }


def summarize_workload_hardness(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": data.get("scope"),
        "passed": data.get("passed"),
        "passed_entries": data.get("passed_entries"),
        "total_entries": data.get("total_entries"),
        "by_tier": data.get("by_tier", {}),
        "entries": data.get("entries", []),
        "main_takeaway": data.get("main_takeaway"),
    }


def summarize_deployment_selector(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": data.get("scope"),
        "passed": data.get("passed"),
        "passed_modes": data.get("passed_modes"),
        "total_modes": data.get("total_modes"),
        "hardness_passed": data.get("hardness_passed"),
        "default_policy": data.get("default_policy"),
        "modes": data.get("modes", []),
        "selector": data.get("selector", []),
        "main_takeaway": data.get("main_takeaway"),
    }


def summarize_reproducibility_manifest(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": data.get("scope"),
        "passed": data.get("passed"),
        "artifact_count": data.get("artifact_count"),
        "missing_or_empty": data.get("missing_or_empty", []),
        "command_count": len(data.get("commands", [])),
        "artifacts": data.get("artifacts", []),
    }


def summarize_reproducibility_validation(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": data.get("scope"),
        "passed": data.get("passed"),
        "artifact_count": data.get("artifact_count"),
        "mismatch_count": data.get("mismatch_count"),
        "mismatches": data.get("mismatches", []),
    }


def summarize_ycsb_f_straggler_baselines(data: dict[str, Any]) -> dict[str, Any]:
    rows = data.get("summary", {}).get("by_policy_packing", {})
    return {
        "scope": "YCSB-F p8000 with 5% delayed-expiry stragglers on actual ZNS for history baselines",
        "rows": data.get("summary", {}).get("row_count"),
        "failed_rows": data.get("summary", {}).get("failed_rows"),
        "wall_time_s": data.get("summary", {}).get("wall_time_s"),
        "by_policy": {
            key.split("::", 1)[0]: item
            for key, item in rows.items()
            if key.endswith("::secret-group")
        },
    }


def summarize_adaptive(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": "adaptive QUASAR admission/binning comparison on YCSB and Sysbench pressure suites",
        "default_policy": data.get("default_policy"),
        "candidate_policy": data.get("candidate_policy"),
        "decision": data.get("decision"),
        "decision_reason": data.get("decision_reason"),
        "ycsb_pressure": data.get("ycsb_pressure", {}),
        "sysbench_pressure": data.get("sysbench_pressure", {}),
    }


def summarize_multitenant(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": "multi-tenant PQC pressure with reset-time secret tenant isolation",
        "decision": data.get("decision"),
        "simulator": data.get("simulator", {}),
        "physical": data.get("physical", {}),
    }


def summarize_physical_robustness(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": data.get("scope"),
        "trace": data.get("trace"),
        "device_limits": data.get("device_limits", {}),
        "clean": data.get("clean", {}),
        "missing_hint_5pct": data.get("missing_hint_5pct", {}),
        "wrong_epoch_5pct": data.get("wrong_epoch_5pct", {}),
        "straggler_5pct_exact_secret_group": data.get("straggler_5pct_exact_secret_group", {}),
        "straggler_5pct_exact_secret_group_nobatch": data.get("straggler_5pct_exact_secret_group_nobatch", {}),
        "straggler_5pct_epoch_bin_4": data.get("straggler_5pct_epoch_bin_4", {}),
        "straggler_5pct_epoch_bin_5_residual_12288": data.get("straggler_5pct_epoch_bin_5_residual_12288", {}),
        "decision": data.get("decision"),
        "decision_reason": data.get("decision_reason"),
    }


def summarize_residual_fallback(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": data.get("scope"),
        "device_limits": data.get("device_limits", {}),
        "decision": data.get("decision"),
        "best_candidates": data.get("best_candidates", {}),
        "physical_rows": data.get("physical_rows", []),
        "budget_rows": data.get("budget_rows", []),
        "budget_physical_rows": data.get("budget_physical_rows", []),
        "controller_decisions": data.get("controller_decisions", []),
        "dryrun_row_count": len(data.get("dryrun_rows", [])),
    }


def summarize_exact_baselines(
    dogi: dict[str, Any],
    dogi_pressure: dict[str, Any],
    dogi_pressure_suite: dict[str, Any],
    dogi_original_lba: dict[str, Any],
    midas: dict[str, Any],
    sepbit: dict[str, Any],
    nosep: dict[str, Any],
) -> dict[str, Any]:
    dogi_rows = []
    for row in dogi.get("rows", []):
        dogi_rows.append(
            {
                "workload": row.get("workload"),
                "waf": row.get("waf"),
                "user_write_gib": row.get("user_write_gib"),
                "gc_write_gib": row.get("gc_write_gib"),
                "completed": row.get("completed"),
            }
        )
    return {
        "dogi_physical_compact": {
            "scope": "exact external DOGI prototype on physical ZNS, compacted LBA span",
            "completed": dogi.get("completed"),
            "workloads": dogi.get("workloads"),
            "aggregate_waf": dogi.get("aggregate_waf"),
            "avg_waf": dogi.get("avg_waf"),
            "total_user_write_gib": dogi.get("total_user_write_gib"),
            "total_gc_write_gib": dogi.get("total_gc_write_gib"),
            "logical_size_gb": dogi.get("logical_size_gb"),
            "rows": dogi_rows,
            "caveat": (
                "Compacted LBA span preserves reuse order but is not the full original "
                "LBA span used by a production run."
            ),
        },
        "dogi_physical_dynamic_pressure": {
            "scope": "exact external DOGI prototype on physical ZNS, Alibaba-like p8000 compact trace",
            "completed": dogi_pressure.get("completed"),
            "waf": dogi_pressure.get("waf"),
            "user_write_gib": dogi_pressure.get("user_write_gib"),
            "gc_write_gib": dogi_pressure.get("gc_write_gib"),
            "trace_path": dogi_pressure.get("trace_path"),
            "placement_algorithm": dogi_pressure.get("placement_algorithm"),
            "selection_algorithm": dogi_pressure.get("selection_algorithm"),
            "saw_zenfs_mount": dogi_pressure.get("saw_zenfs_mount"),
            "caveat": (
                "This is the public DOGI binary on a compacted Alibaba-like PQC pressure trace. "
                "It validates the exact DOGI stack on the physical ZNS device, but units still differ "
                "from QUASAR's same-path packed replay."
            ),
        },
        "dogi_physical_dynamic_pressure_suite": {
            "scope": "exact public DOGI prototype placement variants on physical ZNS, Alibaba-like p8000 compact trace",
            "completed_runs": dogi_pressure_suite.get("completed_runs"),
            "total_runs": dogi_pressure_suite.get("total_runs"),
            "best_placement": dogi_pressure_suite.get("best_placement"),
            "best_waf": dogi_pressure_suite.get("best_waf"),
            "rows": dogi_pressure_suite.get("rows", []),
            "caveat": dogi_pressure_suite.get("caveat"),
        },
        "dogi_physical_original_lba_pressure": {
            "scope": "exact external DOGI prototype on physical ZNS, Alibaba-like p8000 original LBA span",
            "completed": dogi_original_lba.get("completed"),
            "waf": dogi_original_lba.get("waf"),
            "user_write_gib": dogi_original_lba.get("user_write_gib"),
            "gc_write_gib": dogi_original_lba.get("gc_write_gib"),
            "trace_path": dogi_original_lba.get("trace_path"),
            "placement_algorithm": dogi_original_lba.get("placement_algorithm"),
            "selection_algorithm": dogi_original_lba.get("selection_algorithm"),
            "saw_zenfs_mount": dogi_original_lba.get("saw_zenfs_mount"),
            "caveat": (
                "This run keeps the original LBA span and therefore removes the compact-LBA caveat "
                "for the Alibaba-like p8000 DOGI pressure trace. It is still an exact DOGI-stack "
                "counter, not a same-path QUASAR packed-replay metric."
            ),
        },
        "midas_memory_repeat4": {
            "scope": "exact external MiDAS memory-backed prototype on exchange-pqc2000 repeat4 compact trace",
            "completed": midas.get("completed"),
            "total_waf": midas.get("total_waf"),
            "recomputed_waf_from_dataw_gcdw": midas.get("recomputed_waf_from_dataw_gcdw"),
            "runtime_seconds": midas.get("runtime_seconds"),
            "counters": midas.get("counters", {}),
            "caveat": (
                "MiDAS exact artifact uses internal page/traffic units and a memory-backed "
                "prototype, so it is evidence about MiDAS strength but not a direct ZNS "
                "throughput comparison."
            ),
        },
        "sepbit_repeat4": {
            "scope": "exact external SepBIT trace_replay simulator on the same exchange repeat4 compact trace",
            "completed": sepbit.get("completed"),
            "wa": sepbit.get("summary", {}).get("wa"),
            "ngc": sepbit.get("summary", {}).get("ngc"),
            "bytes_to_system": sepbit.get("summary", {}).get("bytes_to_system"),
            "bytes_to_storage": sepbit.get("summary", {}).get("bytes_to_storage"),
            "nosep_wa": nosep.get("summary", {}).get("wa"),
            "nosep_ngc": nosep.get("summary", {}).get("ngc"),
            "caveat": (
                "SepBIT numbers are trace_replay simulator WA, not native ZNS physical "
                "append latency."
            ),
        },
    }


def markdown(summary: dict[str, Any]) -> str:
    fair = summary["same_path_physical_zns"]
    fast_db = summary["fast_db_pressure"]
    fast_ycsb = summary["fast_ycsb_pressure"]
    ycsb_pressure_curve = summary["ycsb_pressure_curve"]
    actual_zns_overhead = summary["actual_zns_overhead"]
    xnvme_zns_latency = summary["xnvme_zns_latency"]
    security_capability = summary["security_capability"]
    claim_matrix = summary["claim_matrix"]
    workload_hardness = summary["workload_hardness"]
    deployment_selector = summary["deployment_selector"]
    reproducibility_manifest = summary["reproducibility_manifest"]
    reproducibility_validation = summary["reproducibility_validation"]
    ycsb_f_straggler_baselines = summary["ycsb_f_straggler_baselines"]
    adaptive = summary["adaptive_policy_comparison"]
    multitenant = summary["multitenant_pressure"]
    robustness = summary["physical_robustness"]
    residual = summary["residual_fallback_sweep"]
    exact = summary["exact_external_baselines"]

    lines = [
        "# Unified Baseline vs QUASAR Comparison",
        "",
        "This report separates evidence by compatibility of units and stack.",
        "",
        "## Main Conclusion",
        "",
        "- The deployable policy should be **QUASAR-DOGI hybrid with secret-group packing**: DOGI-style placement remains useful for normal payload locality, while QUASAR handles PQC secret death cohorts.",
        "- The six DOGI-paper workload-axis replay is the fairness matrix. It mainly proves stale-secret exposure and semantic reset behavior because WAF is often already near 1.0.",
        "- The FAST-style Sysbench-OLTP pressure replay is the stress figure. It shows WAF/GC separation when update-heavy DB traffic and PQC metadata create real pressure.",
        "- The FAST/YCSB pressure replay confirms the workload concern: p2000 YCSB can be too easy, while p4000 through p10000 YCSB-A/F exposes WAF/GC separation.",
        "- The actual-ZNS YCSB pressure curve now includes p2000 as a negative WAF control and p4000/p6000/p8000/p10000 as pressure points.",
        "- Adaptive QUASAR binning was tested but did not beat the current hybrid in the single-tenant pressure suite, so the default remains QUASAR-DOGI hybrid.",
        "- Multi-tenant pressure adds a second mode: tuned adaptive hybrid can eliminate reset-time secret tenant mixing at measurable reset/open-zone cost.",
        "- Physical hint robustness shows a real improvement boundary: clean/missing/wrong hints execute, stragglers can exceed the ZNS open-zone budget, and residual epoch-bin fallback restores zero final secret waiting at explicit GC-copy cost.",
        "- Residual fallback sweep generalizes this boundary: Exchange and Sysbench representatives are practical, while YCSB-F p8000 shows strict zero-wait mode can be too expensive.",
        "- The residual controller converts that sweep into deployable choices: low-overhead, balanced, and strict-zero-wait profiles choose different residual copy budgets from the measured frontier.",
        "- The YCSB-F straggler baseline replay runs FIFO/SepBIT/MiDAS/DOGI on the same actual-ZNS hard condition and confirms they issue no semantic resets.",
        "- Actual-ZNS overhead is now reported separately: hybrid pays semantic reset work, while C-level policy-decision cost remains below DOGI-style MLP inference.",
        "- Security semantics are bounded explicitly: current evidence proves reset eligibility and exposure reduction, not NAND physical erasure without sanitize validation.",
        "- Claim matrix is generated as a writing guardrail: supported, qualified, and boundary claims are separated from forbidden overclaims.",
        "- Workload hardness matrix is generated as a benchmark guardrail: negative controls, pressure workloads, headline claim eligibility, and QUASAR-hostile workloads are separated.",
        "- Deployment policy selector is generated as an implementation guardrail: default hybrid, tenant isolation, residual migration, and overflow fallback are explicit modes.",
        "- Reproducibility manifest records the actual-ZNS artifacts, hashes, paper claims, and regeneration commands.",
        "- Reproducibility validation checks that current artifact files still match the manifest hashes.",
        "- Exact DOGI/MiDAS/SepBIT artifacts are included, but their units are not directly interchangeable with QUASAR's native packed ZNS replay.",
        "",
        "## Reproducibility Manifest",
        "",
        f"- Scope: {reproducibility_manifest['scope']}",
        f"- Passed: `{reproducibility_manifest['passed']}`",
        f"- Artifacts: `{reproducibility_manifest['artifact_count']}`",
        f"- Commands: `{reproducibility_manifest['command_count']}`",
        f"- Missing or empty: `{reproducibility_manifest['missing_or_empty']}`",
        f"- Hash validation passed: `{reproducibility_validation['passed']}`",
        f"- Hash mismatches: `{reproducibility_validation['mismatch_count']}`",
        "",
        "## Deployment Policy Selector",
        "",
        f"- Scope: {deployment_selector['scope']}",
        f"- Passed modes: `{deployment_selector['passed_modes']}/{deployment_selector['total_modes']}`",
        f"- Default policy: `{deployment_selector['default_policy']}`",
        f"- Takeaway: {deployment_selector['main_takeaway']}",
        "",
        "| Mode | Policy | Pass | When |",
        "| --- | --- | --- | --- |",
    ]
    for mode in deployment_selector["modes"]:
        lines.append(
            "| `{mode}` | `{policy}` | `{passed}` | {when} |".format(
                mode=mode.get("mode"),
                policy=mode.get("policy"),
                passed="yes" if mode.get("passed") else "no",
                when=mode.get("when"),
            )
        )
    lines.extend(
        [
            "",
            "## Workload Hardness Matrix",
            "",
            f"- Scope: {workload_hardness['scope']}",
            f"- Passed: `{workload_hardness['passed_entries']}/{workload_hardness['total_entries']}`",
            f"- By tier: `{workload_hardness['by_tier']}`",
            f"- Takeaway: {workload_hardness['main_takeaway']}",
            "",
            "| Entry | Tier | Pass | Purpose |",
            "| --- | --- | --- | --- |",
        ]
    )
    for entry in workload_hardness["entries"]:
        lines.append(
            "| {name} | `{tier}` | `{passed}` | {purpose} |".format(
                name=entry.get("name"),
                tier=entry.get("tier"),
                passed="yes" if entry.get("passed") else "no",
                purpose=entry.get("purpose"),
            )
        )
    claim_gate = next((entry for entry in workload_hardness["entries"] if entry.get("tier") == "claim-gate"), {})
    claim_evidence = claim_gate.get("evidence", {})
    if claim_gate:
        lines.extend(
            [
                "",
                "### Headline WAF/GC Claim Gate",
                "",
                f"- Pass: `{'yes' if claim_gate.get('passed') else 'no'}`",
                f"- Rule: {claim_evidence.get('minimum_rule')}",
                f"- YCSB eligible pressure rows: `{claim_evidence.get('eligible_ycsb_pressure_rows')}`",
                f"- YCSB baseline-complete rows: `{claim_evidence.get('ycsb_baseline_complete_rows')}`",
                f"- Dynamic eligible rows: `{claim_evidence.get('eligible_dynamic_rows')}`",
                f"- Dynamic baseline-complete rows: `{claim_evidence.get('dynamic_baseline_complete_rows')}`",
                f"- DB pressure eligible: `{claim_evidence.get('db_pressure_eligible')}`",
                f"- Required history baselines: `{claim_evidence.get('required_history_baselines')}`",
                f"- Required dynamic policies: `{claim_evidence.get('required_all_policies')}`",
                "",
                "Only rows satisfying this gate should be used for the headline WAF/GC claim. "
                "Easy p2000 rows remain negative-control or semantic-exposure evidence.",
            ]
        )
    lines.extend(
        [
            "",
            "## Same-Path Physical ZNS Fairness Matrix",
            "",
            f"- Scope: {fair['scope']}",
            f"- Rows: `{fair['rows']}`, failed rows: `{fair['failed_rows']}`",
            f"- Wall time: `{fair['wall_time_s']:.3f}` s",
            f"- Physical zone capacity: `{fair['physical_zone_capacity']}` 4KiB blocks",
            f"- Append engine: `{fair['append_engine']}`, helper chunk blocks: `{fair['helper_chunk_blocks']}`",
            "",
            "| Policy | WAF | GC Blocks | Stale Secrets | Semantic Physical Resets | Secret Waiting End | Avg Util | Max Live Phys Zones |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for policy in STYLE_POLICIES:
        item = fair["by_policy"][policy]
        lines.append(
            "| {policy} | {waf} | {gc} | {stale} | {resets} | {wait} | {util} | {zones} |".format(
                policy=LABELS[policy],
                waf=fmt_float(item["sim_waf"]),
                gc=fmt_int(item["sim_gc_blocks"]),
                stale=fmt_int(item["sim_stale_secret_blocks"]),
                resets=fmt_int(item["physical_reset_commands"]),
                wait=fmt_int(item["secret_waiting_end"]),
                util=fmt_float(item["avg_space_utilization"], 3),
                zones=fmt_int(item["max_live_physical_zones"]),
            )
        )
    lines.extend(
        [
            "",
            "Hybrid vs DOGI-style on this fairness matrix:",
            "",
            f"- WAF reduction: `{fmt_pct(fair['hybrid_vs_dogi']['waf_reduction'])}`",
            f"- GC reduction: `{fmt_pct(fair['hybrid_vs_dogi']['gc_reduction'])}`",
            f"- Stale secret blocks removed: `{fmt_int(fair['hybrid_vs_dogi']['stale_secret_reduction_blocks'])}`",
            "",
            "## FAST-Style DB Pressure Stress",
            "",
            f"- Scope: {fast_db['scope']}",
            f"- Rows: `{fast_db['rows']}`, failed rows: `{fast_db['failed_rows']}`",
            f"- Wall time: `{fast_db['wall_time_s']:.3f}` s",
            f"- Total physical writes: `{fast_db['total_physical_gib']:.2f}` GiB",
            "",
            "| Policy / Packing | WAF | GC Blocks | Stale Secrets | Semantic Physical Resets | Secret Waiting End | Avg Util | Max Live Phys Zones |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for key in [
        "fifo::secret-group",
        "sepbit-style::secret-group",
        "midas-style::secret-group",
        "dogi-history::secret-group",
        "quasar::secret-group",
        "quasar-dogi-hybrid::secret-group",
    ]:
        item = fast_db["by_policy"][key]
        lines.append(
            "| `{key}` | {waf} | {gc} | {stale} | {resets} | {wait} | {util} | {zones} |".format(
                key=key,
                waf=fmt_float(item["sim_waf"]),
                gc=fmt_int(item["sim_gc_blocks"]),
                stale=fmt_int(item["sim_stale_secret_blocks"]),
                resets=fmt_int(item["physical_reset_commands"]),
                wait=fmt_int(item["secret_blocks_waiting_for_physical_reset"]),
                util=fmt_float(item["avg_space_utilization"], 3),
                zones=fmt_int(item["max_live_physical_zones"]),
            )
        )
    lines.extend(
        [
            "",
            "Hybrid vs DOGI-style on DB pressure:",
            "",
            f"- WAF reduction: `{fmt_pct(fast_db['hybrid_vs_dogi']['waf_reduction'])}`",
            f"- GC reduction: `{fmt_pct(fast_db['hybrid_vs_dogi']['gc_reduction'])}`",
            f"- Stale secret blocks removed: `{fmt_int(fast_db['hybrid_vs_dogi']['stale_secret_reduction_blocks'])}`",
            "",
            "## FAST/YCSB Pressure Stress",
            "",
            f"- Scope: {fast_ycsb['scope']}",
            "- Boundary: synthetic PQC metadata overlays on DOGI-style YCSB axes, not private original DOGI traces.",
            "",
            "| Workload | Zones | DOGI WAF | Hybrid WAF | WAF Reduction | DOGI GC Blocks | Hybrid GC Blocks | GC Reduction | DOGI Stale Secrets | Hybrid Stale Secrets |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for workload, item in fast_ycsb["simulator"].items():
        dogi_row = item["policies"]["dogi-history"]
        hybrid_row = item["policies"]["quasar-dogi-hybrid"]
        comparison = item["hybrid_vs_dogi"]
        lines.append(
            "| `{workload}` | {zones} | {dogi_waf} | {hybrid_waf} | {waf_red} | {dogi_gc} | {hybrid_gc} | {gc_red} | {dogi_stale} | {hybrid_stale} |".format(
                workload=workload,
                zones=item["zones"],
                dogi_waf=fmt_float(dogi_row["waf"]),
                hybrid_waf=fmt_float(hybrid_row["waf"]),
                waf_red=fmt_pct(comparison["waf_reduction"]),
                dogi_gc=fmt_int(dogi_row["gc_write_blocks"]),
                hybrid_gc=fmt_int(hybrid_row["gc_write_blocks"]),
                gc_red=fmt_pct(comparison["gc_reduction"]),
                dogi_stale=fmt_int(dogi_row["stale_secret_blocks_remaining"]),
                hybrid_stale=fmt_int(hybrid_row["stale_secret_blocks_remaining"]),
            )
        )
    lines.extend(
        [
            "",
            "Representative physical YCSB replays:",
            "",
            "| Workload | Rows | Failed | Logical Zones | Wall Time | DOGI WAF | Hybrid WAF | DOGI GC Blocks | Hybrid GC Blocks | DOGI Stale Secrets | Hybrid Stale Secrets | Hybrid Semantic Resets |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for workload, item in fast_ycsb["physical"].items():
        dogi_row = item["by_policy"]["dogi-history"]
        hybrid_row = item["by_policy"]["quasar-dogi-hybrid"]
        lines.append(
            "| `{workload}` | {rows} | {failed} | {zones} | {wall} s | {dogi_waf} | {hybrid_waf} | {dogi_gc} | {hybrid_gc} | {dogi_stale} | {hybrid_stale} | {resets} |".format(
                workload=workload,
                rows=fmt_int(item["rows"]),
                failed=fmt_int(item["failed_rows"]),
                zones=fmt_int(item["logical_zones"]),
                wall=fmt_float(item["wall_time_s"], 3),
                dogi_waf=fmt_float(dogi_row["sim_waf"]),
                hybrid_waf=fmt_float(hybrid_row["sim_waf"]),
                dogi_gc=fmt_int(dogi_row["sim_gc_blocks"]),
                hybrid_gc=fmt_int(hybrid_row["sim_gc_blocks"]),
                dogi_stale=fmt_int(dogi_row["sim_stale_secret_blocks"]),
                hybrid_stale=fmt_int(hybrid_row["sim_stale_secret_blocks"]),
                resets=fmt_int(hybrid_row["physical_reset_commands"]),
            )
        )
    lines.extend(
        [
            "",
            "Actual-ZNS easy-to-pressure YCSB curve:",
            "",
            f"- Rows: `{ycsb_pressure_curve['row_count']}`, failed rows: `{ycsb_pressure_curve['failed_rows']}`",
            f"- WAF-pressure rows: `{ycsb_pressure_curve['waf_pressure_rows']}`",
            f"- Semantic-gap rows: `{ycsb_pressure_curve['semantic_gap_rows']}`",
            "",
            "| Workloads | PQC Level | DOGI WAF | Hybrid WAF | DOGI GC | Hybrid GC | DOGI Stale | Hybrid Stale | DOGI Resets | Hybrid Resets |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in ycsb_pressure_curve["rows"]:
        lines.append(
            "| {workloads} | {pqc} | {dogi_waf} | {hybrid_waf} | {dogi_gc} | {hybrid_gc} | {dogi_stale} | {hybrid_stale} | {dogi_resets} | {hybrid_resets} |".format(
                workloads=", ".join(f"`{workload}`" for workload in row.get("workloads", [])),
                pqc=fmt_int(row.get("pqc_level")),
                dogi_waf=fmt_float(row.get("dogi_waf")),
                hybrid_waf=fmt_float(row.get("hybrid_waf")),
                dogi_gc=fmt_int(row.get("dogi_gc_blocks")),
                hybrid_gc=fmt_int(row.get("hybrid_gc_blocks")),
                dogi_stale=fmt_int(row.get("dogi_stale_secret_blocks")),
                hybrid_stale=fmt_int(row.get("hybrid_stale_secret_blocks")),
                dogi_resets=fmt_int(row.get("dogi_semantic_resets")),
                hybrid_resets=fmt_int(row.get("hybrid_semantic_resets")),
            )
        )
    lines.extend(
        [
            "",
            "Curve reading: `pqc2000` is the negative WAF control; WAF is already 1.0, but storage-history baselines still miss semantic reset. `pqc4000/pqc6000/pqc8000/pqc10000` show where GC/WAF separation appears on the same actual ZNS path. The larger `pqc10000` rows keep the claim realistic: WAF does not universally explode, but stale-secret exposure remains large and QUASAR/hybrid keeps GC and stale secrets at zero.",
            "",
            "## Actual-ZNS Overhead",
            "",
            f"- Scope: {actual_zns_overhead['scope']}",
            f"- Artifacts: `{actual_zns_overhead['artifact_count']}`, rows: `{actual_zns_overhead['row_count']}`, failed rows: `{actual_zns_overhead['failed_rows']}`",
            f"- Caveat: {actual_zns_overhead['caveat']}",
            "",
            "| Policy | Append Cmds | Semantic Resets | Throughput MiB/s | Append Avg ms | Worst Append p99 ms | Reset Avg ms | CPU Median ns/write |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for policy in ["dogi-history", "quasar", "quasar-dogi-hybrid"]:
        row = actual_zns_overhead["by_policy"].get(policy, {})
        cpu = row.get("cpu_policy", {})
        lines.append(
            "| `{policy}` | {append_cmds} | {semantic_resets} | {throughput} | {append_avg} | {append_p99} | {reset_avg} | {cpu_ns} |".format(
                policy=policy,
                append_cmds=fmt_int(row.get("physical_append_commands")),
                semantic_resets=fmt_int(row.get("semantic_physical_reset_commands")),
                throughput=fmt_float(row.get("throughput_mib_s"), 2),
                append_avg=fmt_float((row.get("append_avg_ns") or 0) / 1_000_000, 3),
                append_p99=fmt_float((row.get("append_worst_p99_ns") or 0) / 1_000_000, 3),
                reset_avg=fmt_float((row.get("reset_avg_ns") or 0) / 1_000_000, 3),
                cpu_ns=fmt_float(cpu.get("median_ns_per_write"), 1),
            )
        )
    comparison = actual_zns_overhead["hybrid_vs_dogi"]
    lines.extend(
        [
            "",
            "Overhead reading:",
            "",
            f"- Hybrid/DOGI append-average latency ratio: `{fmt_float(comparison.get('append_avg_ratio'), 3)}`",
            f"- Hybrid/DOGI throughput ratio: `{fmt_float(comparison.get('throughput_ratio'), 3)}`",
            f"- Hybrid semantic reset delta: `{fmt_int(comparison.get('semantic_reset_delta'))}`",
            f"- Hybrid/DOGI C-level policy-decision median ratio: `{fmt_float(comparison.get('cpu_median_ns_ratio'), 3)}`",
            "",
            "Use this as overhead accounting, not as a final production latency claim, because the actual-ZNS replay uses zonefs helper appends/truncates.",
            "",
            "## xNVMe Raw ZNS Latency Probe",
            "",
            f"- Backend: `{xnvme_zns_latency['backend']}`",
            f"- Completed: `{xnvme_zns_latency['completed']}`",
            f"- Device: `{xnvme_zns_latency['device']}`",
            f"- Append count: `{xnvme_zns_latency['append_count']}`",
            f"- Caveat: {xnvme_zns_latency['caveat']}",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Append avg ns | {fmt_float(xnvme_zns_latency.get('append_avg_ns'), 1)} |",
            f"| Append p50 ns | {fmt_int(xnvme_zns_latency.get('append_p50_ns'))} |",
            f"| Append p95 ns | {fmt_int(xnvme_zns_latency.get('append_p95_ns'))} |",
            f"| Append p99 ns | {fmt_int(xnvme_zns_latency.get('append_p99_ns'))} |",
            f"| Append max ns | {fmt_int(xnvme_zns_latency.get('append_max_ns'))} |",
            f"| Reset before ns | {fmt_int(xnvme_zns_latency.get('reset_before_ns'))} |",
            f"| Reset after ns | {fmt_int(xnvme_zns_latency.get('reset_after_ns'))} |",
            f"| Throughput MiB/s | {fmt_float(xnvme_zns_latency.get('throughput_mib_s'), 2)} |",
            "",
            "This is the lower-overhead native command-path sanity check missing from the zonefs-helper overhead panel.",
            "",
            "## Security Claim Boundary",
            "",
            f"- Device: `{security_capability['device_model']}` firmware `{security_capability['firmware']}`",
            f"- SANICAP: `{security_capability['sanicap_hex']}`",
            f"- Sanitize supported: `{security_capability['sanitize_supported']}`",
            f"- Sanitize log status: `{security_capability['sanitize_log_status']}`",
            "",
            "| Operation | Advertised |",
            "| --- | --- |",
            f"| Crypto erase sanitize | `{security_capability['sanitize_operations_supported'].get('crypto_erase')}` |",
            f"| Block erase sanitize | `{security_capability['sanitize_operations_supported'].get('block_erase')}` |",
            f"| Overwrite sanitize | `{security_capability['sanitize_operations_supported'].get('overwrite')}` |",
            "",
            security_capability["claim_boundary"],
            "",
            "## Claim Matrix",
            "",
            f"- Claims: `{claim_matrix['claim_count']}`",
            f"- Status counts: `{claim_matrix['by_status']}`",
            "",
            "| Claim | Status | Caveat |",
            "| --- | --- | --- |",
        ]
    )
    for claim in claim_matrix["claims"]:
        lines.append(
            "| {claim} | `{status}` | {caveat} |".format(
                claim=claim.get("claim"),
                status=claim.get("status"),
                caveat=claim.get("caveat"),
            )
        )
    lines.extend(
        [
            "",
            "Forbidden overclaims: QUASAR always wins on WAF; zone reset alone proves physical erase; shared-namespace sanitize is per-zone epoch cleanup; helper-based zonefs latency is production p99; exact external baseline units are directly interchangeable with packed ZNS replay.",
        ]
    )
    ycsb_f_physical = fast_ycsb["physical"].get("ycsb-f-pqc8000", {})
    residual_physical_by_profile = {
        (row.get("workload"), row.get("profile") or "representative"): row
        for row in residual.get("physical_rows", [])
    }
    ycsb_f_low = residual_physical_by_profile.get(("ycsb-f-pqc8000", "low_overhead"), {})
    ycsb_f_balanced = residual_physical_by_profile.get(("ycsb-f-pqc8000", "balanced"), {})
    ycsb_f_strict_actual = residual_physical_by_profile.get(("ycsb-f-pqc8000", "strict_zero_wait"), {})
    ycsb_f_controller = {
        row.get("profile"): row.get("selected") or {}
        for row in residual.get("controller_decisions", [])
        if row.get("workload") == "ycsb-f-pqc8000"
    }
    if ycsb_f_physical:
        lines.extend(
            [
                "",
                "YCSB-F p8000 actual-ZNS hard-case ladder:",
                "",
                "| Scenario | Policy / Mode | Evidence | WAF | Secret Waiting End | Stale Secrets | Semantic Resets | Residual Blocks | Max Zones |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for policy in ["fifo", "sepbit-style", "midas-style", "dogi-history", "quasar-dogi-hybrid"]:
            row = ycsb_f_physical["by_policy"][policy]
            label = "QUASAR-DOGI clean" if policy == "quasar-dogi-hybrid" else policy
            lines.append(
                "| pressure, no straggler | `{label}` | actual ZNS | {waf} | {waiting} | {stale} | {resets} | {residual_blocks} | {max_zones} |".format(
                    label=label,
                    waf=fmt_float(row.get("sim_waf")),
                    waiting=fmt_int(row.get("secret_blocks_waiting_for_physical_reset")),
                    stale=fmt_int(row.get("sim_stale_secret_blocks")),
                    resets=fmt_int(row.get("physical_reset_commands")),
                    residual_blocks="N/A",
                    max_zones=fmt_int(row.get("max_live_physical_zones")),
                )
            )
        for policy in ["fifo", "sepbit-style", "midas-style", "dogi-history"]:
            row = ycsb_f_straggler_baselines.get("by_policy", {}).get(policy)
            if not row:
                continue
            lines.append(
                "| straggler baseline | `{label}` | actual ZNS | {waf} | {waiting} | {stale} | {resets} | {residual_blocks} | {max_zones} |".format(
                    label=policy,
                    waf=fmt_float(row.get("physical_waf")),
                    waiting=fmt_int(row.get("secret_blocks_waiting_for_physical_reset")),
                    stale=fmt_int(row.get("sim_stale_secret_blocks")),
                    resets=fmt_int(row.get("physical_reset_commands")),
                    residual_blocks="N/A",
                    max_zones=fmt_int(row.get("max_live_physical_zones")),
                )
            )
        if ycsb_f_low:
            lines.append(
                "| straggler, controller low-overhead | `QUASAR-DOGI low-overhead` | actual ZNS | {waf} | {waiting} | {stale} | {resets} | {residual_blocks} | {max_zones} |".format(
                    waf=fmt_float(ycsb_f_low.get("physical_waf")),
                    waiting=fmt_int(ycsb_f_low.get("secret_waiting_end")),
                    stale=fmt_int(ycsb_f_low.get("sim_stale_secret_blocks")),
                    resets=fmt_int(ycsb_f_low.get("physical_reset_commands")),
                    residual_blocks=fmt_int(ycsb_f_low.get("residual_migrated_blocks")),
                    max_zones=fmt_int(ycsb_f_low.get("max_live_physical_zones")),
                )
            )
        if ycsb_f_balanced:
            lines.append(
                "| straggler, controller balanced | `QUASAR-DOGI balanced` | actual ZNS | {waf} | {waiting} | {stale} | {resets} | {residual_blocks} | {max_zones} |".format(
                    waf=fmt_float(ycsb_f_balanced.get("physical_waf")),
                    waiting=fmt_int(ycsb_f_balanced.get("secret_waiting_end")),
                    stale=fmt_int(ycsb_f_balanced.get("sim_stale_secret_blocks")),
                    resets=fmt_int(ycsb_f_balanced.get("physical_reset_commands")),
                    residual_blocks=fmt_int(ycsb_f_balanced.get("residual_migrated_blocks")),
                    max_zones=fmt_int(ycsb_f_balanced.get("max_live_physical_zones")),
                )
            )
        strict = ycsb_f_strict_actual or ycsb_f_controller.get("strict_zero_wait", {})
        if strict:
            lines.append(
                "| straggler, controller strict | `QUASAR-DOGI strict-zero-wait` | {evidence} | {waf} | {waiting} | {stale} | {resets} | {residual_blocks} | {max_zones} |".format(
                    evidence="actual ZNS" if ycsb_f_strict_actual else "dry-run frontier",
                    waf=fmt_float(strict.get("physical_waf")),
                    waiting=fmt_int(strict.get("secret_waiting_end")),
                    stale=fmt_int(strict.get("sim_stale_secret_blocks")),
                    resets=fmt_int(strict.get("physical_reset_commands")),
                    residual_blocks=fmt_int(strict.get("residual_migrated_blocks")),
                    max_zones=fmt_int(strict.get("max_live_physical_zones")),
                )
            )
        lines.extend(
            [
                "",
                "YCSB-F interpretation: WAF alone is misleading. MiDAS/SepBIT/DOGI can keep WAF close to 1.0 while leaving tens of thousands of secret blocks waiting and issuing no semantic resets. QUASAR-DOGI clean mode removes exposure; under stragglers, the controller explicitly trades WAF/copy cost for bounded or zero waiting.",
            ]
        )
    lines.extend(
        [
            "",
            "## Adaptive Policy Audit",
            "",
            f"- Scope: {adaptive['scope']}",
            f"- Default policy: `{adaptive['default_policy']}`",
            f"- Candidate policy: `{adaptive['candidate_policy']}`",
            f"- Decision: `{adaptive['decision']}`",
            f"- Reason: {adaptive['decision_reason']}",
            "",
            "| Suite | Current Hybrid Wins | Adaptive Hybrid Wins | Ties |",
            "| --- | ---: | ---: | ---: |",
            "| FAST/YCSB pressure | {current} | {adaptive_wins} | {ties} |".format(
                current=fmt_int(adaptive["ycsb_pressure"].get("current_wins")),
                adaptive_wins=fmt_int(adaptive["ycsb_pressure"].get("adaptive_wins")),
                ties=fmt_int(adaptive["ycsb_pressure"].get("ties")),
            ),
            "| Sysbench pressure | {current} | {adaptive_wins} | {ties} |".format(
                current=fmt_int(adaptive["sysbench_pressure"].get("current_wins")),
                adaptive_wins=fmt_int(adaptive["sysbench_pressure"].get("adaptive_wins")),
                ties=fmt_int(adaptive["sysbench_pressure"].get("ties")),
            ),
            "",
            "## Multi-Tenant Tenant-Isolation Mode",
            "",
            f"- Scope: {multitenant['scope']}",
            f"- Decision: `{multitenant['decision']}`",
            "",
            "| Workload | Policy | WAF | GC Blocks | Stale Secrets | Reset Secret Tenant Impurity | Families |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for workload, item in multitenant["simulator"].items():
        for label, key in [
            ("DOGI-style", "dogi"),
            ("Current hybrid", "current"),
            ("Tenant-isolation mode", "tenant_isolation"),
        ]:
            row = item[key]
            lines.append(
                "| `{workload}` | {label} | {waf} | {gc} | {stale} | {tenant_imp} | {families} |".format(
                    workload=workload,
                    label=label,
                    waf=fmt_float(row.get("waf")),
                    gc=fmt_int(row.get("gc_write_blocks")),
                    stale=fmt_int(row.get("stale_secret_blocks_remaining")),
                    tenant_imp=fmt_float(row.get("reset_secret_tenant_impurity"), 3),
                    families=fmt_int(row.get("quasar_family_count")),
                )
            )
    physical = multitenant["physical"]
    lines.extend(
        [
            "",
            "Representative physical multi-tenant replay:",
            "",
            "| Policy | WAF | GC Blocks | Stale Secrets | Semantic Resets | Secret Waiting End | Reset Secret Tenant Impurity | Avg Util | Max Live Phys Zones | Families |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for policy, label in [
        ("dogi-history", "DOGI-style"),
        ("quasar-dogi-hybrid", "Current hybrid"),
        ("quasar-adaptive-hybrid", "Tenant-isolation mode"),
    ]:
        row = physical["by_policy"][policy]
        lines.append(
            "| {label} | {waf} | {gc} | {stale} | {resets} | {wait} | {tenant_imp} | {util} | {zones} | {families} |".format(
                label=label,
                waf=fmt_float(row.get("sim_waf")),
                gc=fmt_int(row.get("sim_gc_blocks")),
                stale=fmt_int(row.get("sim_stale_secret_blocks")),
                resets=fmt_int(row.get("physical_reset_commands")),
                wait=fmt_int(row.get("secret_blocks_waiting_for_physical_reset")),
                tenant_imp=fmt_float(row.get("reset_secret_tenant_impurity"), 3),
                util=fmt_float(row.get("avg_space_utilization"), 3),
                zones=fmt_int(row.get("max_live_physical_zones")),
                families=fmt_int(row.get("quasar_family_count")),
            )
        )
    lines.extend(
        [
            "",
            "## Physical Hint Robustness",
            "",
            f"- Scope: {robustness['scope']}",
            f"- Trace: `{robustness['trace']}`",
            f"- Device limits: `mar={robustness['device_limits'].get('mar')}`, `mor={robustness['device_limits'].get('mor')}`",
            f"- Decision: `{robustness['decision']}`",
            "",
            "| Case | Sim WAF | Physical WAF | GC Blocks | Stale Secrets | Secret Waiting End | Physical Resets | Residual Blocks | Max Live Phys Zones | Max Pack Keys | Failed Rows |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    robustness_rows = [
        ("DOGI clean", robustness["clean"].get("dogi", {}), robustness["clean"].get("failed_rows")),
        ("Hybrid clean", robustness["clean"].get("hybrid", {}), robustness["clean"].get("failed_rows")),
        (
            "Hybrid missing hints 5%",
            robustness["missing_hint_5pct"].get("hybrid", {}),
            robustness["missing_hint_5pct"].get("failed_rows"),
        ),
        (
            "Hybrid wrong epoch 5%",
            robustness["wrong_epoch_5pct"].get("hybrid", {}),
            robustness["wrong_epoch_5pct"].get("failed_rows"),
        ),
        (
            "Hybrid straggler 5%, secret-group",
            robustness["straggler_5pct_exact_secret_group"].get("hybrid", {}),
            robustness["straggler_5pct_exact_secret_group"].get("failed_rows"),
        ),
        (
            "Hybrid straggler 5%, epoch-bin-4",
            robustness["straggler_5pct_epoch_bin_4"].get("hybrid", {}),
            robustness["straggler_5pct_epoch_bin_4"].get("failed_rows"),
        ),
        (
            "Hybrid straggler 5%, epoch-bin-5 + residual",
            robustness["straggler_5pct_epoch_bin_5_residual_12288"].get("hybrid", {}),
            robustness["straggler_5pct_epoch_bin_5_residual_12288"].get("failed_rows"),
        ),
    ]
    for label, row, failed_rows in robustness_rows:
        lines.append(
            "| {label} | {waf} | {physical_waf} | {gc} | {stale} | {wait} | {resets} | {residual_blocks} | {zones} | {keys} | {failed} |".format(
                label=label,
                waf=fmt_float(row.get("sim_waf")),
                physical_waf=fmt_float(row.get("physical_waf")),
                gc=fmt_int(row.get("sim_gc_blocks")),
                stale=fmt_int(row.get("sim_stale_secret_blocks")),
                wait=fmt_int(row.get("secret_waiting_end")),
                resets=fmt_int(row.get("physical_reset_commands")),
                residual_blocks=fmt_int(row.get("residual_migrated_blocks")),
                zones=fmt_int(row.get("max_live_physical_zones")),
                keys=fmt_int(row.get("max_active_pack_keys")),
                failed=fmt_int(failed_rows),
            )
        )
    lines.extend(
        [
            "",
            f"Robustness interpretation: {robustness['decision_reason']}",
            "",
            "## Residual Fallback Frontier",
            "",
            f"- Scope: {residual['scope']}",
            f"- Decision: `{residual['decision']}`",
            f"- Dry-run rows: `{residual['dryrun_row_count']}`",
            "",
            "| Workload | Best Zero-Wait Candidate | Physical WAF | Residual Blocks | Max Zones | Actual ZNS Representative |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    physical_by_profile = {
        (row.get("workload"), row.get("profile") or "representative"): row
        for row in residual["physical_rows"]
    }
    physical_by_workload: dict[str, list[dict[str, Any]]] = {}
    for row in residual["physical_rows"]:
        physical_by_workload.setdefault(row.get("workload"), []).append(row)

    def physical_frontier_text(workload: str) -> str:
        if workload == "ycsb-f-pqc8000":
            parts = []
            for profile in ["low_overhead", "balanced", "strict_zero_wait"]:
                row = physical_by_profile.get((workload, profile))
                if not row:
                    continue
                parts.append(
                    "{profile}: `{packing}`, th={threshold}, WAF {waf}, waiting {waiting}".format(
                        profile=profile,
                        packing=row.get("packing"),
                        threshold=row.get("threshold"),
                        waf=fmt_float(row.get("physical_waf")),
                        waiting=fmt_int(row.get("secret_waiting_end")),
                    )
                )
            return "; ".join(parts) if parts else "not run"
        rows = physical_by_workload.get(workload, [])
        if not rows:
            return "not run"
        row = rows[0]
        return (
            f"`{row.get('packing')}`, th={row.get('threshold')}, "
            f"physical WAF {fmt_float(row.get('physical_waf'))}, "
            f"waiting {fmt_int(row.get('secret_waiting_end'))}"
        )

    for workload, item in sorted(residual["best_candidates"].items()):
        best = (item.get("best_zero_wait") or [{}])[0]
        lines.append(
            "| `{workload}` | `{packing}`, th={threshold} | {waf} | {residual_blocks} | {max_z} | {physical_text} |".format(
                workload=workload,
                packing=best.get("packing", "N/A"),
                threshold=best.get("threshold", "N/A"),
                waf=fmt_float(best.get("physical_waf")),
                residual_blocks=fmt_int(best.get("residual_migrated_blocks")),
                max_z=fmt_int(best.get("max_live_physical_zones")),
                physical_text=physical_frontier_text(workload),
            )
        )
    lines.extend(
        [
            "",
            "Residual interpretation: expose residual migration as a strict-exposure mode. It is practical for Exchange/Sysbench-style pressure but too expensive to make unconditional for every YCSB-F-like workload.",
        ]
    )
    if residual.get("budget_rows"):
        lines.extend(
            [
                "",
                "Bounded-overhead residual budget curve:",
                "",
                "| Workload | Packing | Threshold | Copy Budget | Physical WAF | Secret Waiting End | Residual Blocks | Budget Skips |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in sorted(
            residual["budget_rows"],
            key=lambda row: (row.get("workload", ""), row.get("packing", ""), int(row.get("copy_budget") or 0)),
        ):
            lines.append(
                "| `{workload}` | `{packing}` | {threshold} | {budget} | {waf} | {waiting} | {residual_blocks} | {skips} |".format(
                    workload=row.get("workload"),
                    packing=row.get("packing"),
                    threshold=fmt_int(row.get("threshold")),
                    budget=fmt_int(row.get("copy_budget")),
                    waf=fmt_float(row.get("physical_waf")),
                    waiting=fmt_int(row.get("secret_waiting_end")),
                    residual_blocks=fmt_int(row.get("residual_migrated_blocks")),
                    skips=fmt_int(row.get("residual_migration_budget_skips")),
                )
            )
        lines.extend(
            [
                "",
                "Budget interpretation: copy budget is the deployable low-overhead knob. It caps WAF/copy cost and reports the stale-secret exposure it leaves behind, while strict zero-wait mode remains available for high-assurance deployments.",
            ]
        )
    if residual.get("budget_physical_rows"):
        lines.extend(
            [
                "",
                "Actual-ZNS bounded-overhead residual budget curve:",
                "",
                "| Workload | Packing | Threshold | Copy Budget | Physical WAF | Secret Waiting End | Residual Blocks | Budget Skips | Resets | Max Zones |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in sorted(
            residual["budget_physical_rows"],
            key=lambda row: (row.get("workload", ""), row.get("packing", ""), int(row.get("copy_budget") or 0)),
        ):
            lines.append(
                "| `{workload}` | `{packing}` | {threshold} | {budget} | {waf} | {waiting} | {residual_blocks} | {skips} | {resets} | {max_z} |".format(
                    workload=row.get("workload"),
                    packing=row.get("packing"),
                    threshold=fmt_int(row.get("threshold")),
                    budget=fmt_int(row.get("copy_budget")),
                    waf=fmt_float(row.get("physical_waf")),
                    waiting=fmt_int(row.get("secret_waiting_end")),
                    residual_blocks=fmt_int(row.get("residual_migrated_blocks")),
                    skips=fmt_int(row.get("residual_migration_budget_skips")),
                    resets=fmt_int(row.get("physical_reset_commands")),
                    max_z=fmt_int(row.get("max_live_physical_zones")),
                )
            )
    if residual.get("controller_decisions"):
        lines.extend(
            [
                "",
                "Residual policy controller selections:",
                "",
                "| Workload | Profile | Mode | Packing | Threshold | Recommended Copy Budget | Physical WAF | Secret Waiting End |",
                "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for decision in sorted(
            residual["controller_decisions"],
            key=lambda row: (row.get("workload", ""), row.get("profile", "")),
        ):
            selected = decision.get("selected") or {}
            budget = selected.get("recommended_copy_budget")
            lines.append(
                "| `{workload}` | `{profile}` | `{mode}` | `{packing}` | {threshold} | {budget} | {waf} | {waiting} |".format(
                    workload=decision.get("workload"),
                    profile=decision.get("profile"),
                    mode=selected.get("mode", "none"),
                    packing=selected.get("packing", "N/A"),
                    threshold=fmt_int(selected.get("threshold")),
                    budget="unbounded" if budget is None else fmt_int(budget),
                    waf=fmt_float(selected.get("physical_waf")),
                    waiting=fmt_int(selected.get("secret_waiting_end")),
                )
            )
        lines.extend(
            [
                "",
                "Controller interpretation: low-overhead mode can leave bounded exposure, balanced mode chooses a finite copy budget or threshold-only residual point, and strict mode keeps the zero-wait option explicit.",
            ]
        )
    lines.extend(
        [
            "",
            "## Exact External Baselines",
            "",
            "These are strong sanity checks, not direct apples-to-apples throughput comparisons with QUASAR's packed ZNS replay.",
            "",
            "| Artifact | Scope | Main Result | Caveat |",
            "| --- | --- | --- | --- |",
        ]
    )
    dogi = exact["dogi_physical_compact"]
    dogi_pressure = exact["dogi_physical_dynamic_pressure"]
    dogi_pressure_suite = exact["dogi_physical_dynamic_pressure_suite"]
    dogi_original_lba = exact["dogi_physical_original_lba_pressure"]
    midas = exact["midas_memory_repeat4"]
    sepbit = exact["sepbit_repeat4"]
    lines.append(
        "| Exact DOGI physical compact | {scope} | aggregate WAF `{waf}`, avg WAF `{avg}`, user `{user}` GiB, GC `{gc}` GiB | {caveat} |".format(
            scope=dogi["scope"],
            waf=fmt_float(dogi["aggregate_waf"], 3),
            avg=fmt_float(dogi["avg_waf"], 3),
            user=fmt_float(dogi["total_user_write_gib"], 3),
            gc=fmt_float(dogi["total_gc_write_gib"], 3),
            caveat=dogi["caveat"],
        )
    )
    lines.append(
        "| Exact DOGI Alibaba p8000 physical compact | {scope} | WAF `{waf}`, user `{user}` GiB, GC `{gc}` GiB, selection `{selection}` | {caveat} |".format(
            scope=dogi_pressure["scope"],
            waf=fmt_float(dogi_pressure["waf"], 3),
            user=fmt_float(dogi_pressure["user_write_gib"], 3),
            gc=fmt_float(dogi_pressure["gc_write_gib"], 3),
            selection=dogi_pressure["selection_algorithm"],
            caveat=dogi_pressure["caveat"],
        )
    )
    lines.append(
        "| Exact DOGI-family Alibaba p8000 suite | {scope} | completed `{completed}/{total}`, best `{best}` WAF `{waf}` | {caveat} |".format(
            scope=dogi_pressure_suite["scope"],
            completed=dogi_pressure_suite["completed_runs"],
            total=dogi_pressure_suite["total_runs"],
            best=dogi_pressure_suite["best_placement"],
            waf=fmt_float(dogi_pressure_suite["best_waf"], 3),
            caveat=dogi_pressure_suite["caveat"],
        )
    )
    lines.append(
        "| Exact DOGI Alibaba p8000 original-LBA | {scope} | completed `{completed}`, WAF `{waf}`, user `{user}` GiB, GC `{gc}` GiB | {caveat} |".format(
            scope=dogi_original_lba["scope"],
            completed=str(bool(dogi_original_lba["completed"])).lower(),
            waf=fmt_float(dogi_original_lba["waf"], 3),
            user=fmt_float(dogi_original_lba["user_write_gib"], 3),
            gc=fmt_float(dogi_original_lba["gc_write_gib"], 3),
            caveat=dogi_original_lba["caveat"],
        )
    )
    lines.append(
        "| Exact MiDAS memory repeat4 | {scope} | total WAF `{waf}`, recomputed WAF `{rwaf}` | {caveat} |".format(
            scope=midas["scope"],
            waf=fmt_float(midas["total_waf"], 3),
            rwaf=fmt_float(midas["recomputed_waf_from_dataw_gcdw"], 3),
            caveat=midas["caveat"],
        )
    )
    lines.append(
        "| Exact SepBIT repeat4 | {scope} | SepBIT WA `{wa}`, NoSep WA `{nosep}` | {caveat} |".format(
            scope=sepbit["scope"],
            wa=fmt_float(sepbit["wa"], 3),
            nosep=fmt_float(sepbit["nosep_wa"], 3),
            caveat=sepbit["caveat"],
        )
    )
    lines.extend(
        [
            "",
            "## Claim Boundary",
            "",
            "- Do not claim QUASAR dominates MiDAS/DOGI/SepBIT on every workload or in every unit system.",
            "- The strongest supported claim is narrower and cleaner: when PQC objects have protocol-known death cohorts, QUASAR-DOGI hybrid exposes that missing signal to placement and reset scheduling.",
            "- MiDAS exact remaining strong on repeat4 is useful: it prevents overclaiming and pushes the paper toward semantic reset/exposure plus pressure-dependent WAF.",
            "- Original-LBA exact DOGI now completes for Alibaba p8000; compact exact DOGI remains useful for multi-workload and placement-variant coverage.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--physical-fairness",
        type=Path,
        default=Path("artifacts/results/packed-physical-zonefs-replay-dogi-paper-pqc2000-z512-secret-group-helper.json"),
    )
    parser.add_argument(
        "--fast-db",
        type=Path,
        default=Path("artifacts/results/fast-db-pressure/sysbench-pressure-summary.json"),
    )
    parser.add_argument(
        "--fast-ycsb",
        type=Path,
        default=Path("artifacts/results/fast-ycsb-pressure/ycsb-pressure-summary.json"),
    )
    parser.add_argument(
        "--ycsb-pressure-curve",
        type=Path,
        default=Path("artifacts/results/fast-ycsb-pressure/ycsb-actual-zns-pressure-curve.json"),
    )
    parser.add_argument(
        "--actual-zns-overhead",
        type=Path,
        default=Path("artifacts/results/actual-zns-overhead-summary.json"),
    )
    parser.add_argument(
        "--xnvme-zns-latency",
        type=Path,
        default=Path("artifacts/results/xnvme-zns-latency/summary.json"),
    )
    parser.add_argument(
        "--security-capability",
        type=Path,
        default=Path("artifacts/results/physical-zns-security-capability.json"),
    )
    parser.add_argument(
        "--claim-matrix",
        type=Path,
        default=Path("artifacts/results/quasar-claim-matrix.json"),
    )
    parser.add_argument(
        "--workload-hardness",
        type=Path,
        default=Path("artifacts/results/workload-hardness-matrix.json"),
    )
    parser.add_argument(
        "--deployment-selector",
        type=Path,
        default=Path("artifacts/results/quasar-deployment-policy-selector.json"),
    )
    parser.add_argument(
        "--reproducibility-manifest",
        type=Path,
        default=Path("artifacts/results/quasar-reproducibility-manifest.json"),
    )
    parser.add_argument(
        "--reproducibility-validation",
        type=Path,
        default=Path("artifacts/results/quasar-reproducibility-validation.json"),
    )
    parser.add_argument(
        "--ycsb-f-straggler-baselines",
        type=Path,
        default=Path(
            "artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc8000-straggler005-baselines-helper.json"
        ),
    )
    parser.add_argument(
        "--adaptive-comparison",
        type=Path,
        default=Path("artifacts/results/adaptive-policy-comparison.json"),
    )
    parser.add_argument(
        "--multitenant-pressure",
        type=Path,
        default=Path("artifacts/results/multitenant-pressure/multitenant-pressure-summary.json"),
    )
    parser.add_argument(
        "--physical-robustness",
        type=Path,
        default=Path("artifacts/results/physical-robustness-ycsb-a-pqc4000/summary.json"),
    )
    parser.add_argument(
        "--residual-fallback-sweep",
        type=Path,
        default=Path("artifacts/results/residual-fallback-sweep/summary.json"),
    )
    parser.add_argument(
        "--dogi-exact",
        type=Path,
        default=Path("artifacts/results/dogi-physical-zns-full-pqc2000-compact-lg2/summary.json"),
    )
    parser.add_argument(
        "--dogi-pressure-exact",
        type=Path,
        default=Path("artifacts/results/dogi-exact/alibaba-pqc8000-dogi.json"),
    )
    parser.add_argument(
        "--dogi-pressure-suite",
        type=Path,
        default=Path("artifacts/results/dogi-exact/alibaba-pqc8000-suite.json"),
    )
    parser.add_argument(
        "--dogi-original-lba",
        type=Path,
        default=Path("artifacts/results/dogi-exact/alibaba-pqc8000-original-lba-dogi-cwd-app.json"),
    )
    parser.add_argument(
        "--midas-exact",
        type=Path,
        default=Path("artifacts/results/midas-exact/exchange-pqc2000-repeat4-compact.json"),
    )
    parser.add_argument(
        "--sepbit-exact",
        type=Path,
        default=Path("artifacts/results/sepbit-exact/exchange-pqc2000-repeat4-compact-sepbit.json"),
    )
    parser.add_argument(
        "--nosep-exact",
        type=Path,
        default=Path("artifacts/results/sepbit-exact/exchange-pqc2000-repeat4-compact-nosep.json"),
    )
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/unified-baseline-comparison.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/unified-baseline-comparison.md"))
    args = parser.parse_args()

    summary = {
        "same_path_physical_zns": summarize_physical_fairness(load_json(args.physical_fairness)),
        "fast_db_pressure": summarize_fast_db(load_json(args.fast_db)),
        "fast_ycsb_pressure": summarize_fast_ycsb(load_json(args.fast_ycsb)),
        "ycsb_pressure_curve": summarize_ycsb_pressure_curve(load_json(args.ycsb_pressure_curve)),
        "actual_zns_overhead": summarize_actual_zns_overhead(load_json(args.actual_zns_overhead)),
        "xnvme_zns_latency": summarize_xnvme_zns_latency(load_json(args.xnvme_zns_latency)),
        "security_capability": summarize_security_capability(load_json(args.security_capability)),
        "claim_matrix": summarize_claim_matrix(load_json(args.claim_matrix)),
        "workload_hardness": summarize_workload_hardness(load_json(args.workload_hardness)),
        "deployment_selector": summarize_deployment_selector(load_json(args.deployment_selector)),
        "reproducibility_manifest": summarize_reproducibility_manifest(load_json(args.reproducibility_manifest)),
        "reproducibility_validation": summarize_reproducibility_validation(load_json(args.reproducibility_validation)),
        "ycsb_f_straggler_baselines": summarize_ycsb_f_straggler_baselines(
            load_json(args.ycsb_f_straggler_baselines)
        ),
        "adaptive_policy_comparison": summarize_adaptive(load_json(args.adaptive_comparison)),
        "multitenant_pressure": summarize_multitenant(load_json(args.multitenant_pressure)),
        "physical_robustness": summarize_physical_robustness(load_json(args.physical_robustness)),
        "residual_fallback_sweep": summarize_residual_fallback(load_json(args.residual_fallback_sweep)),
        "exact_external_baselines": summarize_exact_baselines(
            load_json(args.dogi_exact),
            load_json(args.dogi_pressure_exact),
            load_json(args.dogi_pressure_suite),
            load_json(args.dogi_original_lba),
            load_json(args.midas_exact),
            load_json(args.sepbit_exact),
            load_json(args.nosep_exact),
        ),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "markdown_out": str(args.markdown_out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
