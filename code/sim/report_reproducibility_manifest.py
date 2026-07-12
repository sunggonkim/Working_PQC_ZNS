#!/usr/bin/env python3
"""Build a reproducibility manifest for the QUASAR actual-ZNS comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ARTIFACTS = [
    {
        "id": "same_path_actual_zns_fairness",
        "path": "artifacts/results/packed-physical-zonefs-replay-dogi-paper-pqc2000-z512-secret-group-helper.json",
        "role": "six DOGI/FAST workload-axis actual-ZNS fairness matrix",
        "claim": "storage-history baselines miss PQC death cohorts even when WAF is near 1.0",
    },
    {
        "id": "ycsb_actual_zns_pressure_curve",
        "path": "artifacts/results/fast-ycsb-pressure/ycsb-actual-zns-pressure-curve.json",
        "role": "actual-ZNS YCSB p2000 negative control plus p4000/p6000/p8000/p10000 pressure curve",
        "claim": "WAF/GC gains are pressure-dependent while semantic reset gap is broad",
    },
    {
        "id": "ycsb_actual_zns_p2000_raw",
        "path": "artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-pqc2000-z512-helper.json",
        "role": "raw actual-ZNS packed replay for YCSB p2000 negative WAF control",
        "claim": "easy YCSB point keeps WAF near 1.0 while exposing stale-secret reset gap",
    },
    {
        "id": "ycsb_actual_zns_a_p4000_raw",
        "path": "artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc4000-z560-helper.json",
        "role": "raw actual-ZNS packed replay for YCSB-A p4000 pressure point",
        "claim": "YCSB-A p4000 creates DOGI-style GC while hybrid drains secrets",
    },
    {
        "id": "ycsb_actual_zns_a_p6000_raw",
        "path": "artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc6000-z712-helper.json",
        "role": "raw actual-ZNS packed replay for YCSB-A p6000 pressure point",
        "claim": "YCSB-A p6000 strengthens the intermediate pressure curve",
    },
    {
        "id": "ycsb_actual_zns_a_p8000_raw",
        "path": "artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc8000-z863-helper.json",
        "role": "raw actual-ZNS packed replay for YCSB-A p8000 pressure point",
        "claim": "YCSB-A p8000 preserves stale-secret gap under higher PQC density",
    },
    {
        "id": "ycsb_actual_zns_f_p4000_raw",
        "path": "artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc4000-z733-helper.json",
        "role": "raw actual-ZNS packed replay for YCSB-F p4000 easy/stale-secret point",
        "claim": "YCSB-F p4000 remains an easy WAF point but exposes stale-secret gap",
    },
    {
        "id": "ycsb_actual_zns_f_p6000_raw",
        "path": "artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc6000-z733-helper.json",
        "role": "raw actual-ZNS packed replay for YCSB-F p6000 pressure point",
        "claim": "YCSB-F p6000 captures the transition from easy WAF to pressure",
    },
    {
        "id": "ycsb_actual_zns_f_p8000_raw",
        "path": "artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc8000-z733-helper.json",
        "role": "raw actual-ZNS packed replay for YCSB-F p8000 pressure point",
        "claim": "YCSB-F p8000 creates strong DOGI-style WAF/GC separation",
    },
    {
        "id": "ycsb_actual_zns_a_p10000_raw",
        "path": "artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc10000-z1024-helper.json",
        "role": "raw actual-ZNS packed replay for larger YCSB-A p10000 pressure point",
        "claim": "YCSB-A p10000 confirms the realistic failure mode is stale-secret exposure plus moderate DOGI-style GC, not a toy WAF explosion",
    },
    {
        "id": "ycsb_actual_zns_f_p10000_raw",
        "path": "artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc10000-z900-helper.json",
        "role": "raw actual-ZNS packed replay for larger YCSB-F p10000 pressure point",
        "claim": "YCSB-F p10000 strengthens DOGI-axis pressure while QUASAR/hybrid keeps GC and stale secrets at zero",
    },
    {
        "id": "sysbench_actual_zns_pressure",
        "path": "artifacts/results/fast-db-pressure/sysbench-pressure-summary.json",
        "role": "FAST-style DB pressure actual-ZNS replay summary",
        "claim": "update-heavy PQC metadata pressure can create large DOGI-style GC copy cost",
    },
    {
        "id": "dynamic_exchange_actual_zns_pressure",
        "path": "artifacts/results/fast-dynamic-pressure/dynamic-pressure-summary.json",
        "role": "DOGI dynamic-axis Exchange/Varmail/Alibaba pressure actual-ZNS replay summary",
        "claim": "dynamic service workloads also expose DOGI-style GC and stale-secret cost under PQC pressure",
    },
    {
        "id": "dynamic_exchange_actual_zns_raw",
        "path": "artifacts/results/fast-dynamic-pressure/packed-physical-zonefs-exchange-pqc8000-z768-helper.json",
        "role": "raw actual-ZNS packed replay for Exchange p8000 dynamic pressure",
        "claim": "Exchange p8000 creates DOGI/SepBIT/MiDAS GC while hybrid drains secrets",
    },
    {
        "id": "dynamic_varmail_actual_zns_raw",
        "path": "artifacts/results/fast-dynamic-pressure/packed-physical-zonefs-varmail-pqc8000-z768-helper.json",
        "role": "raw actual-ZNS packed replay for Varmail p8000 dynamic pressure",
        "claim": "Varmail p8000 creates DOGI/SepBIT/MiDAS GC while hybrid drains secrets",
    },
    {
        "id": "dynamic_alibaba_actual_zns_raw",
        "path": "artifacts/results/fast-dynamic-pressure/packed-physical-zonefs-alibaba-pqc8000-z768-helper.json",
        "role": "raw actual-ZNS packed replay for Alibaba p8000 dynamic pressure",
        "claim": "Alibaba p8000 creates DOGI/SepBIT/MiDAS GC while hybrid drains secrets",
    },
    {
        "id": "dogi_exact_alibaba_pressure",
        "path": "artifacts/results/dogi-exact/alibaba-pqc8000-dogi.json",
        "role": "exact public DOGI prototype run on physical ZNS with Alibaba p8000 compact trace",
        "claim": "public DOGI binary completes on the hard dynamic PQC pressure trace and reports high GC/WAF",
    },
    {
        "id": "dogi_exact_alibaba_suite",
        "path": "artifacts/results/dogi-exact/alibaba-pqc8000-suite.json",
        "role": "exact public DOGI prototype DOGI/Greedy/CostBenefit suite on physical ZNS",
        "claim": "all public DOGI-family placements complete and report high WAF on the hard dynamic PQC pressure trace",
    },
    {
        "id": "dogi_original_lba_adapter",
        "path": "artifacts/results/fast-dynamic-pressure/alibaba-pqc8000-original-lba-dogi-adapter.json",
        "role": "original-LBA DOGI adapter summary for Alibaba p8000 without compacting the LBA span",
        "claim": "original-LBA DOGI replay requires a 42GiB logical span instead of the compact 2GiB span",
    },
    {
        "id": "dogi_original_lba_preflight",
        "path": "artifacts/results/fast-dynamic-pressure/alibaba-pqc8000-original-lba-dogi-preflight-nvme0n1.json",
        "role": "preflight for the original-LBA DOGI run on the physical ZNS device",
        "claim": "the original-LBA trace is syntactically runnable by the DOGI prototype and the device/tool chain is visible",
    },
    {
        "id": "dogi_original_lba_completed_run",
        "path": "artifacts/results/dogi-exact/alibaba-pqc8000-original-lba-dogi-cwd-app.json",
        "role": "completed original-LBA public DOGI physical run summary",
        "claim": "the original-LBA DOGI run completes when executed from the prototype app working directory, reporting WAF on the 42GiB Alibaba p8000 span",
    },
    {
        "id": "dogi_public_parity_audit",
        "path": "artifacts/results/dogi-public-parity-audit.json",
        "role": "reviewer-facing boundary between same-path DOGI-style replay and exact public DOGI evidence",
        "claim": "substantial public DOGI evidence exists, but full end-to-end parity is not claimed",
    },
    {
        "id": "ycsb_f_straggler_baselines",
        "path": "artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc8000-straggler005-baselines-helper.json",
        "role": "actual-ZNS hard straggler replay for FIFO/SepBIT/MiDAS/DOGI baselines",
        "claim": "history baselines issue no semantic resets under delayed-expiry stragglers",
    },
    {
        "id": "actual_zns_overhead",
        "path": "artifacts/results/actual-zns-overhead-summary.json",
        "role": "actual-ZNS helper-path overhead plus C policy CPU accounting",
        "claim": "hybrid pays reset work but policy-decision CPU remains below DOGI-style MLP",
    },
    {
        "id": "xnvme_zns_latency",
        "path": "artifacts/results/xnvme-zns-latency/summary.json",
        "role": "raw xNVMe/Linux NVMe ioctl ZNS append/reset latency probe",
        "claim": "native xNVMe command-path p99 is measured without zonefs helper append overhead",
    },
    {
        "id": "xnvme_zns_latency_source",
        "path": "code/quasar/xnvme_zns_latency.c",
        "role": "source for the xNVMe native ZNS latency probe",
        "claim": "xNVMe replay evidence is backed by an inspectable in-tree tool",
    },
    {
        "id": "physical_zns_security_capability",
        "path": "artifacts/results/physical-zns-security-capability.json",
        "role": "physical ZNS sanitize/security capability and claim-boundary summary",
        "claim": "the evaluated device supports sanitize and records whether crypto-erase execution was validated",
    },
    {
        "id": "physical_zns_sanitize_execution",
        "path": "artifacts/results/physical-zns-sanitize-exec/summary.json",
        "role": "destructive NVMe crypto-erase sanitize execution summary for the physical ZNS SSD",
        "claim": (
            "the device crypto-erase sanitize command path completed successfully, but this is "
            "device/namespace-scoped evidence rather than a per-zone epoch erase primitive"
        ),
    },
    {
        "id": "workload_hardness",
        "path": "artifacts/results/workload-hardness-matrix.json",
        "role": "benchmark guardrail for fairness, negative-control, pressure, and hostile tiers",
        "claim": "evaluation does not rely on an overly easy PQC-only trace",
    },
    {
        "id": "deployment_selector",
        "path": "artifacts/results/quasar-deployment-policy-selector.json",
        "role": "deployable policy selector for default, tenant-isolation, strict-residual, and fallback modes",
        "claim": "QUASAR improvement is an explicit mode selector, not one universal knob",
    },
    {
        "id": "fdp_handle_pressure",
        "path": "artifacts/results/pqc-mixed-fdp-mapping.json",
        "role": "trace-driven QUASAR-to-FDP placement-handle pressure model",
        "claim": "FDP can carry QUASAR lifecycle families, but scarce handles collide death cohorts",
    },
    {
        "id": "fdp_handle_pressure_figure",
        "path": "artifacts/figures/fast-style/fig8-fdp-handle-pressure.pdf",
        "role": "paper Figure 8 for FDP handle-count purity and collision pressure",
        "claim": "FDP handle pressure is reported as deployment modeling, not physical FDP performance",
    },
    {
        "id": "real_app_sysbench_pqc_block_trace",
        "path": "artifacts/results/real-app-block-trace/sysbench-pqc/summary.json",
        "role": "real sysbench fileio block trace captured while liboqs PQC lifecycle side writes are persisted",
        "claim": "the real-application block-trace blocker is closed for sysbench plus PQC side writes",
    },
    {
        "id": "real_app_sysbench_pqc_blkparse_sample",
        "path": "artifacts/results/real-app-block-trace/sysbench-pqc/blkparse-sample.txt",
        "role": "sample of the blkparse output from the sysbench plus PQC capture",
        "claim": "block trace evidence includes auditable blkparse event lines without storing the full raw trace in the manifest",
    },
    {
        "id": "real_app_sysbench_pqc_capture_source",
        "path": "code/tracegen/capture_real_app_block_trace.py",
        "role": "source for capturing sysbench fileio block traces with concurrent PQC lifecycle side writes",
        "claim": "real application block-trace capture is backed by an inspectable in-tree tool",
    },
    {
        "id": "unified_comparison",
        "path": "artifacts/results/unified-baseline-comparison.json",
        "role": "single JSON summary separating same-path, pressure, exact external, and boundary evidence",
        "claim": "paper-ready comparison summary",
    },
    {
        "id": "claim_matrix",
        "path": "artifacts/results/quasar-claim-matrix.json",
        "role": "claim-to-evidence guardrail",
        "claim": "supported, qualified, and boundary claims are separated",
    },
    {
        "id": "external_readiness",
        "path": "artifacts/results/external-readiness.json",
        "role": "conservative readiness report for external/system evidence",
        "claim": "no current blockers or pending paper-grade evidence gaps for scoped claim",
    },
    {
        "id": "goal_completion_audit",
        "path": "artifacts/results/actual-zns-goal-completion-audit.json",
        "role": "requirement-by-requirement audit of the actual-ZNS comparison goal",
        "claim": "scoped claim is ready while FAST R2 production blockers keep the broader goal open",
    },
    {
        "id": "acceptance",
        "path": "artifacts/results/acceptance-report.json",
        "role": "local acceptance gate summary",
        "claim": "all reproducibility and evidence gates pass",
    },
    {
        "id": "ycsb_pressure_figure",
        "path": "artifacts/figures/actual-zns/ycsb-pressure-waf-stale.png",
        "role": "paper figure for actual-ZNS YCSB WAF/stale-secret curve",
        "claim": "visualizes negative control and pressure rows",
    },
    {
        "id": "overhead_figure",
        "path": "artifacts/figures/actual-zns/overhead-accounting.png",
        "role": "paper figure for actual-ZNS overhead accounting",
        "claim": "visualizes throughput, CPU, and semantic reset cost",
    },
    {
        "id": "workload_hardness_figure",
        "path": "artifacts/figures/actual-zns/workload-hardness.png",
        "role": "paper figure for workload hardness tiers",
        "claim": "visualizes fairness, pressure, and hostile coverage",
    },
]


COMMANDS = [
    {
        "step": "actual_zns_summary_pipeline",
        "command": "python3 code/sim/run_actual_zns_summary_pipeline.py",
    },
    {
        "step": "workload_hardness",
        "command": "python3 code/sim/report_fast_dynamic_pressure.py && python3 code/sim/report_workload_hardness_matrix.py",
    },
    {
        "step": "deployment_selector",
        "command": "python3 code/sim/report_deployment_policy_selector.py",
    },
    {
        "step": "actual_zns_figures",
        "command": "python3 code/sim/plot_actual_zns_comparison.py",
    },
    {
        "step": "fdp_mapping",
        "command": "python3 code/quasar/fdp_mapping.py --trace artifacts/traces/pqc-mixed.jsonl --handles 8 16 32 64 128 --out artifacts/results/pqc-mixed-fdp-mapping.json --markdown-out artifacts/results/pqc-mixed-fdp-mapping.md",
    },
    {
        "step": "real_app_block_trace",
        "command": "sudo python3 code/tracegen/capture_real_app_block_trace.py --duration 8 --sysbench-total-size 64M --sysbench-file-num 8 --sysbench-threads 4 --pqc-sessions 64 --pqc-sleep-ms 5",
    },
    {
        "step": "fast_style_figures",
        "command": "python3 code/sim/plot_fast_style_quasar_figures.py",
    },
    {
        "step": "unified_report",
        "command": "python3 code/sim/report_unified_comparison.py",
    },
    {
        "step": "claim_matrix",
        "command": "python3 code/sim/report_claim_matrix.py && python3 code/sim/report_unified_comparison.py",
    },
    {
        "step": "external_readiness",
        "command": "python3 code/baselines/external_readiness.py",
    },
    {
        "step": "goal_completion_audit",
        "command": "python3 code/sim/report_goal_completion_audit.py",
    },
    {
        "step": "acceptance",
        "command": "python3 code/sim/acceptance_check.py",
    },
    {
        "step": "unit_tests",
        "command": "python3 -m unittest discover -s code -p 'test*.py'",
    },
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_entry(root: Path, item: dict[str, str]) -> dict[str, Any]:
    path = root / item["path"]
    exists = path.exists()
    return {
        **item,
        "exists": exists,
        "bytes": path.stat().st_size if exists else 0,
        "sha256": sha256(path) if exists and path.is_file() else None,
    }


def summarize(root: Path) -> dict[str, Any]:
    artifacts = [artifact_entry(root, item) for item in ARTIFACTS]
    missing = [item["id"] for item in artifacts if not item["exists"] or item["bytes"] <= 0]
    readiness = {}
    for entry in artifacts:
        if entry["path"].endswith(".json") and entry["exists"]:
            try:
                with (root / entry["path"]).open("r", encoding="utf-8") as src:
                    data = json.load(src)
                readiness[entry["id"]] = {
                    key: data.get(key)
                    for key in [
                        "passed",
                        "passed_gates",
                        "total_gates",
                        "paper_ready_external",
                        "blockers",
                        "pending",
                        "claim_count",
                        "by_status",
                        "passed_modes",
                        "total_modes",
                        "audit_status",
                        "passed_evidence",
                        "total_evidence",
                    ]
                    if key in data
                }
            except json.JSONDecodeError:
                readiness[entry["id"]] = {"json_error": True}
    passed = not missing
    return {
        "scope": "reproducibility manifest for actual-ZNS baseline-vs-QUASAR comparison",
        "passed": passed,
        "artifact_count": len(artifacts),
        "missing_or_empty": missing,
        "artifacts": artifacts,
        "commands": COMMANDS,
        "readiness": readiness,
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# QUASAR Reproducibility Manifest",
        "",
        f"- Scope: {summary['scope']}",
        f"- Passed: `{summary['passed']}`",
        f"- Artifacts: `{summary['artifact_count']}`",
        f"- Missing or empty: `{summary['missing_or_empty']}`",
        "",
        "## Artifacts",
        "",
        "| ID | Path | Bytes | SHA256 | Role | Claim |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    for item in summary["artifacts"]:
        sha = item["sha256"][:12] if item["sha256"] else "N/A"
        lines.append(
            "| `{id}` | `{path}` | {bytes} | `{sha}` | {role} | {claim} |".format(
                id=item["id"],
                path=item["path"],
                bytes=item["bytes"],
                sha=sha,
                role=item["role"],
                claim=item["claim"],
            )
        )
    lines.extend(
        [
            "",
            "## Regeneration Commands",
            "",
            "| Step | Command |",
            "| --- | --- |",
        ]
    )
    for command in summary["commands"]:
        lines.append(f"| `{command['step']}` | `{command['command']}` |")
    lines.extend(
        [
            "",
            "## Readiness Snapshot",
            "",
            "```json",
            json.dumps(summary["readiness"], indent=2, sort_keys=True),
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/quasar-reproducibility-manifest.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/quasar-reproducibility-manifest.md"))
    args = parser.parse_args()

    summary = summarize(args.root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "passed": summary["passed"]}, sort_keys=True))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
