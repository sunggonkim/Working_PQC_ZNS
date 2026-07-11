#!/usr/bin/env python3
"""Generate a real-liboqs PQC ratio sweep and evaluate placement policies."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path


FIXED_HANDSHAKE_PQC_BLOCKS = 4
DEFAULT_RATIOS = [0.01, 0.02, 0.05, 0.10, 0.20, 0.40]


def ratio_token(ratio: float) -> str:
    return f"{int(round(ratio * 10000)):04d}"


def payload_blocks_for_ratio(ratio: float) -> int:
    if ratio <= 0 or ratio >= 1:
        raise ValueError(f"ratio must be between 0 and 1: {ratio}")
    return max(0, math.ceil(FIXED_HANDSHAKE_PQC_BLOCKS * (1.0 - ratio) / ratio))


def run_cmd(cmd: list[str]) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def generate_trace(args: argparse.Namespace, ratio: float, idx: int) -> dict:
    token = ratio_token(ratio)
    payload_blocks = payload_blocks_for_ratio(ratio)
    payload_bytes = payload_blocks * args.block_size
    name = f"liboqs-handshake-pqc{token}"
    summary_path = args.summary_dir / f"{name}-summary.json"
    cmd = [
        sys.executable,
        "code/tracegen/liboqs_workload.py",
        "--sessions",
        str(args.sessions),
        "--event-type",
        "handshake",
        "--kem",
        args.kem,
        "--sig",
        args.sig,
        "--tenants",
        str(args.tenants),
        "--session-spacing-ms",
        str(args.session_spacing_ms),
        "--session-min-ms",
        str(args.session_min_ms),
        "--session-max-ms",
        str(args.session_max_ms),
        "--payload-min-bytes",
        str(payload_bytes),
        "--payload-max-bytes",
        str(payload_bytes),
        "--epoch-len-ms",
        str(args.epoch_len_ms),
        "--rotation-epochs",
        str(args.rotation_epochs),
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

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    blocks_by_intent = summary.get("trace", {}).get("blocks_by_intent", {})
    payload = int(blocks_by_intent.get("PAYLOAD", 0))
    total = sum(int(value) for value in blocks_by_intent.values())
    actual_ratio = (total - payload) / total if total else 0.0
    summary.update(
        {
            "target_pqc_ratio": ratio,
            "actual_pqc_block_ratio": actual_ratio,
            "payload_blocks_per_session": payload_blocks,
            "payload_bytes_per_session": payload_bytes,
            "workload": name,
        }
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def write_generation_summary(summaries: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summaries, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(summary: dict, generation: list[dict], path: Path) -> None:
    def pct_or_na(value) -> str:
        if value is None:
            return "N/A"
        return f"{value * 100:.1f}%"

    break_even = summary.get("break_even_ratio")
    lines = [
        "# liboqs Ratio Sweep Summary",
        "",
        f"- Generated traces: {len(generation)}",
        f"- Evaluation comparisons: {summary.get('comparison_count', 0)}",
        f"- Break-even target ratio: {'N/A' if break_even is None else f'{break_even * 100:.1f}%'}",
        "",
        "## Generated Ratios",
        "",
        "| Workload | Target PQC Ratio | Actual PQC Block Ratio | Payload Blocks/Session | KEM OK | SIG OK |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    for item in generation:
        lines.append(
            "| `{workload}` | {target:.1f}% | {actual:.2f}% | {payload_blocks:,} | {kem_ok} | {sig_ok} |".format(
                workload=item["workload"],
                target=item["target_pqc_ratio"] * 100,
                actual=item["actual_pqc_block_ratio"] * 100,
                payload_blocks=item["payload_blocks_per_session"],
                kem_ok=item.get("all_kem_ok"),
                sig_ok=item.get("all_sig_ok"),
            )
        )

    lines.extend(
        [
            "",
            "## Placement Result",
            "",
            "| Target PQC Ratio | N | Avg WAF vs DOGI | Aggregate GC vs DOGI | Avg p99 Latency vs DOGI | Stale Secrets Avoided |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in sorted(summary.get("ratio_summary", []), key=lambda item: item["ratio"]):
        lines.append(
            "| {ratio:.1f}% | {n} | {waf} | {gc} | {p99} | {stale:,} |".format(
                ratio=row["ratio"] * 100,
                n=row["n"],
                waf=pct_or_na(row["avg_waf_reduction_vs_dogi"]),
                gc=pct_or_na(row["aggregate_gc_reduction_vs_dogi"]),
                p99=pct_or_na(row["avg_p99_reduction_vs_dogi"]),
                stale=row["stale_avoided"],
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", type=Path, default=Path("artifacts/traces/liboqs-ratio-sweep/traces"))
    parser.add_argument("--event-dir", type=Path, default=Path("artifacts/traces/liboqs-ratio-sweep/events"))
    parser.add_argument("--summary-dir", type=Path, default=Path("artifacts/results/liboqs-ratio-sweep/summaries"))
    parser.add_argument("--eval-out", type=Path, default=Path("artifacts/results/liboqs-ratio-sweep/eval.json"))
    parser.add_argument("--ratio-summary-json", type=Path, default=Path("artifacts/results/liboqs-ratio-sweep/ratio-summary.json"))
    parser.add_argument("--generation-summary-json", type=Path, default=Path("artifacts/results/liboqs-ratio-sweep/generation-summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/liboqs-ratio-sweep/summary.md"))
    parser.add_argument("--ratios", default=",".join(str(ratio) for ratio in DEFAULT_RATIOS))
    parser.add_argument("--sessions", type=int, default=120)
    parser.add_argument("--kem", default="ML-KEM-768")
    parser.add_argument("--sig", default="ML-DSA-65")
    parser.add_argument("--tenants", type=int, default=8)
    parser.add_argument("--session-spacing-ms", type=int, default=2)
    parser.add_argument("--session-min-ms", type=int, default=80)
    parser.add_argument("--session-max-ms", type=int, default=500)
    parser.add_argument("--epoch-len-ms", type=int, default=200)
    parser.add_argument("--rotation-epochs", type=int, default=8)
    parser.add_argument("--block-size", type=int, default=4096)
    parser.add_argument("--zone-capacity", type=int, default=64)
    parser.add_argument("--min-free-zones", type=int, default=2)
    parser.add_argument("--seed", type=int, default=301)
    args = parser.parse_args()

    args.trace_dir.mkdir(parents=True, exist_ok=True)
    args.event_dir.mkdir(parents=True, exist_ok=True)
    args.summary_dir.mkdir(parents=True, exist_ok=True)

    ratios = [float(item) for item in args.ratios.split(",") if item.strip()]
    generation = [generate_trace(args, ratio, idx) for idx, ratio in enumerate(ratios)]
    write_generation_summary(generation, args.generation_summary_json)

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
            str(args.eval_out),
        ]
    )
    run_cmd(
        [
            sys.executable,
            "code/sim/report_ratio_sweep.py",
            "--results",
            str(args.eval_out),
            "--json-out",
            str(args.ratio_summary_json),
            "--markdown-out",
            str(args.summary_dir / "placement-summary.md"),
        ]
    )
    summary = json.loads(args.ratio_summary_json.read_text(encoding="utf-8"))
    write_markdown(summary, generation, args.markdown_out)
    print(json.dumps({"generated": len(generation), **summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
