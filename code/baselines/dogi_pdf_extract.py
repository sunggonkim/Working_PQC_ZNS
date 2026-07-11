#!/usr/bin/env python3
"""Extract DOGI FAST paper facts needed for QUASAR experiment planning."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


def pdf_to_text(pdf: Path) -> str:
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext is required for DOGI PDF extraction")
    proc = subprocess.run(["pdftotext", str(pdf), "-"], check=False, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "pdftotext failed")
    return proc.stdout


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def excerpt(text: str, pattern: str, chars: int = 520) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return ""
    start = max(0, match.start() - chars // 4)
    end = min(len(text), match.end() + chars)
    return normalize(text[start:end])


def has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def build_report(pdf: Path) -> dict[str, Any]:
    text = pdf_to_text(pdf)
    compact = normalize(text)
    report = {
        "source_pdf": str(pdf),
        "paper": {
            "title": "DOGI: Data Placement with Oracle-Guided Insights for Log-Structured Systems",
            "venue": "USENIX FAST 2026",
            "url": "https://www.usenix.org/conference/fast26/presentation/kim-jeeyun",
        },
        "extracted_claims": {
            "waf_reduction_up_to_percent": 23.2 if has(compact, r"up to 23\.2%") else None,
            "throughput_improvement_up_to_percent": 13.3 if has(compact, r"up to 13\.3%") else None,
            "average_waf_reduction_percent": 15.5 if has(compact, r"reduces WAF by 15\.5%") else None,
            "average_write_throughput_improvement_percent": 9.2 if has(compact, r"throughput by 9\.2%") else None,
        },
        "baseline_family": {
            "oracle": "NoDaP near-optimal oracle-guided placement",
            "sota": ["SepBIT", "MiDAS", "PHFTL", "ML-DT"],
            "dogi_components": [
                "hybrid heuristic and ML prediction for user-written blocks",
                "historical information plus ML for GC-written block relocation",
                "dynamic group configuration",
            ],
        },
        "motivation_observations": [
            {
                "observation": "User-written block placement remains inaccurate under heuristic-only policies.",
                "quasar_takeaway": "For PQC, the missing signal is not a better storage-visible feature; it is the protocol-known death cohort.",
            },
            {
                "observation": "ML improves prediction accuracy but can add long inference latency and hurt write throughput.",
                "quasar_takeaway": "QUASAR should report CPU cost and show that hint lookup is cheaper than DOGI-style inference for PQC objects.",
            },
            {
                "observation": "GC-written blocks have diverse remaining lifetimes and are hard to relocate using age alone.",
                "quasar_takeaway": "QUASAR should avoid creating GC-written secret residues by making secret zones reset-eligible at epoch close.",
            },
            {
                "observation": "The number of placement groups has a granularity-vs-misprediction trade-off.",
                "quasar_takeaway": "QUASAR must evaluate open-zone budget, bin width, and zone utilization rather than claiming exact epoch placement is always free.",
            },
        ],
        "experimental_setup": {
            "simulator_storage_gib": 128 if has(compact, r"128GiB storage") else None,
            "segment_size_mib": 256 if has(compact, r"256MiB segments?") else None,
            "logical_block_size_kib": 4 if has(compact, r"4KiB") else None,
            "op_ratio_percent": 10 if has(compact, r"10% over") else None,
            "real_device": "Western Digital ZN540 2TB ZNS NVMe SSD" if has(compact, r"Western Digital ZN540 2TB") else None,
            "storage_stack": "ZenFS over ZNS, one segment mapped to one ZoneFile" if has(compact, r"ZenFS") else None,
            "peak_4k_sequential_write_gib_s": 1.1 if has(compact, r"1\.1GiB/s") else None,
            "prototype_uses_for": ["throughput", "latency"],
            "simulator_uses_for": ["WAF", "prediction accuracy", "group optimization"],
        },
        "workloads": [
            "FIO Zipf theta=1.0",
            "YCSB-A on MySQL",
            "YCSB-F on MySQL",
            "Filebench Varmail",
            "Alibaba Cloud I/O traces",
            "Microsoft Exchange traces",
        ],
        "artifact_requirements": {
            "dogi_repo": "https://github.com/dgist-datalab/DOGI",
            "rocksdb_version": "v6.25.3" if has(compact, r"RocksDB v6\.25\.3") else None,
            "zenfs_version": "v0.2.0" if has(compact, r"ZenFS v0\.2\.0") else None,
            "zns_alternatives": ["physical ZN540", "NVMeVirt ZNS emulation"],
            "nvmevirt_memory_note": "DRAM must exceed emulated device size plus 10% OP region",
        },
        "artifact_components": {
            "initialization_and_placement": [
                "app/main.cc",
                "app/classifier.cc",
                "src/placement/dogi.cc",
            ],
            "model_training_and_inference": [
                "app/freq_features.cc",
                "app/model_train.cc",
                "DOGI-Train/model_trainer.py",
                "app/mlp_inference.cc",
            ],
            "group_configuration_and_gc": [
                "group_optimizer.cc",
                "group_config.cc",
                "src/selection/dogiselect.cc",
            ],
        },
        "workload_interpretation": {
            "s_type": {
                "workloads": ["FIO", "YCSB-A", "YCSB-F"],
                "reading": "skewed/static access patterns; storage-visible lifetime prediction is easier",
            },
            "d_type": {
                "workloads": ["Varmail", "Alibaba", "Exchange"],
                "reading": "dynamic access patterns; DOGI still helps, but prediction accuracy and WAF gains are smaller",
            },
        },
        "quasar_implications": [
            "Use the same six DOGI workload families when adding PQC pressure.",
            "Report WAF and absolute GC bytes, because DOGI's own average WAF gain is not enormous.",
            "Run physical ZN540 replay for throughput/latency, while keeping simulator results for large sweeps.",
            "Do not compare QUASAR only to weak FIFO; include DOGI-style, MiDAS-style, exact MiDAS/SepBIT artifacts, and oracle.",
            "Separate physical append-path smoke results from full DOGI prototype throughput claims.",
            "Use NoDaP/epoch-oracle only as an upper bound, not as a deployable baseline.",
        ],
        "quasar_fairness_checklist": [
            "Use DOGI-visible features for DOGI-style baselines: LBA, previous LBA, interval/frequency bits, segment access, previous group.",
            "Do not give DOGI `intent_class` or `epoch_id`; those are the proposed QUASAR interface.",
            "Do give DOGI-style baselines the same logical trace, update/delete timing, storage capacity, zone size, and OP pressure.",
            "Report when DOGI already has WAF near 1.0; in that regime QUASAR's claim moves to exposure/CPU overhead rather than WAF.",
            "For physical replay, distinguish direct zonefs append latency from RocksDB/ZenFS/DOGI end-to-end throughput.",
        ],
        "evidence_excerpts": {
            "setup": excerpt(compact, r"Evaluation Platform"),
            "workloads": excerpt(compact, r"Workloads\."),
            "artifact": excerpt(compact, r"Hardware requirements"),
            "limitations": excerpt(compact, r"we discover three key limitations"),
        },
    }
    return report


def markdown(report: dict[str, Any]) -> str:
    setup = report["experimental_setup"]
    claims = report["extracted_claims"]
    lines = [
        "# DOGI FAST 2026 Extraction",
        "",
        f"- Source: `{report['source_pdf']}`",
        f"- Paper: {report['paper']['title']}",
        f"- Venue: {report['paper']['venue']}",
        "",
        "## Extracted Claims",
        "",
        f"- WAF reduction: average `{claims['average_waf_reduction_percent']}%`, up to `{claims['waf_reduction_up_to_percent']}%`.",
        f"- Write-throughput improvement: average `{claims['average_write_throughput_improvement_percent']}%`, up to `{claims['throughput_improvement_up_to_percent']}%`.",
        "",
        "## Setup To Mirror",
        "",
        f"- Real device: `{setup['real_device']}`",
        f"- Stack: `{setup['storage_stack']}`",
        f"- Segment size: `{setup['segment_size_mib']} MiB`",
        f"- Logical block size: `{setup['logical_block_size_kib']} KiB`",
        f"- OP ratio: `{setup['op_ratio_percent']}%`",
        "",
        "## Workloads",
        "",
    ]
    lines.extend(f"- {workload}" for workload in report["workloads"])
    lines.extend(["", "## DOGI Observations To Carry Into QUASAR", ""])
    for item in report["motivation_observations"]:
        lines.append(f"- {item['observation']} QUASAR implication: {item['quasar_takeaway']}")
    lines.extend(["", "## DOGI Artifact Components", ""])
    for group, files in report["artifact_components"].items():
        lines.append(f"- {group}: {', '.join(files)}")
    lines.extend(["", "## Fairness Checklist", ""])
    lines.extend(f"- {item}" for item in report["quasar_fairness_checklist"])
    lines.extend(["", "## QUASAR Experiment Implications", ""])
    lines.extend(f"- {item}" for item in report["quasar_implications"])
    return "\n".join(lines) + "\n"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, default=Path("Paper/Previous papers/fast26-kim-jeeyun.pdf"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/dogi-fast26-extraction.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/dogi-fast26-extraction.md"))
    args = parser.parse_args()

    report = build_report(args.pdf)
    write_json(args.out, report)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"source_pdf": str(args.pdf), "workloads": len(report["workloads"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
