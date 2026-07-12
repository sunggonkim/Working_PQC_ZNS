#!/usr/bin/env python3
"""Audit progress toward the full actual-ZNS baseline-vs-QUASAR goal.

This report is stricter than the claim matrix. It asks whether the user's full
goal has current evidence, where the evidence is scoped, and which experiments
would still strengthen the result. The goal is to avoid quietly redefining
"perfect comparison" around only the artifacts that already exist.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def item(
    requirement: str,
    status: str,
    evidence: list[str],
    remaining: str,
    next_action: str,
) -> dict[str, Any]:
    return {
        "requirement": requirement,
        "status": status,
        "evidence": evidence,
        "remaining": remaining,
        "next_action": next_action,
    }


def sanitize_validated(security: dict[str, Any]) -> bool:
    return bool(security.get("sanitize_execution_validated") or security.get("crypto_erase_executed"))


def xnvme_latency_validated(xnvme: dict[str, Any]) -> bool:
    return bool(
        xnvme.get("completed")
        and xnvme.get("append_count", 0) >= 1024
        and xnvme.get("append_p99_ns", 0) > 0
        and xnvme.get("mounted_after") is True
        and xnvme.get("nonempty_after_lines") == 0
    )


def real_app_block_trace_validated(real_app: dict[str, Any]) -> bool:
    blktrace = real_app.get("blktrace", {})
    pqc = real_app.get("pqc_side_writer", {})
    sysbench = real_app.get("sysbench", {})
    return bool(
        real_app.get("artifact") == "real-app-sysbench-pqc-block-trace"
        and blktrace.get("event_lines", 0) >= 10_000
        and blktrace.get("write_events", 0) > 0
        and pqc.get("sessions_completed", 0) >= 32
        and pqc.get("records", 0) >= 96
        and pqc.get("all_kem_ok") is True
        and pqc.get("all_sig_ok") is True
        and sysbench.get("elapsed_s", 0.0) > 0.0
        and "real sysbench fileio" in real_app.get("claim", "")
    )


def production_blocker(name: str, evidence: list[str], required_to_close: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "open",
        "evidence": evidence,
        "required_to_close": required_to_close,
    }


BLOCKER_LABELS = {
    "full_public_dogi_end_to_end_parity": "full public-DOGI end-to-end parity",
    "spdk_or_zenfs_tail_latency": "SPDK/ZenFS tail latency",
    "physical_fdp_or_faithful_emulator_replay": "physical FDP or faithful-emulator replay",
    "per_cohort_physical_erase_scope": "per-cohort physical erase scope",
    "real_application_block_traces": "real application block traces",
    "device_diversity": "device diversity",
}


def fast_r2_production_blockers(
    unified: dict[str, Any],
    readiness: dict[str, Any],
    real_app_block_trace: dict[str, Any],
) -> list[dict[str, Any]]:
    """List fatal Reviewer-2 blockers for a production-grade FAST claim.

    These blockers are stricter than the scoped paper claim.  They prevent the
    audit from declaring the broader goal complete just because same-path ZNS
    replay, xNVMe probing, and sanitize command-path evidence exist.
    """

    components = readiness.get("components", {})
    dogi_parity = components.get("dogi_public_parity", {})
    zns_fdp = components.get("zns_fdp_replay", {})
    security = unified.get("security_capability", {})
    exact = unified.get("exact_external_baselines", {})
    fdp_modeled = any(
        claim.get("claim", "").startswith("FDP can carry")
        for claim in unified.get("claim_matrix", {}).get("claims", [])
    )
    blockers = [
        production_blocker(
            "full_public_dogi_end_to_end_parity",
            [
                f"dogi_public_parity_status={dogi_parity.get('status')}",
                "same-path DOGI-style is apples-to-apples replay, not the public DOGI stack",
                f"public DOGI original-LBA WAF={exact.get('dogi_physical_original_lba_pressure', {}).get('waf')}",
            ],
            "Run DOGI and QUASAR through the same app/ZenFS/SPDK or equivalent stack with identical trace units.",
        ),
        production_blocker(
            "spdk_or_zenfs_tail_latency",
            [
                f"zns_component_status={zns_fdp.get('status')}",
                f"xnvme_probe_present={bool(unified.get('xnvme_zns_latency', {}).get('completed'))}",
                "zonefs helper replay is accounting evidence, not poll-mode p99 latency",
            ],
            "Implement SPDK/ZenFS or true async xNVMe replay and report p95/p99 append/reset service latency.",
        ),
        production_blocker(
            "physical_fdp_or_faithful_emulator_replay",
            [
                f"fdp_trace_model_present={fdp_modeled}",
                "current FDP evidence is handle-collision/purity modeling only",
            ],
            "Run the QUASAR family-to-handle policy on FDP hardware or a faithful FDP emulator.",
        ),
        production_blocker(
            "per_cohort_physical_erase_scope",
            [
                f"sanitize_execution_validated={security.get('sanitize_execution_validated')}",
                f"crypto_erase_executed={security.get('crypto_erase_executed')}",
                "shared-namespace sanitize is destructive and not a per-zone/per-epoch cleanup primitive",
            ],
            (
                "Demonstrate a dedicated namespace/media pool, per-cohort key isolation, "
                "or hardware per-zone erase semantics whose blast radius matches the cohort."
            ),
        ),
        production_blocker(
            "device_diversity",
            [
                "physical measurements are scoped to one WD ZN540-class ZNS SSD",
                "device-specific reset/sanitize/FDP behavior is not generalized",
            ],
            "Repeat append/reset/security/FDP evidence on at least one additional ZNS or FDP-capable device.",
        ),
    ]
    if not real_app_block_trace_validated(real_app_block_trace):
        blockers.insert(
            -1,
            production_blocker(
                "real_application_block_traces",
                [
                    "Sysbench/MySQL is currently an execution/readiness gate",
                    "DOGI-shaped YCSB/Sysbench carriers are generated pressure traces",
                ],
                "Capture MySQL/Sysbench, RocksDB/YCSB, KMS, or audit-service block traces with PQC lifecycle side writes.",
            ),
        )
    return blockers


def build_audit(
    unified: dict[str, Any],
    readiness: dict[str, Any],
    acceptance: dict[str, Any],
    validation: dict[str, Any],
    pipeline_manifest: dict[str, Any],
    real_app_block_trace: dict[str, Any],
) -> dict[str, Any]:
    same = unified["same_path_physical_zns"]
    ycsb = unified["ycsb_pressure_curve"]
    db = unified["fast_db_pressure"]
    exact = unified["exact_external_baselines"]
    hardness = unified["workload_hardness"]
    claim_gate = next((entry for entry in hardness.get("entries", []) if entry.get("tier") == "claim-gate"), {})
    claim_gate_evidence = claim_gate.get("evidence", {})
    main_claim_gate_passed = bool(
        claim_gate.get("passed")
        and claim_gate_evidence.get("eligible_ycsb_pressure_rows", 0) >= 3
        and claim_gate_evidence.get("ycsb_baseline_complete_rows", 0) >= 3
        and claim_gate_evidence.get("db_pressure_eligible") is True
        and claim_gate_evidence.get("eligible_dynamic_rows", 0) >= 2
        and claim_gate_evidence.get("dynamic_baseline_complete_rows", 0) >= 2
    )
    selector = unified["deployment_selector"]
    overhead = unified["actual_zns_overhead"]
    xnvme = unified.get("xnvme_zns_latency", {})
    security = unified["security_capability"]

    same_policies = same.get("by_policy", {})
    required_same_policies = {
        "fifo",
        "sepbit-style",
        "midas-style",
        "dogi-history",
        "quasar",
        "quasar-dogi-hybrid",
    }
    missing_same = sorted(required_same_policies - set(same_policies))

    requirements = [
        item(
            "Run the main comparison on a real ZNS path with FIFO/SepBIT/MiDAS/DOGI-style baselines and QUASAR.",
            "satisfied" if same.get("failed_rows") == 0 and same.get("rows", 0) >= 72 and not missing_same else "missing",
            [
                f"same-path actual-ZNS rows={same.get('rows')} failed={same.get('failed_rows')}",
                f"policies={sorted(same_policies)}",
                f"hybrid resets={same_policies.get('quasar-dogi-hybrid', {}).get('physical_reset_commands')}",
                f"DOGI stale secrets={same_policies.get('dogi-history', {}).get('sim_stale_secret_blocks')}",
                f"hybrid stale secrets={same_policies.get('quasar-dogi-hybrid', {}).get('sim_stale_secret_blocks')}",
            ],
            "Exact external DOGI/MiDAS/SepBIT units are still separate from this same-path packed replay.",
            "Keep this as the apples-to-apples physical ZNS comparison; do not mix units with exact external runs.",
        ),
        item(
            "Show the workload is not an easy QUASAR-only construction.",
            "satisfied"
            if hardness.get("passed")
            and hardness.get("passed_entries") == hardness.get("total_entries")
            and main_claim_gate_passed
            else "missing",
            [
                f"hardness={hardness.get('passed_entries')}/{hardness.get('total_entries')}",
                f"tiers={hardness.get('by_tier')}",
                f"main-claim gate={main_claim_gate_passed}",
                f"eligible YCSB pressure rows={claim_gate_evidence.get('eligible_ycsb_pressure_rows')}",
                f"YCSB baseline-complete rows={claim_gate_evidence.get('ycsb_baseline_complete_rows')}",
                f"DB pressure eligible={claim_gate_evidence.get('db_pressure_eligible')}",
                f"eligible dynamic rows={claim_gate_evidence.get('eligible_dynamic_rows')}",
                f"dynamic baseline-complete rows={claim_gate_evidence.get('dynamic_baseline_complete_rows')}",
            ],
            "None for the current scoped claim.",
            "Use the DOGI-favorable p0 control and YCSB p2000 negative control in the paper narrative.",
        ),
        item(
            "Demonstrate pressure cases where WAF/GC separation appears, not only stale-secret separation.",
            "satisfied"
            if ycsb.get("waf_pressure_rows", 0) >= 3 and db.get("hybrid_vs_dogi", {}).get("gc_reduction", 0.0) >= 0.75
            else "weak",
            [
                f"YCSB pressure rows={ycsb.get('waf_pressure_rows')}/{ycsb.get('row_count')}",
                f"YCSB semantic-gap rows={ycsb.get('semantic_gap_rows')}/{ycsb.get('row_count')}",
                f"Sysbench GC reduction={db.get('hybrid_vs_dogi', {}).get('gc_reduction')}",
                f"Sysbench stale secrets removed={db.get('hybrid_vs_dogi', {}).get('stale_secret_reduction_blocks')}",
            ],
            "None for the current scoped claim; larger p10000 actual-ZNS YCSB pressure points have been added.",
            "Add more min-free-zone sweeps only if reviewers demand a smoother hardware curve.",
        ),
        item(
            "Include exact external DOGI/MiDAS/SepBIT evidence without pretending the units are identical.",
            "qualified"
            if exact.get("dogi_physical_compact", {}).get("completed")
            and exact.get("dogi_physical_dynamic_pressure_suite", {}).get("completed_runs")
            == exact.get("dogi_physical_dynamic_pressure_suite", {}).get("total_runs")
            and exact.get("dogi_physical_original_lba_pressure", {}).get("completed")
            and exact.get("midas_memory_repeat4", {}).get("completed")
            and exact.get("sepbit_repeat4", {}).get("completed")
            else "missing",
            [
                f"DOGI exact compact WAF={exact.get('dogi_physical_compact', {}).get('aggregate_waf')}",
                "DOGI exact Alibaba p8000 suite="
                f"{exact.get('dogi_physical_dynamic_pressure_suite', {}).get('completed_runs')}/"
                f"{exact.get('dogi_physical_dynamic_pressure_suite', {}).get('total_runs')}, "
                f"best={exact.get('dogi_physical_dynamic_pressure_suite', {}).get('best_placement')} "
                f"WAF={exact.get('dogi_physical_dynamic_pressure_suite', {}).get('best_waf')}",
                "DOGI exact original-LBA Alibaba p8000 "
                f"WAF={exact.get('dogi_physical_original_lba_pressure', {}).get('waf')}",
                f"MiDAS exact WAF={exact.get('midas_memory_repeat4', {}).get('total_waf')}",
                f"SepBIT exact WA={exact.get('sepbit_repeat4', {}).get('wa')}",
            ],
            "None for the current scoped claim; exact units remain separate from QUASAR same-path packed replay.",
            "Keep compact-LBA and original-LBA exact external numbers in a separate table from same-path packed ZNS replay.",
        ),
        item(
            "Improve QUASAR if the evidence shows a better deployable mode.",
            "satisfied" if selector.get("passed") and selector.get("default_policy") == "quasar-dogi-hybrid" else "weak",
            [
                f"selector modes={selector.get('passed_modes')}/{selector.get('total_modes')}",
                f"default policy={selector.get('default_policy')}",
                f"hardness passed={selector.get('hardness_passed')}",
            ],
            "Adaptive modes are available but should not be default unless a workload triggers them.",
            "Use QUASAR-DOGI hybrid by default; enable tenant-isolation or strict-residual modes explicitly.",
        ),
        item(
            "Account for overhead rather than only placement quality.",
            "satisfied"
            if overhead.get("failed_rows") == 0
            and overhead.get("row_count", 0) >= 80
            and xnvme_latency_validated(xnvme)
            else "weak",
            [
                f"overhead rows={overhead.get('row_count')} failed={overhead.get('failed_rows')}",
                f"hybrid/DOGI C-policy median ratio={overhead.get('hybrid_vs_dogi', {}).get('cpu_median_ns_ratio')}",
                f"semantic reset delta={overhead.get('hybrid_vs_dogi', {}).get('semantic_reset_delta')}",
                f"xNVMe completed={xnvme.get('completed')}",
                f"xNVMe append_count={xnvme.get('append_count')}",
                f"xNVMe append_p99_ns={xnvme.get('append_p99_ns')}",
                f"xNVMe mounted_after={xnvme.get('mounted_after')}",
            ],
            (
                "SPDK poll-mode is still not measured, but the lower-overhead raw xNVMe/Linux NVMe ioctl "
                "command path is validated."
            ),
            "Use zonefs-helper overhead as full-suite accounting and xNVMe as native command-path p99 evidence.",
        ),
        item(
            "Keep security claims bounded to reset eligibility unless sanitize is executed.",
            "satisfied-sanitize-validated"
            if sanitize_validated(security)
            else "satisfied-boundary"
            if security.get("sanitize_supported")
            else "weak",
            [
                f"device={security.get('device_model')}",
                f"SANICAP={security.get('sanicap_hex')}",
                f"sanitize_supported={security.get('sanitize_supported')}",
                f"sanitize_log_status={security.get('sanitize_log_status')}",
                f"crypto_erase_executed={security.get('crypto_erase_executed')}",
                f"sanitize_execution_validated={security.get('sanitize_execution_validated')}",
            ],
            (
                "None for the destructive command-path proof; shared-namespace sanitize is not a "
                "per-zone/per-epoch physical erase primitive. A strong erase deployment still "
                "requires a dedicated namespace/media pool, per-cohort key isolation, or hardware "
                "erase semantics whose blast radius matches the cohort."
            )
            if sanitize_validated(security)
            else "Physical erase proof still needs an erase path whose blast radius matches the target cohort.",
            (
                "State exposure-window reduction by default; claim physical erasure only for deployments "
                "whose erase command scope is isolated to the cohort being destroyed."
            ),
        ),
        item(
            "Make the generated actual-ZNS comparison reproducible and hash-checked.",
            "satisfied"
            if acceptance.get("passed")
            and validation.get("passed")
            and validation.get("mismatch_count") == 0
            and pipeline_manifest.get("passed")
            and pipeline_manifest.get("non_destructive")
            else "missing",
            [
                f"acceptance={acceptance.get('passed_gates')}/{acceptance.get('total_gates')}",
                f"hash mismatches={validation.get('mismatch_count')}",
                f"summary pipeline passed={pipeline_manifest.get('passed')}",
                f"summary pipeline steps={len(pipeline_manifest.get('steps', []))}",
            ],
            "Raw long-running physical replays still require device availability and time.",
            "Use run_actual_zns_summary_pipeline.py after changing any derived artifact.",
        ),
        item(
            "Capture real application block traces while PQC lifecycle side writes are persisted.",
            "satisfied" if real_app_block_trace_validated(real_app_block_trace) else "missing",
            [
                f"artifact={real_app_block_trace.get('artifact')}",
                f"device={real_app_block_trace.get('device')}",
                f"sysbench_elapsed_s={real_app_block_trace.get('sysbench', {}).get('elapsed_s')}",
                f"blkparse_events={real_app_block_trace.get('blktrace', {}).get('event_lines')}",
                f"blkparse_write_events={real_app_block_trace.get('blktrace', {}).get('write_events')}",
                f"pqc_sessions={real_app_block_trace.get('pqc_side_writer', {}).get('sessions_completed')}",
                f"pqc_records={real_app_block_trace.get('pqc_side_writer', {}).get('records')}",
                f"all_kem_ok={real_app_block_trace.get('pqc_side_writer', {}).get('all_kem_ok')}",
                f"all_sig_ok={real_app_block_trace.get('pqc_side_writer', {}).get('all_sig_ok')}",
            ],
            (
                "None for the real-application block-trace gap. This still does not prove SPDK/ZenFS "
                "tail latency or public-DOGI end-to-end parity."
            )
            if real_app_block_trace_validated(real_app_block_trace)
            else "Need a captured MySQL/Sysbench, RocksDB/YCSB, KMS, or audit-service block trace with PQC side writes.",
            "Use the captured sysbench+PQC trace as external-validity evidence; do not treat it as a ZNS placement result.",
        ),
        item(
            "Show external/system readiness has no current paper blockers for the scoped claim.",
            "satisfied" if readiness.get("paper_ready_external") and not readiness.get("blockers") else "missing",
            [
                f"paper_ready_external={readiness.get('paper_ready_external')}",
                f"blockers={readiness.get('blockers')}",
                f"pending={readiness.get('pending')}",
            ],
            "External readiness is scoped to the current claim, not an absolute proof of every possible device/firmware stack.",
            "Keep exact-baseline and same-path caveats visible.",
        ),
    ]

    blocking = [row for row in requirements if row["status"] in {"missing", "weak"}]
    production_blockers = fast_r2_production_blockers(unified, readiness, real_app_block_trace)
    optional_strengthening = [
        f"{row['name']}: {row['required_to_close']}" for row in production_blockers
    ]
    scoped_claim_ready = not blocking
    full_goal_complete = scoped_claim_ready and not production_blockers
    blocker_names = [row["name"] for row in production_blockers]
    blocker_phrase = ", ".join(BLOCKER_LABELS.get(name, name.replace("_", " ")) for name in blocker_names)
    return {
        "scope": "completion audit for actual-ZNS DOGI/SepBIT/MiDAS/FIFO vs QUASAR comparison",
        "scoped_claim_ready": scoped_claim_ready,
        "full_goal_complete": full_goal_complete,
        "blocking_count": len(blocking),
        "fast_r2_production_blocker_count": len(production_blockers),
        "full_goal_remaining_count": len(production_blockers),
        "requirements": requirements,
        "fast_r2_production_blockers": production_blockers,
        "optional_strengthening": optional_strengthening,
        "completion_boundary": (
            "The current artifacts support the scoped paper claim, but the broader user goal remains active "
            "because Reviewer-2 production blockers remain open."
        )
        if not full_goal_complete
        else "The scoped paper claim and broader full goal are both complete.",
        "main_takeaway": (
            "The scoped actual-ZNS comparison is ready: same-path physical replay, workload hardness, pressure, "
            "external exact baselines, overhead, security boundaries, and reproducibility are all covered. "
            "However, this is not production-grade FAST evidence yet: "
            f"{blocker_phrase} remain open."
        )
        if not blocking
        else "Some requirements still need stronger evidence before the scoped claim is ready.",
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Actual-ZNS Goal Completion Audit",
        "",
        f"- Scope: {summary['scope']}",
        f"- Scoped claim ready: `{summary['scoped_claim_ready']}`",
        f"- Full goal complete: `{summary['full_goal_complete']}`",
        f"- Blocking gaps: `{summary['blocking_count']}`",
        f"- FAST R2 production blockers: `{summary['fast_r2_production_blocker_count']}`",
        "",
        summary["main_takeaway"],
        "",
        summary["completion_boundary"],
        "",
        "| Requirement | Status | Evidence | Remaining | Next Action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in summary["requirements"]:
        evidence = "<br>".join(f"- {item}" for item in row["evidence"])
        lines.append(
            "| {requirement} | `{status}` | {evidence} | {remaining} | {next_action} |".format(
                requirement=row["requirement"],
                status=row["status"],
                evidence=evidence,
                remaining=row["remaining"],
                next_action=row["next_action"],
            )
        )
    lines.extend(["", "## FAST R2 Production Blockers", ""])
    lines.append("| Blocker | Evidence | Required To Close |")
    lines.append("| --- | --- | --- |")
    for row in summary["fast_r2_production_blockers"]:
        evidence = "<br>".join(f"- {item}" for item in row["evidence"])
        lines.append(
            "| {name} | {evidence} | {required} |".format(
                name=row["name"],
                evidence=evidence,
                required=row["required_to_close"],
            )
        )
    lines.extend(["", "## Compatibility Alias: Full-Goal Remaining Items", ""])
    lines.extend(f"- {item}" for item in summary["optional_strengthening"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unified", type=Path, default=Path("artifacts/results/unified-baseline-comparison.json"))
    parser.add_argument("--readiness", type=Path, default=Path("artifacts/results/external-readiness.json"))
    parser.add_argument("--acceptance", type=Path, default=Path("artifacts/results/acceptance-report.json"))
    parser.add_argument("--validation", type=Path, default=Path("artifacts/results/quasar-reproducibility-validation.json"))
    parser.add_argument(
        "--pipeline-manifest",
        type=Path,
        default=Path("artifacts/results/actual-zns-summary-pipeline-manifest.json"),
    )
    parser.add_argument(
        "--real-app-block-trace",
        type=Path,
        default=Path("artifacts/results/real-app-block-trace/sysbench-pqc/summary.json"),
    )
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/actual-zns-goal-completion-audit.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/actual-zns-goal-completion-audit.md"))
    args = parser.parse_args()

    summary = build_audit(
        load_json(args.unified),
        load_json(args.readiness),
        load_json(args.acceptance),
        load_json(args.validation),
        load_json(args.pipeline_manifest),
        load_json(args.real_app_block_trace) if args.real_app_block_trace.exists() else {},
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "scoped_claim_ready": summary["scoped_claim_ready"]}, sort_keys=True))
    return 0 if summary["scoped_claim_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
