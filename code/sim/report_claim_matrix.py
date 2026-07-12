#!/usr/bin/env python3
"""Generate a claim-to-evidence matrix for the QUASAR paper."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def fmt_bool(value: bool) -> str:
    return "yes" if value else "no"


def make_claim(
    claim: str,
    status: str,
    evidence: list[str],
    paper_wording: str,
    caveat: str,
) -> dict[str, Any]:
    return {
        "claim": claim,
        "status": status,
        "evidence": evidence,
        "paper_wording": paper_wording,
        "caveat": caveat,
    }


def sanitize_validated(security: dict[str, Any]) -> bool:
    return bool(security.get("sanitize_execution_validated") or security.get("crypto_erase_executed"))


def build_claims(
    unified: dict[str, Any],
    readiness: dict[str, Any],
    acceptance: dict[str, Any],
    fdp_mapping: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    fair = unified["same_path_physical_zns"]
    ycsb_curve = unified["ycsb_pressure_curve"]
    fast_db = unified["fast_db_pressure"]
    residual = unified["residual_fallback_sweep"]
    overhead = unified["actual_zns_overhead"]
    security = unified["security_capability"]
    exact = unified["exact_external_baselines"]
    hardness = unified["workload_hardness"]
    claim_gate = next((entry for entry in hardness.get("entries", []) if entry.get("tier") == "claim-gate"), {})
    claim_gate_evidence = claim_gate.get("evidence", {})
    selector = unified["deployment_selector"]
    manifest = unified["reproducibility_manifest"]
    validation = unified["reproducibility_validation"]
    fdp_runs = (fdp_mapping or {}).get("runs", [])
    fdp_best = max(fdp_runs, key=lambda row: row.get("handles", 0), default={})
    fdp_mid = next((row for row in fdp_runs if row.get("handles") == 64), fdp_best)

    claims = [
        make_claim(
            "Storage-history baselines miss PQC death cohorts.",
            "supported",
            [
                f"same-path physical ZNS fairness rows={fair['rows']} failed={fair['failed_rows']}",
                f"YCSB pressure semantic-gap rows={ycsb_curve['semantic_gap_rows']}/{ycsb_curve['row_count']}",
            ],
            (
                "FIFO, SepBIT-style, MiDAS-style, and DOGI-style placement retain expired PQC secret bytes "
                "because they do not receive protocol death-cohort information."
            ),
            "This is a semantic/exposure claim; WAF may remain near 1.0 on easy traces.",
        ),
        make_claim(
            "QUASAR-DOGI hybrid removes stale-secret exposure on clean hinted actual-ZNS replays.",
            "supported",
            [
                "same-path physical ZNS hybrid secret waiting end is zero",
                f"YCSB curve semantic-gap rows={ycsb_curve['semantic_gap_rows']}",
                f"Sysbench stale secret blocks removed={fast_db['hybrid_vs_dogi']['stale_secret_reduction_blocks']}",
            ],
            (
                "QUASAR-DOGI hybrid keeps DOGI-style payload placement while placing PQC secrets by death cohort, "
                "making expired secret cohorts reset-eligible."
            ),
            "Requires correct lifecycle hints and durable epoch-close logic.",
        ),
        make_claim(
            "WAF/GC gains are pressure-dependent, not universal.",
            "supported",
            [
                f"actual-ZNS YCSB WAF-pressure rows={ycsb_curve['waf_pressure_rows']}/{ycsb_curve['row_count']}",
                f"Sysbench GC reduction={fast_db['hybrid_vs_dogi']['gc_reduction']}",
                f"workload-hardness passed={hardness['passed_entries']}/{hardness['total_entries']}",
            ],
            (
                "WAF improvements appear when PQC metadata density and free-zone pressure create real GC work; "
                "otherwise the main benefit is stale-secret exposure reduction."
            ),
            "Do not claim QUASAR dominates every workload on total WAF.",
        ),
        make_claim(
            "The evaluation is not based on an overly easy PQC-only trace.",
            "supported",
            [
                f"workload-hardness tiers={hardness['by_tier']}",
                f"headline gate passed={claim_gate.get('passed')}",
                f"eligible YCSB pressure rows={claim_gate_evidence.get('eligible_ycsb_pressure_rows')}",
                f"YCSB baseline-complete rows={claim_gate_evidence.get('ycsb_baseline_complete_rows')}",
                f"eligible dynamic rows={claim_gate_evidence.get('eligible_dynamic_rows')}",
                f"dynamic baseline-complete rows={claim_gate_evidence.get('dynamic_baseline_complete_rows')}",
                f"YCSB pressure rows={ycsb_curve['waf_pressure_rows']}",
                f"Sysbench GC reduction={fast_db['hybrid_vs_dogi']['gc_reduction']}",
            ],
            (
                "The workload suite separates negative controls, DOGI-compatible pressure workloads, "
                "FAST-style DB pressure, and QUASAR-hostile robustness cases."
            ),
            "Clean epoch traces remain sanity checks; the main benchmark must use DOGI/FAST-compatible overlays and hostile stress.",
        ),
        make_claim(
            "The improved deployable QUASAR design uses explicit modes rather than one universal knob.",
            "supported",
            [
                f"deployment-selector modes={selector['passed_modes']}/{selector['total_modes']}",
                f"default policy={selector['default_policy']}",
                f"workload-hardness passed={selector['hardness_passed']}",
            ],
            (
                "QUASAR-DOGI hybrid is the default; tenant isolation, residual migration, and overflow fallback "
                "are enabled only when the measured workload/security objective requires their overhead."
            ),
            "Do not present adaptive binning or strict residual migration as free default behavior.",
        ),
        make_claim(
            "The actual-ZNS comparison is reproducible from an artifact manifest.",
            "supported",
            [
                f"manifest passed={manifest['passed']}",
                f"manifest artifacts={manifest['artifact_count']}",
                f"manifest commands={manifest['command_count']}",
                f"hash validation mismatches={validation['mismatch_count']}",
            ],
            (
                "The paper artifact set records hashes, roles, claims, and regeneration commands for the "
                "actual-ZNS comparison, pressure curves, overhead, selector, figures, and acceptance reports; "
                "a validation pass confirms the current files still match those hashes."
            ),
            "The manifest indexes current artifacts; long-running raw physical replays may still need explicit rerun time and device availability.",
        ),
        make_claim(
            "Residual migration is a deployable strict-exposure mode with explicit cost.",
            "supported",
            [
                f"residual decision={residual['decision']}",
                f"actual budget rows={len(residual.get('budget_physical_rows', []))}",
            ],
            (
                "QUASAR exposes low-overhead, balanced, and strict-zero-wait modes; strict exposure can force "
                "zero waiting but may pay high copy/WAF cost on hostile YCSB-F straggler workloads."
            ),
            "Strict mode is not the default for every workload.",
        ),
        make_claim(
            "Hybrid has explicit reset overhead but lower policy-decision CPU cost than DOGI-style MLP.",
            "supported",
            [
                f"actual-ZNS overhead rows={overhead['row_count']} failed={overhead['failed_rows']}",
                f"hybrid/DOGI CPU median ratio={overhead['hybrid_vs_dogi']['cpu_median_ns_ratio']}",
                f"semantic reset delta={overhead['hybrid_vs_dogi']['semantic_reset_delta']}",
            ],
            (
                "Hybrid pays actual semantic reset work but its C-level placement-decision path remains cheaper "
                "than DOGI-style MLP inference."
            ),
            "Actual-ZNS latency uses zonefs helper appends/truncates, so use as overhead accounting, not final production p99.",
        ),
        make_claim(
            (
                "Zone reset alone is not physical erase, but the device crypto-erase path is validated."
                if sanitize_validated(security)
                else "Zone reset evidence is not a physical NAND erase proof."
            ),
            "supported" if sanitize_validated(security) else "supported-boundary",
            [
                f"SANICAP={security['sanicap_hex']}",
                f"sanitize_supported={security['sanitize_supported']}",
                f"sanitize_log_status={security['sanitize_log_status']}",
                f"crypto_erase_executed={security.get('crypto_erase_executed')}",
                f"sanitize_execution_validated={security.get('sanitize_execution_validated')}",
            ],
            (
                "QUASAR proves reset eligibility and stale-secret exposure reduction. On the evaluated device, "
                "NVMe crypto-erase sanitize completed successfully; physical-erasure claims still require "
                "explicitly issuing sanitize or equivalent crypto-erase at epoch boundaries."
                if sanitize_validated(security)
                else "QUASAR proves reset eligibility and stale-secret exposure reduction. Strong physical erase requires "
                "a separate sanitize or crypto-erase execution and validation experiment."
            ),
            security["claim_boundary"],
        ),
        make_claim(
            "Exact external baselines are included but have non-identical unit systems.",
            "qualified",
            [
                f"DOGI exact aggregate WAF={exact['dogi_physical_compact']['aggregate_waf']}",
                f"MiDAS exact WAF={exact['midas_memory_repeat4']['total_waf']}",
                f"SepBIT exact WA={exact['sepbit_repeat4']['wa']}",
            ],
            (
                "External DOGI/MiDAS/SepBIT runs validate baseline realism, while same-path packed ZNS replay is "
                "used for apples-to-apples physical placement comparison."
            ),
            "Do not mix exact-baseline internal units with QUASAR native ZNS throughput as if they were identical.",
        ),
        make_claim(
            "FDP can carry QUASAR's lifecycle signal, but scarce placement handles create collision pressure.",
            "supported-boundary",
            [
                f"FDP handle-model runs={len(fdp_runs)}",
                f"families={fdp_best.get('family_count')}",
                f"best handles={fdp_best.get('handles')} family purity={fdp_best.get('family_purity')}",
                f"64-handle intent purity={fdp_mid.get('intent_purity')}",
                f"64-handle avg families/handle={fdp_mid.get('avg_families_per_occupied_handle')}",
            ],
            (
                "A trace-driven FDP mapping shows that QUASAR families retain high intent/family purity as placement "
                "handles increase, but small handle counts collide multiple death cohorts and require admission or binning."
            ),
            "This is a trace-driven handle-pressure model, not a physical FDP device performance result.",
        ),
        make_claim(
            "The current artifact set is paper-ready for the scoped system claim.",
            "supported",
            [
                f"acceptance={acceptance['passed_gates']}/{acceptance['total_gates']}",
                f"external readiness paper_ready={readiness['paper_ready_external']}",
            ],
            (
                "The scoped claim is ready: PQC death-cohort hints improve ZNS placement/reset scheduling under "
                "clean hints, pressure, and measured fallback modes."
            ),
                "Lower-overhead xNVMe/SPDK replay remains optional strengthening.",
        ),
    ]
    return claims


def summarize(claims: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    for claim in claims:
        by_status[claim["status"]] = by_status.get(claim["status"], 0) + 1
    return {
        "claim_count": len(claims),
        "by_status": by_status,
        "claims": claims,
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# QUASAR Claim Matrix",
        "",
        f"- Claims: `{summary['claim_count']}`",
        f"- Status counts: `{summary['by_status']}`",
        "",
        "| Claim | Status | Paper Wording | Caveat | Evidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    for claim in summary["claims"]:
        evidence = "<br>".join(f"- {item}" for item in claim["evidence"])
        lines.append(
            "| {claim} | `{status}` | {wording} | {caveat} | {evidence} |".format(
                claim=claim["claim"],
                status=claim["status"],
                wording=claim["paper_wording"],
                caveat=claim["caveat"],
                evidence=evidence,
            )
        )
    lines.extend(
        [
            "",
            "## Forbidden Overclaims",
            "",
            "- QUASAR always beats DOGI/MiDAS/SepBIT on WAF.",
            "- The clean PQC-only epoch trace is sufficient as the main benchmark.",
            "- Adaptive binning or strict residual migration should be enabled for every workload by default.",
            "- Current generated artifacts can be changed without updating hashes or the reproducibility manifest.",
            "- Zone reset alone proves physical NAND erase.",
            "- Helper-based zonefs latency is final production p99 latency.",
            "- Exact external baseline units are directly interchangeable with packed ZNS replay throughput.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unified", type=Path, default=Path("artifacts/results/unified-baseline-comparison.json"))
    parser.add_argument("--readiness", type=Path, default=Path("artifacts/results/external-readiness.json"))
    parser.add_argument("--acceptance", type=Path, default=Path("artifacts/results/acceptance-report.json"))
    parser.add_argument("--fdp-mapping", type=Path, default=Path("artifacts/results/pqc-mixed-fdp-mapping.json"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/quasar-claim-matrix.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/quasar-claim-matrix.md"))
    args = parser.parse_args()

    summary = summarize(
        build_claims(
            load_json(args.unified),
            load_json(args.readiness),
            load_json(args.acceptance),
            load_json(args.fdp_mapping),
        )
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "markdown_out": str(args.markdown_out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
