#!/usr/bin/env python3
"""Run file-ZNS replay latency/throughput checks on representative traces."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

try:
    import replay
except ModuleNotFoundError:  # pragma: no cover - root-level unittest discovery
    from quasar import replay


DEFAULT_TRACES = [
    Path("artifacts/traces/liboqs-profiles/traces/kms-rotation.jsonl"),
    Path("artifacts/traces/liboqs-profiles/traces/mixed-service.jsonl"),
    Path("artifacts/traces/dogi-paper-ratio-sweep-50k/exchange-pqc2000.jsonl"),
]


def trace_label(path: Path) -> str:
    return path.stem.replace(".jsonl", "")


def run_one(
    trace: Path,
    *,
    out_dir: Path,
    zone_capacity: int,
    emulator_zones: int,
    bin_width: int,
    cert_epochs: int,
    min_epoch_fill_blocks: int,
) -> dict:
    label = trace_label(trace)
    state = out_dir / f"{label}-file-zns-state.json"
    summary_out = out_dir / f"{label}-file-zns-summary.json"
    config = replay.ReplayConfig(
        backend="file-zns",
        device=None,
        zone_capacity=zone_capacity,
        emulator_zones=emulator_zones,
        emulator_state=state,
        bin_width=bin_width,
        cert_epochs=cert_epochs,
        min_epoch_fill_blocks=min_epoch_fill_blocks,
        execute=True,
    )
    started = time.perf_counter_ns()
    commands, summary = replay.build_plan(trace, config)
    replay.add_planner_metrics(summary, time.perf_counter_ns() - started)
    replay.execute_plan(commands, config)
    summary.update(replay.load_json(state)["summary"])
    summary["trace_label"] = label
    summary["summary_path"] = str(summary_out)
    replay.write_json(summary_out, summary)
    return summary


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {"trace_count": 0, "total_append_commands": 0, "total_reset_family_commands": 0}
    total_wall_ns = sum(int(row.get("emulator_wall_time_ns", 0)) for row in rows)
    total_bytes = sum(int(row.get("emulator_bytes_written", 0)) for row in rows)
    total_appends = sum(int(row.get("append_commands", 0)) for row in rows)
    total_resets = sum(int(row.get("reset_family_commands", 0)) for row in rows)
    wall_s = total_wall_ns / 1_000_000_000 if total_wall_ns else 0.0
    return {
        "trace_count": len(rows),
        "total_append_commands": total_appends,
        "total_reset_family_commands": total_resets,
        "total_emulator_wall_time_ns": total_wall_ns,
        "total_emulator_wall_time_s": wall_s,
        "total_emulator_bytes_written": total_bytes,
        "aggregate_emulator_throughput_mib_s": (total_bytes / (1024 * 1024) / wall_s) if wall_s else 0.0,
        "aggregate_emulator_append_ops_s": (total_appends / wall_s) if wall_s else 0.0,
    }


def ns_to_us(value: float | int) -> str:
    return f"{float(value) / 1000.0:.1f}"


def write_markdown(path: Path, rows: list[dict], aggregate: dict) -> None:
    lines = [
        "# Replay-Level Latency Suite",
        "",
        "Backend: `file-zns` JSON-backed ZNS emulator. These numbers measure replay-path CPU/emulator latency, not physical SSD latency.",
        "",
        "## Aggregate",
        "",
        f"- Traces: `{aggregate['trace_count']}`",
        f"- Total appends: `{aggregate['total_append_commands']:,}`",
        f"- Total reset-family commands: `{aggregate['total_reset_family_commands']:,}`",
        f"- Aggregate throughput: `{aggregate['aggregate_emulator_throughput_mib_s']:.2f}` MiB/s",
        f"- Aggregate append ops: `{aggregate['aggregate_emulator_append_ops_s']:.2f}` ops/s",
        "",
        "## Per-Trace Result",
        "",
        "| Trace | Events | Appends | Resets | Planner ns/event | Wall ms | Throughput MiB/s | Append p99 us | Reset p99 us | Max Used Zones |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| `{trace}` | {events:,} | {appends:,} | {resets:,} | {planner:.1f} | {wall:.2f} | {throughput:.2f} | {append_p99} | {reset_p99} | {zones:,} |".format(
                trace=row["trace_label"],
                events=int(row.get("trace_events", 0)),
                appends=int(row.get("append_commands", 0)),
                resets=int(row.get("reset_family_commands", 0)),
                planner=float(row.get("planner_ns_per_trace_event", 0.0)),
                wall=float(row.get("emulator_wall_time_ns", 0)) / 1_000_000.0,
                throughput=float(row.get("emulator_throughput_mib_s", 0.0)),
                append_p99=ns_to_us(row.get("emulator_append_latency_p99_ns", 0)),
                reset_p99=ns_to_us(row.get("emulator_reset_family_latency_p99_ns", 0)),
                zones=int(row.get("emulator_max_used_zones", 0)),
            )
        )
    lines.extend(
        [
            "",
            "Interpretation:",
            "",
            "- This closes the local replay-level measurement gap for file-backed ZNS emulation.",
            "- It does not replace physical ZNS/FDP measurements; physical append/reset latency remains a separate external gap.",
            "- The useful comparison point is stability across traces and whether reset-heavy PQC traces cause replay-path spikes.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--traces", nargs="+", type=Path, default=DEFAULT_TRACES)
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/results/replay-latency"))
    parser.add_argument("--json-out", type=Path, default=Path("artifacts/results/replay-latency/summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/replay-latency/summary.md"))
    parser.add_argument("--zone-capacity", type=int, default=512)
    parser.add_argument("--emulator-zones", type=int, default=4096)
    parser.add_argument("--bin-width", type=int, default=1)
    parser.add_argument("--cert-epochs", type=int, default=12)
    parser.add_argument("--min-epoch-fill-blocks", type=int, default=1)
    parser.add_argument("--skip-missing", action="store_true")
    args = parser.parse_args()

    rows: list[dict] = []
    for trace in args.traces:
        if not trace.exists():
            if args.skip_missing:
                continue
            raise FileNotFoundError(trace)
        rows.append(
            run_one(
                trace,
                out_dir=args.out_dir,
                zone_capacity=args.zone_capacity,
                emulator_zones=args.emulator_zones,
                bin_width=args.bin_width,
                cert_epochs=args.cert_epochs,
                min_epoch_fill_blocks=args.min_epoch_fill_blocks,
            )
        )
    aggregate = summarize(rows)
    replay.write_json(args.json_out, {"aggregate": aggregate, "traces": rows})
    write_markdown(args.markdown_out, rows, aggregate)
    print(f"wrote {args.json_out}")
    print(f"wrote {args.markdown_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
