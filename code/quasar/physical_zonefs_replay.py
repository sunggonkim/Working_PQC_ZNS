#!/usr/bin/env python3
"""Physical zonefs replay for QUASAR append/reset-path evidence.

The default mode is deliberately narrow:

* it writes only to zonefs sequential files,
* it uses direct append (`dd oflag=append,direct`),
* it never issues reset or sanitize commands unless reset flags are explicit,
* it caps the number of appends and blocks per append by default.

With `--include-resets` and `--reset-selected-zones-at-start`, the executor uses
zonefs file truncation as the reset mechanism. This is destructive for selected
zone files and is intended only for dedicated experimental devices.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

try:
    import replay
except ModuleNotFoundError:  # pragma: no cover - used from package tests
    from quasar import replay


def percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * pct / 100.0
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    weight = pos - lower
    return int(round(ordered[lower] * (1 - weight) + ordered[upper] * weight))


def latency_summary(values: list[int]) -> dict[str, Any]:
    return {
        "count": len(values),
        "min_ns": min(values) if values else 0,
        "p50_ns": percentile(values, 50),
        "p95_ns": percentile(values, 95),
        "p99_ns": percentile(values, 99),
        "max_ns": max(values) if values else 0,
        "avg_ns": (sum(values) / len(values)) if values else 0.0,
    }


def numeric_key(path: Path) -> tuple[int, str]:
    try:
        return (int(path.name), path.name)
    except ValueError:
        return (10**18, path.name)


def select_zone_files(
    mount: Path,
    *,
    start_index: int,
    max_zone_files: int,
    require_empty: bool,
) -> list[Path]:
    seq = mount / "seq"
    if not seq.is_dir():
        raise FileNotFoundError(seq)
    selected: list[Path] = []
    for path in sorted((item for item in seq.iterdir() if item.is_file()), key=numeric_key):
        try:
            index = int(path.name)
        except ValueError:
            continue
        if index < start_index:
            continue
        if require_empty and path.stat().st_size != 0:
            continue
        selected.append(path)
        if len(selected) >= max_zone_files:
            break
    if not selected:
        raise RuntimeError("no candidate zonefs sequential files found")
    return selected


def run_dd_append(target: Path, blocks: int) -> dict[str, Any]:
    before = target.stat().st_size
    started = time.perf_counter_ns()
    proc = subprocess.run(
        [
            "dd",
            "if=/dev/zero",
            f"of={target}",
            "bs=4096",
            f"count={blocks}",
            "oflag=append,direct",
            "conv=notrunc",
            "status=none",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    elapsed = time.perf_counter_ns() - started
    after = target.stat().st_size
    return {
        "target": str(target),
        "blocks": blocks,
        "bytes_requested": blocks * 4096,
        "before_size": before,
        "after_size": after,
        "latency_ns": elapsed,
        "returncode": proc.returncode,
        "stderr": proc.stderr[:1000],
        "stdout": proc.stdout[:1000],
        "succeeded": proc.returncode == 0 and after >= before + blocks * 4096,
    }


def run_helper_append(target: Path, blocks: int, helper: Path, *, chunk_blocks: int = 1024) -> dict[str, Any]:
    before = target.stat().st_size
    started = time.perf_counter_ns()
    proc = subprocess.run(
        [str(helper), str(target), str(blocks), str(chunk_blocks)],
        check=False,
        text=True,
        capture_output=True,
    )
    elapsed = time.perf_counter_ns() - started
    after = target.stat().st_size
    helper_payload: dict[str, Any] = {}
    if proc.stdout.strip():
        try:
            helper_payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            helper_payload = {"raw_stdout": proc.stdout[:1000]}
    return {
        "target": str(target),
        "blocks": blocks,
        "bytes_requested": blocks * 4096,
        "before_size": before,
        "after_size": after,
        "latency_ns": elapsed,
        "helper_elapsed_ns": helper_payload.get("elapsed_ns", 0),
        "returncode": proc.returncode,
        "stderr": proc.stderr[:1000],
        "stdout": proc.stdout[:1000],
        "helper": str(helper),
        "succeeded": proc.returncode == 0 and after >= before + blocks * 4096,
    }


def run_truncate_reset(target: Path) -> dict[str, Any]:
    before = target.stat().st_size
    started = time.perf_counter_ns()
    proc = subprocess.run(
        ["truncate", "-s", "0", str(target)],
        check=False,
        text=True,
        capture_output=True,
    )
    elapsed = time.perf_counter_ns() - started
    after = target.stat().st_size
    return {
        "target": str(target),
        "before_size": before,
        "after_size": after,
        "latency_ns": elapsed,
        "returncode": proc.returncode,
        "stderr": proc.stderr[:1000],
        "stdout": proc.stdout[:1000],
        "succeeded": proc.returncode == 0 and after == 0,
    }


def coalesce_adjacent_appends(commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    coalesced: list[dict[str, Any]] = []
    for command in commands:
        if (
            command["op"] == "append"
            and coalesced
            and coalesced[-1]["op"] == "append"
            and coalesced[-1]["family"] == command["family"]
        ):
            coalesced[-1]["blocks"] += int(command["blocks"])
            coalesced[-1]["bytes"] += int(command.get("bytes", int(command["blocks"]) * 4096))
            coalesced[-1]["coalesced_events"] = int(coalesced[-1].get("coalesced_events", 1)) + 1
        else:
            item = dict(command)
            if item["op"] == "append":
                item["coalesced_events"] = 1
            coalesced.append(item)
    return coalesced


def build_replay_plan(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    config = replay.ReplayConfig(
        backend="dry-run",
        device=None,
        zone_capacity=args.zone_capacity,
        emulator_zones=args.max_zone_files,
        emulator_state=None,
        bin_width=args.bin_width,
        cert_epochs=args.cert_epochs,
        min_epoch_fill_blocks=args.min_epoch_fill_blocks,
        execute=False,
    )
    commands, summary = replay.build_plan(args.trace, config)
    reset_commands = [command for command in commands if command["op"] == "reset_family"]
    if args.include_resets:
        selected: list[dict[str, Any]] = []
        appends_seen = 0
        for command in commands:
            if command["op"] == "append":
                if args.max_appends and appends_seen >= args.max_appends:
                    continue
                appends_seen += 1
                selected.append(command)
            elif command["op"] == "reset_family":
                selected.append(command)
        physical_commands = selected
    else:
        physical_commands = [command for command in commands if command["op"] == "append"]
        if args.max_appends:
            physical_commands = physical_commands[: args.max_appends]
    before_coalesce = len(physical_commands)
    if args.coalesce_adjacent_appends:
        physical_commands = coalesce_adjacent_appends(physical_commands)
    summary["physical_commands_before_coalesce"] = before_coalesce
    summary["physical_commands_after_coalesce"] = len(physical_commands)
    summary["physical_append_candidates"] = sum(1 for command in physical_commands if command["op"] == "append")
    summary["physical_reset_commands_skipped"] = len(reset_commands)
    summary["physical_reset_commands_included"] = sum(1 for command in physical_commands if command["op"] == "reset_family")
    return physical_commands, summary


def execute_zonefs(commands: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    zone_files = select_zone_files(
        args.mount,
        start_index=args.start_zone_index,
        max_zone_files=args.max_zone_files,
        require_empty=not (args.allow_nonempty_zone_files or args.reset_selected_zones_at_start),
    )
    free_zones = list(zone_files)
    family_to_zone: dict[str, Path] = {}
    overflow_count = 0
    latencies: list[int] = []
    append_latencies: list[int] = []
    reset_latencies: list[int] = []
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    family_counts: Counter[str] = Counter()
    bytes_written = 0
    reset_commands = 0
    reset_zones = 0
    start_reset_zones = 0
    max_active_zones = 0
    used_zone_files_ever: set[Path] = set()
    started = time.perf_counter_ns()
    if args.execute and args.reset_selected_zones_at_start:
        for zone_file in zone_files:
            result = run_truncate_reset(zone_file)
            start_reset_zones += 1
            reset_latencies.append(int(result["latency_ns"]))
            if not result["succeeded"]:
                failures.append({"op": "initial_reset", **result})
                if args.fail_on_append_error:
                    raise RuntimeError(f"initial zonefs reset failed: {json.dumps(result, sort_keys=True)}")
                break

    for command in commands:
        if failures:
            break
        if command["op"] == "reset_family":
            family = command["family"]
            zone = family_to_zone.pop(family, None)
            reset_commands += 1
            row = {"op": "reset_family", "family": family, "target": str(zone) if zone else None, "ts": command.get("ts")}
            if zone is not None:
                if args.execute:
                    result = run_truncate_reset(zone)
                    row.update(result)
                    if not result["succeeded"]:
                        rows.append(row)
                        failures.append(row)
                        if args.fail_on_append_error:
                            raise RuntimeError(f"physical reset failed: {json.dumps(row, sort_keys=True)}")
                        break
                    reset_latencies.append(int(result["latency_ns"]))
                    latencies.append(int(result["latency_ns"]))
                free_zones.append(zone)
                free_zones.sort(key=numeric_key)
                reset_zones += 1
            rows.append(row)
            continue

        family = command["family"]
        if family not in family_to_zone:
            if not free_zones:
                row = {
                    "op": "append",
                    "family": family,
                    "planned_blocks": int(command["blocks"]),
                    "executed_blocks": 0,
                    "target": None,
                    "ts": command.get("ts"),
                    "succeeded": False,
                    "stderr": "no free zonefs files available",
                }
                rows.append(row)
                failures.append(row)
                if args.fail_on_append_error:
                    raise RuntimeError(f"physical append failed: {json.dumps(row, sort_keys=True)}")
                break
            else:
                family_to_zone[family] = free_zones.pop(0)
                used_zone_files_ever.add(family_to_zone[family])
        max_active_zones = max(max_active_zones, len(family_to_zone))
        planned_blocks = int(command["blocks"])
        blocks_remaining = planned_blocks
        executed_blocks = 0
        target = family_to_zone[family]
        row = {
            "op": "append",
            "family": family,
            "planned_blocks": planned_blocks,
            "executed_blocks": 0,
            "target": str(target),
            "ts": command.get("ts"),
            "coalesced_events": command.get("coalesced_events", 1),
        }
        if args.execute:
            while blocks_remaining > 0:
                chunk = blocks_remaining
                if args.max_blocks_per_append:
                    chunk = min(chunk, args.max_blocks_per_append)
                result = run_dd_append(target, chunk)
                if not result["succeeded"]:
                    row.update(result)
                    rows.append(row)
                    failures.append(row)
                    if args.fail_on_append_error:
                        raise RuntimeError(f"physical append failed: {json.dumps(row, sort_keys=True)}")
                    break
                elapsed = int(result["latency_ns"])
                latencies.append(elapsed)
                append_latencies.append(elapsed)
                bytes_written += int(result["bytes_requested"])
                executed_blocks += chunk
                blocks_remaining -= chunk
            if failures:
                break
            row["executed_blocks"] = executed_blocks
            row["bytes_requested"] = planned_blocks * 4096
            row["succeeded"] = True
        else:
            executed_blocks = planned_blocks
            row["executed_blocks"] = executed_blocks
        rows.append(row)
        family_counts[family] += executed_blocks
    wall_time_ns = time.perf_counter_ns() - started
    wall_s = wall_time_ns / 1_000_000_000
    append_command_count = sum(1 for command in commands if command["op"] == "append")
    return {
        "execute": args.execute,
        "method": "dd-oflag-append-direct",
        "mount": str(args.mount),
        "trace": str(args.trace),
        "reset_issued": bool(args.include_resets or args.reset_selected_zones_at_start),
        "failed": bool(failures),
        "failures": failures[:8],
        "append_commands": append_command_count,
        "reset_family_commands": reset_commands,
        "initial_reset_zones": start_reset_zones,
        "reset_zones": reset_zones,
        "append_commands_attempted": sum(1 for row in rows if row.get("op") == "append"),
        "append_commands_completed": sum(1 for row in rows if row.get("op") == "append" and row.get("succeeded", not args.execute)),
        "dd_append_ops": len(append_latencies),
        "unique_families": len(family_counts),
        "zone_files_available": len(zone_files),
        "zone_files_used": len(used_zone_files_ever),
        "max_active_zone_files": max_active_zones,
        "final_active_zone_files": len(family_to_zone),
        "overflow_family_assignments": overflow_count,
        "bytes_written": bytes_written,
        "wall_time_ns": wall_time_ns,
        "wall_time_s": wall_s,
        "throughput_mib_s": (bytes_written / (1024 * 1024) / wall_s) if wall_s and args.execute else 0.0,
        "append_ops_s": (len(latencies) / wall_s) if wall_s and args.execute else 0.0,
        "latency": latency_summary(latencies),
        "append_latency": latency_summary(append_latencies),
        "reset_latency": latency_summary(reset_latencies),
        "family_to_zone": {family: str(path) for family, path in sorted(family_to_zone.items())},
        "family_blocks": dict(sorted(family_counts.items())),
        "rows": rows[: args.max_rows_in_output],
        "row_count": len(rows),
        "notes": [
            (
                "Zonefs truncate resets were issued for selected zone files."
                if bool(args.include_resets or args.reset_selected_zones_at_start)
                else "No zone reset or sanitize command was issued."
            ),
            "No NVMe sanitize command was issued.",
            (
                "This run includes trace reset-family commands."
                if args.include_resets
                else "This is a physical append-path smoke, not a full WAF experiment."
            ),
        ],
    }


def markdown(report: dict[str, Any], plan_summary: dict[str, Any]) -> str:
    lines = [
        "# Physical Zonefs Replay",
        "",
        f"- Executed: `{report['execute']}`",
        f"- Method: `{report['method']}`",
        f"- Trace: `{report['trace']}`",
        f"- Mount: `{report['mount']}`",
        f"- Reset issued: `{report['reset_issued']}`",
        f"- Failed: `{report.get('failed', False)}`",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| append commands | {report['append_commands']} |",
        f"| append commands attempted | {report.get('append_commands_attempted', report['append_commands'])} |",
        f"| append commands completed | {report.get('append_commands_completed', report['append_commands'])} |",
        f"| dd append ops | {report.get('dd_append_ops', 0)} |",
        f"| reset family commands | {report.get('reset_family_commands', 0)} |",
        f"| initial reset zones | {report.get('initial_reset_zones', 0)} |",
        f"| reset zones | {report.get('reset_zones', 0)} |",
        f"| unique families | {report['unique_families']} |",
        f"| zone files used | {report['zone_files_used']} |",
        f"| max active zone files | {report.get('max_active_zone_files', 0)} |",
        f"| final active zone files | {report.get('final_active_zone_files', 0)} |",
        f"| bytes written | {report['bytes_written']} |",
        f"| wall time s | {report['wall_time_s']:.6f} |",
        f"| throughput MiB/s | {report['throughput_mib_s']:.3f} |",
        f"| append ops/s | {report['append_ops_s']:.3f} |",
        f"| p50 append latency ns | {report['latency']['p50_ns']} |",
        f"| p95 append latency ns | {report['latency']['p95_ns']} |",
        f"| p99 append latency ns | {report['latency']['p99_ns']} |",
        f"| skipped reset-family commands in source plan | {plan_summary.get('physical_reset_commands_skipped', 0)} |",
        "",
        "## Family Mapping",
        "",
        "| Family | Zonefs File | Blocks |",
        "| --- | --- | ---: |",
    ]
    for family, target in sorted(report["family_to_zone"].items()):
        lines.append(f"| `{family}` | `{target}` | {report['family_blocks'].get(family, 0)} |")
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in report["notes"])
    if report.get("failures"):
        lines.extend(["", "## First Failure", ""])
        first = report["failures"][0]
        lines.extend(
            [
                f"- Target: `{first.get('target')}`",
                f"- Family: `{first.get('family')}`",
                f"- Return code: `{first.get('returncode')}`",
                f"- stderr: `{first.get('stderr', '').strip()}`",
            ]
        )
    return "\n".join(lines) + "\n"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--mount", type=Path, default=Path("/mnt/zn540"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-appends", type=int, default=64)
    parser.add_argument("--max-blocks-per-append", type=int, default=1)
    parser.add_argument("--max-zone-files", type=int, default=8)
    parser.add_argument("--start-zone-index", type=int, default=10)
    parser.add_argument("--allow-nonempty-zone-files", action="store_true")
    parser.add_argument("--zone-capacity", type=int, default=512)
    parser.add_argument("--bin-width", type=int, default=4)
    parser.add_argument("--cert-epochs", type=int, default=8)
    parser.add_argument("--min-epoch-fill-blocks", type=int, default=1)
    parser.add_argument("--max-rows-in-output", type=int, default=128)
    parser.add_argument("--fail-on-append-error", action="store_true")
    parser.add_argument("--include-resets", action="store_true")
    parser.add_argument("--reset-selected-zones-at-start", action="store_true")
    parser.add_argument("--coalesce-adjacent-appends", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/physical-zonefs-replay.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/physical-zonefs-replay.md"))
    args = parser.parse_args()

    if args.max_appends < 0:
        raise SystemExit("--max-appends must be non-negative")
    if args.max_blocks_per_append < 0:
        raise SystemExit("--max-blocks-per-append must be non-negative")
    commands, plan_summary = build_replay_plan(args)
    report = execute_zonefs(commands, args)
    report["plan_summary"] = plan_summary
    write_json(args.out, report)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text(markdown(report, plan_summary), encoding="utf-8")
    print(
        json.dumps(
            {
                "execute": report["execute"],
                "append_commands": report["append_commands"],
                "bytes_written": report["bytes_written"],
                "reset_issued": report["reset_issued"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
