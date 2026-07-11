#!/usr/bin/env python3
"""Generate larger real-liboqs KMS/update stress traces and evaluate placement."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

try:
    import zns_pqc_verify as sim
except ModuleNotFoundError:  # pragma: no cover - root-level unittest discovery
    from sim import zns_pqc_verify as sim


PROFILES = [
    {
        "name": "kms-burst",
        "sessions": 600,
        "tenants": 32,
        "session_spacing_ms": 1,
        "session_min_ms": 20,
        "session_max_ms": 120,
        "payload_min_bytes": 0,
        "payload_max_bytes": 1024,
        "epoch_len_ms": 32,
        "rotation_epochs": 2,
    },
    {
        "name": "kms-tenant-churn",
        "sessions": 800,
        "tenants": 64,
        "session_spacing_ms": 1,
        "session_min_ms": 40,
        "session_max_ms": 180,
        "payload_min_bytes": 0,
        "payload_max_bytes": 512,
        "epoch_len_ms": 48,
        "rotation_epochs": 2,
    },
    {
        "name": "kms-rotation-dense",
        "sessions": 900,
        "tenants": 16,
        "session_spacing_ms": 1,
        "session_min_ms": 10,
        "session_max_ms": 80,
        "payload_min_bytes": 0,
        "payload_max_bytes": 0,
        "epoch_len_ms": 24,
        "rotation_epochs": 1,
    },
]


def run_cmd(cmd: list[str]) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def generate_profiles(args: argparse.Namespace) -> list[dict]:
    args.trace_dir.mkdir(parents=True, exist_ok=True)
    args.event_dir.mkdir(parents=True, exist_ok=True)
    args.generation_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for idx, profile in enumerate(PROFILES):
        name = profile["name"]
        summary_path = args.generation_dir / f"{name}-generation.json"
        cmd = [
            sys.executable,
            "code/tracegen/liboqs_workload.py",
            "--sessions",
            str(profile["sessions"]),
            "--event-type",
            "kms_wrap",
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
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["profile"] = name
        summaries.append(summary)
    return summaries


def max_live_blocks(trace: Path) -> int:
    live_by_object: dict[int, int] = {}
    live = 0
    peak = 0
    with trace.open("r", encoding="utf-8") as src:
        for line in src:
            row = json.loads(line)
            object_id = int(row["object_id"])
            blocks = int(row["size_blocks"])
            if row["op"] in {"write", "prefill"}:
                live_by_object[object_id] = blocks
                live += blocks
                peak = max(peak, live)
            elif row["op"] == "expire":
                live -= live_by_object.pop(object_id, 0)
    return peak


def zones_for_pressure(trace: Path, *, zone_capacity: int, min_free_zones: int, op_ratio: float) -> int:
    peak_live = max_live_blocks(trace)
    usable = math.ceil((peak_live * (1.0 + op_ratio)) / zone_capacity)
    return max(min_free_zones + 1, usable + min_free_zones)


def sim_args(base: argparse.Namespace, trace: Path, zones: int) -> Namespace:
    return Namespace(
        trace=trace,
        zones=zones,
        zone_capacity=base.zone_capacity,
        min_free_zones=base.min_free_zones,
        lba_bucket_size=base.lba_bucket_size,
        quasar_cert_epochs=base.quasar_cert_epochs,
        quasar_min_epoch_fill=base.quasar_min_epoch_fill,
        quasar_bin_width=base.quasar_bin_width,
        quasar_open_zone_budget=base.quasar_open_zone_budget,
        quasar_residual_threshold=base.quasar_residual_threshold,
        quasar_residual_fraction=base.quasar_residual_fraction,
        quasar_disable_overflow=False,
        quasar_disable_secret_priority=False,
        hint_missing_rate=0.0,
        wrong_epoch_rate=0.0,
        straggler_rate=0.0,
        base_write_ns=base.base_write_ns,
        gc_copy_ns=base.gc_copy_ns,
        dogi_ml_ns_per_batch=base.dogi_ml_ns_per_batch,
        dogi_batch_size=base.dogi_batch_size,
        quasar_hint_ns=base.quasar_hint_ns,
        seed=base.seed,
    )


def run_policy_with_retries(base: argparse.Namespace, trace: Path, policy: str, zones: int) -> dict:
    current_zones = zones
    for attempt in range(base.max_retries + 1):
        try:
            row = sim.run_policy(sim_args(base, trace, current_zones), policy)
            row["zones"] = current_zones
            row["initial_zones"] = zones
            row["retries"] = attempt
            row["failed"] = False
            return row
        except RuntimeError as exc:
            if attempt >= base.max_retries:
                return {
                    "policy": policy,
                    "zones": current_zones,
                    "initial_zones": zones,
                    "retries": attempt,
                    "failed": True,
                    "error": str(exc),
                }
            current_zones = int(current_zones * base.retry_growth) + 1
    raise AssertionError("unreachable")


def evaluate(args: argparse.Namespace) -> list[dict]:
    rows = []
    traces = sorted(args.trace_dir.glob("*.jsonl"))
    if not traces:
        raise SystemExit(f"no JSONL traces found under {args.trace_dir}")
    for trace in traces:
        profile = trace.stem
        peak_live = max_live_blocks(trace)
        for op_ratio in args.op_ratios:
            initial_zones = zones_for_pressure(
                trace,
                zone_capacity=args.zone_capacity,
                min_free_zones=args.min_free_zones,
                op_ratio=op_ratio,
            )
            for policy in args.policies:
                row = run_policy_with_retries(args, trace, policy, initial_zones)
                row["experiment"] = "liboqs-kms-stress"
                row["profile"] = profile
                row["workload"] = profile
                row["op_ratio"] = op_ratio
                row["peak_live_blocks"] = peak_live
                rows.append(row)
                if row.get("failed"):
                    print(f"{profile} op={op_ratio} {policy} failed: {row['error']}")
                else:
                    sim.print_row(row)
    return rows


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def reduction(before: float, after: float) -> float | None:
    if before == 0:
        return None
    return (before - after) / before


def summarize(rows: list[dict]) -> dict:
    comparisons = []
    by_case: dict[tuple[str, float], dict[str, dict]] = {}
    for row in rows:
        if row.get("failed"):
            continue
        by_case.setdefault((row["profile"], float(row["op_ratio"])), {})[row["policy"]] = row
    for (profile, op_ratio), policies in sorted(by_case.items()):
        dogi = policies.get("dogi-history")
        hybrid = policies.get("quasar-dogi-hybrid")
        if not dogi or not hybrid:
            continue
        comparisons.append(
            {
                "profile": profile,
                "op_ratio": op_ratio,
                "dogi_waf": dogi["waf"],
                "hybrid_waf": hybrid["waf"],
                "waf_reduction_vs_dogi": reduction(dogi["waf"], hybrid["waf"]),
                "dogi_gc_blocks": dogi["gc_write_blocks"],
                "hybrid_gc_blocks": hybrid["gc_write_blocks"],
                "gc_reduction_vs_dogi": reduction(dogi["gc_write_blocks"], hybrid["gc_write_blocks"]),
                "dogi_stale_secret_blocks": dogi.get("stale_secret_blocks_remaining", 0),
                "hybrid_stale_secret_blocks": hybrid.get("stale_secret_blocks_remaining", 0),
                "stale_secret_blocks_avoided": dogi.get("stale_secret_blocks_remaining", 0)
                - hybrid.get("stale_secret_blocks_remaining", 0),
                "dogi_p99_ns": dogi.get("write_latency_p99_ns", 0),
                "hybrid_p99_ns": hybrid.get("write_latency_p99_ns", 0),
                "zones": dogi.get("zones", 0),
                "initial_zones": dogi.get("initial_zones", 0),
                "retries": max(dogi.get("retries", 0), hybrid.get("retries", 0)),
            }
        )
    waf_values = [item["waf_reduction_vs_dogi"] for item in comparisons if item["waf_reduction_vs_dogi"] is not None]
    return {
        "row_count": len(rows),
        "failed_runs": sum(1 for row in rows if row.get("failed")),
        "comparison_count": len(comparisons),
        "avg_waf_reduction_vs_dogi": sum(waf_values) / len(waf_values) if waf_values else 0.0,
        "total_gc_blocks_saved": sum(item["dogi_gc_blocks"] - item["hybrid_gc_blocks"] for item in comparisons),
        "total_stale_secret_blocks_avoided": sum(item["stale_secret_blocks_avoided"] for item in comparisons),
        "comparisons": comparisons,
    }


def fmt_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def write_markdown(path: Path, generation: list[dict], summary: dict) -> None:
    lines = [
        "# liboqs KMS Stress Summary",
        "",
        f"- Generated profiles: {len(generation)}",
        f"- Evaluation comparisons: {summary['comparison_count']}",
        f"- Failed runs: {summary['failed_runs']}",
        f"- Average WAF reduction vs DOGI: {summary['avg_waf_reduction_vs_dogi'] * 100:.1f}%",
        f"- Total GC blocks saved vs DOGI: {summary['total_gc_blocks_saved']:,}",
        f"- Total stale secret blocks avoided vs DOGI: {summary['total_stale_secret_blocks_avoided']:,}",
        "",
        "## Generated Traces",
        "",
        "| Profile | Sessions | Writes | Expires | Write Blocks | KEM OK | SIG OK |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for item in generation:
        trace = item.get("trace", {})
        lines.append(
            "| `{profile}` | {sessions:,} | {writes:,} | {expires:,} | {blocks:,} | {kem_ok} | {sig_ok} |".format(
                profile=item["profile"],
                sessions=int(item.get("sessions", 0)),
                writes=int(trace.get("writes", 0)),
                expires=int(trace.get("expires", 0)),
                blocks=int(trace.get("write_blocks", 0)),
                kem_ok=item.get("all_kem_ok", False),
                sig_ok=item.get("all_sig_ok", False),
            )
        )
    lines.extend(
        [
            "",
            "## Placement Result",
            "",
            "| Profile | OP Ratio | Zones | DOGI WAF | Hybrid WAF | WAF vs DOGI | GC vs DOGI | Stale Avoided | DOGI p99 ns | Hybrid p99 ns | Retries |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in summary["comparisons"]:
        lines.append(
            "| `{profile}` | {op:.2f} | {zones:,} | {dogi_waf:.3f} | {hybrid_waf:.3f} | {waf} | {gc} | {stale:,} | {dogi_p99:,} | {hybrid_p99:,} | {retries} |".format(
                profile=item["profile"],
                op=item["op_ratio"],
                zones=int(item["zones"]),
                dogi_waf=item["dogi_waf"],
                hybrid_waf=item["hybrid_waf"],
                waf=fmt_pct(item["waf_reduction_vs_dogi"]),
                gc=fmt_pct(item["gc_reduction_vs_dogi"]),
                stale=int(item["stale_secret_blocks_avoided"]),
                dogi_p99=int(item["dogi_p99_ns"]),
                hybrid_p99=int(item["hybrid_p99_ns"]),
                retries=int(item["retries"]),
            )
        )
    lines.extend(
        [
            "",
            "Interpretation:",
            "",
            "- This suite targets the real-PQC WAF pressure point that handshake-only liboqs traces missed.",
            "- The traces execute real `ML-KEM-768` and `ML-DSA-65` operations, then create KMS wrap/update churn with short session lifetimes and frequent rotation epochs.",
            "- The current result should be read as a simulator/replay trace stress, not as an OpenSSL/oqsprovider service measurement.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", type=Path, default=Path("artifacts/traces/liboqs-kms-stress/traces"))
    parser.add_argument("--event-dir", type=Path, default=Path("artifacts/traces/liboqs-kms-stress/events"))
    parser.add_argument("--generation-dir", type=Path, default=Path("artifacts/results/liboqs-kms-stress/generation"))
    parser.add_argument("--eval-out", type=Path, default=Path("artifacts/results/liboqs-kms-stress/eval.json"))
    parser.add_argument("--summary-out", type=Path, default=Path("artifacts/results/liboqs-kms-stress/summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/liboqs-kms-stress/summary.md"))
    parser.add_argument("--kem", default="ML-KEM-768")
    parser.add_argument("--sig", default="ML-DSA-65")
    parser.add_argument("--seed", type=int, default=901)
    parser.add_argument("--zone-capacity", type=int, default=32)
    parser.add_argument("--min-free-zones", type=int, default=2)
    parser.add_argument("--op-ratios", nargs="+", type=float, default=[0.5, 1.0, 2.0])
    parser.add_argument(
        "--policies",
        nargs="+",
        default=["fifo", "sepbit-style", "midas-style", "dogi-history", "quasar-dogi-hybrid", "epoch-oracle"],
    )
    parser.add_argument("--max-retries", type=int, default=6)
    parser.add_argument("--retry-growth", type=float, default=1.35)
    parser.add_argument("--lba-bucket-size", type=int, default=4096)
    parser.add_argument("--quasar-cert-epochs", type=int, default=12)
    parser.add_argument("--quasar-min-epoch-fill", type=float, default=0.0)
    parser.add_argument("--quasar-bin-width", type=int, default=1)
    parser.add_argument("--quasar-open-zone-budget", type=int, default=0)
    parser.add_argument("--quasar-residual-threshold", type=int, default=-1)
    parser.add_argument("--quasar-residual-fraction", type=float, default=0.0)
    parser.add_argument("--base-write-ns", type=int, default=10_000)
    parser.add_argument("--gc-copy-ns", type=int, default=15_000)
    parser.add_argument("--dogi-ml-ns-per-batch", type=int, default=600_000)
    parser.add_argument("--dogi-batch-size", type=int, default=128)
    parser.add_argument("--quasar-hint-ns", type=int, default=200)
    args = parser.parse_args()

    generation = generate_profiles(args)
    rows = evaluate(args)
    summary = summarize(rows)
    write_json(args.eval_out, rows)
    write_json(args.summary_out, {"generation": generation, **summary})
    write_markdown(args.markdown_out, generation, summary)
    print(f"wrote {args.eval_out}")
    print(f"wrote {args.summary_out}")
    print(f"wrote {args.markdown_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
