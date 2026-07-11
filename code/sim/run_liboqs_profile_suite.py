#!/usr/bin/env python3
"""Generate and evaluate several real-liboqs PQC workload profiles."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


PROFILES = [
    {
        "name": "tls-storm",
        "event_type": "handshake",
        "sessions": 300,
        "tenants": 4,
        "session_spacing_ms": 2,
        "session_min_ms": 50,
        "session_max_ms": 250,
        "payload_min_bytes": 4096,
        "payload_max_bytes": 16384,
        "epoch_len_ms": 100,
        "rotation_epochs": 8,
    },
    {
        "name": "kms-rotation",
        "event_type": "kms_wrap",
        "sessions": 300,
        "tenants": 8,
        "session_spacing_ms": 3,
        "session_min_ms": 80,
        "session_max_ms": 400,
        "payload_min_bytes": 0,
        "payload_max_bytes": 1024,
        "epoch_len_ms": 120,
        "rotation_epochs": 4,
    },
    {
        "name": "cert-log",
        "event_type": "audit_log",
        "sessions": 300,
        "tenants": 4,
        "session_spacing_ms": 4,
        "session_min_ms": 100,
        "session_max_ms": 800,
        "payload_min_bytes": 0,
        "payload_max_bytes": 0,
        "epoch_len_ms": 200,
        "rotation_epochs": 8,
    },
    {
        "name": "mixed-service",
        "event_type": "handshake",
        "sessions": 300,
        "tenants": 12,
        "session_spacing_ms": 2,
        "session_min_ms": 200,
        "session_max_ms": 1200,
        "payload_min_bytes": 32768,
        "payload_max_bytes": 131072,
        "epoch_len_ms": 250,
        "rotation_epochs": 12,
    },
]


def run_cmd(cmd: list[str]) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def generate_profiles(args: argparse.Namespace) -> list[dict]:
    profile_summaries = []
    args.trace_dir.mkdir(parents=True, exist_ok=True)
    args.event_dir.mkdir(parents=True, exist_ok=True)
    args.summary_dir.mkdir(parents=True, exist_ok=True)

    for idx, profile in enumerate(PROFILES):
        name = profile["name"]
        summary_path = args.summary_dir / f"{name}-summary.json"
        cmd = [
            sys.executable,
            "code/tracegen/liboqs_workload.py",
            "--sessions",
            str(profile["sessions"]),
            "--event-type",
            str(profile["event_type"]),
            "--kem",
            args.kem,
            "--sig",
            args.sig,
            "--tenants",
            str(profile["tenants"]),
            "--session-spacing-ms",
            str(profile["session_spacing_ms"]),
            "--session-min-ms",
            str(profile["session_min_ms"]),
            "--session-max-ms",
            str(profile["session_max_ms"]),
            "--payload-min-bytes",
            str(profile["payload_min_bytes"]),
            "--payload-max-bytes",
            str(profile["payload_max_bytes"]),
            "--epoch-len-ms",
            str(profile["epoch_len_ms"]),
            "--rotation-epochs",
            str(profile["rotation_epochs"]),
            "--event-log",
            str(args.event_dir / f"{name}-events.jsonl"),
            "--jsonl",
            str(args.trace_dir / f"{name}.jsonl"),
            "--dogi-trace",
            str(args.trace_dir / f"{name}.dogi"),
            "--summary-out",
            str(summary_path),
            "--seed",
            str(args.seed + idx),
        ]
        run_cmd(cmd)
        profile_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        profile_summary["profile"] = name
        profile_summary["event_type"] = profile["event_type"]
        profile_summaries.append(profile_summary)
    return profile_summaries


def summarize_results(result_path: Path, profile_summaries: list[dict], out_path: Path) -> dict:
    rows = json.loads(result_path.read_text(encoding="utf-8"))
    by_workload: dict[str, dict[str, dict]] = {}
    for row in rows:
        by_workload.setdefault(row["workload"], {})[row["policy"]] = row

    comparisons = []
    for workload, policies in sorted(by_workload.items()):
        dogi = policies.get("dogi-history")
        hybrid = policies.get("quasar-dogi-hybrid")
        if not dogi or not hybrid:
            continue
        comparisons.append(
            {
                "workload": workload,
                "dogi_waf": dogi["waf"],
                "hybrid_waf": hybrid["waf"],
                "waf_reduction_vs_dogi": (dogi["waf"] - hybrid["waf"]) / dogi["waf"],
                "dogi_gc_write_blocks": dogi["gc_write_blocks"],
                "hybrid_gc_write_blocks": hybrid["gc_write_blocks"],
                "gc_reduction_vs_dogi": (
                    (dogi["gc_write_blocks"] - hybrid["gc_write_blocks"]) / dogi["gc_write_blocks"]
                    if dogi["gc_write_blocks"]
                    else None
                ),
                "dogi_p99_write_latency_ns": dogi.get("write_latency_p99_ns", 0),
                "hybrid_p99_write_latency_ns": hybrid.get("write_latency_p99_ns", 0),
                "dogi_stale_secret_blocks": dogi.get("stale_secret_blocks_remaining", 0),
                "hybrid_stale_secret_blocks": hybrid.get("stale_secret_blocks_remaining", 0),
            }
        )

    summary = {
        "profile_summaries": profile_summaries,
        "comparisons": comparisons,
        "avg_waf_reduction_vs_dogi": (
            sum(item["waf_reduction_vs_dogi"] for item in comparisons) / len(comparisons)
            if comparisons
            else 0.0
        ),
        "stale_secret_blocks_avoided": sum(
            item["dogi_stale_secret_blocks"] - item["hybrid_stale_secret_blocks"]
            for item in comparisons
        ),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def write_markdown(summary: dict, path: Path) -> None:
    lines = [
        "# liboqs Profile Suite Summary",
        "",
        f"- Profiles: {len(summary['profile_summaries'])}",
        f"- Average WAF reduction vs DOGI: {summary['avg_waf_reduction_vs_dogi'] * 100:.1f}%",
        f"- Stale secret blocks avoided: {summary['stale_secret_blocks_avoided']:,}",
        "",
        "| Workload | DOGI WAF | Hybrid WAF | WAF vs DOGI | GC vs DOGI | DOGI p99 ns | Hybrid p99 ns | Stale Avoided |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summary["comparisons"]:
        gc_reduction = item["gc_reduction_vs_dogi"]
        stale = item["dogi_stale_secret_blocks"] - item["hybrid_stale_secret_blocks"]
        lines.append(
            "| `{workload}` | {dogi_waf:.3f} | {hybrid_waf:.3f} | {waf:.1f}% | {gc} | {dogi_p99:,} | {hybrid_p99:,} | {stale:,} |".format(
                workload=item["workload"],
                dogi_waf=item["dogi_waf"],
                hybrid_waf=item["hybrid_waf"],
                waf=item["waf_reduction_vs_dogi"] * 100,
                gc="N/A" if gc_reduction is None else f"{gc_reduction * 100:.1f}%",
                dogi_p99=int(item["dogi_p99_write_latency_ns"]),
                hybrid_p99=int(item["hybrid_p99_write_latency_ns"]),
                stale=stale,
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", type=Path, default=Path("artifacts/traces/liboqs-profiles/traces"))
    parser.add_argument("--event-dir", type=Path, default=Path("artifacts/traces/liboqs-profiles/events"))
    parser.add_argument("--summary-dir", type=Path, default=Path("artifacts/results/liboqs-profiles/summaries"))
    parser.add_argument("--results", type=Path, default=Path("artifacts/results/liboqs-profiles/eval.json"))
    parser.add_argument("--summary-out", type=Path, default=Path("artifacts/results/liboqs-profiles/summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/liboqs-profiles/summary.md"))
    parser.add_argument("--kem", default="ML-KEM-768")
    parser.add_argument("--sig", default="ML-DSA-65")
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--zone-capacity", type=int, default=64)
    parser.add_argument("--min-free-zones", type=int, default=2)
    args = parser.parse_args()

    profile_summaries = generate_profiles(args)
    run_cmd(
        [
            sys.executable,
            "code/sim/run_workload_suite.py",
            "--trace-dir",
            str(args.trace_dir),
            "--auto-zones",
            "--auto-op-ratio",
            "0.20",
            "--zone-capacity",
            str(args.zone_capacity),
            "--min-free-zones",
            str(args.min_free_zones),
            "--policies",
            "fifo",
            "sepbit-style",
            "midas-style",
            "dogi-history",
            "quasar",
            "quasar-dogi-hybrid",
            "epoch-oracle",
            "--out",
            str(args.results),
        ]
    )
    summary = summarize_results(args.results, profile_summaries, args.summary_out)
    write_markdown(summary, args.markdown_out)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
