#!/usr/bin/env python3
"""QUASAR replay scaffold for ZNS/FDP experiments.

The default backend is `dry-run`: it reads a rich JSONL trace, applies the same
intent/epoch placement contract used by QUASAR, and emits an executable-looking
plan without touching a device. The `file-zns` backend executes the plan against
a JSON-backed ZNS emulator, which makes append/reset semantics testable on
machines without xNVMe/SPDK/ZNS hardware while preserving the boundary needed
for later real-device experiments.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


SECRET_INTENTS = {"EPHEMERAL_SECRET", "KEM_ARTIFACT"}
RESETTABLE_FAMILIES = {"EPOCH_SECRET", "EPOCH_BIN", "ROTATION"}


def percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * (pct / 100.0)
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    weight = pos - lower
    return int(round(ordered[lower] * (1.0 - weight) + ordered[upper] * weight))


def latency_stats(prefix: str, values: list[int]) -> dict:
    if not values:
        return {
            f"{prefix}_count": 0,
            f"{prefix}_latency_min_ns": 0,
            f"{prefix}_latency_p50_ns": 0,
            f"{prefix}_latency_p95_ns": 0,
            f"{prefix}_latency_p99_ns": 0,
            f"{prefix}_latency_max_ns": 0,
            f"{prefix}_latency_avg_ns": 0.0,
        }
    return {
        f"{prefix}_count": len(values),
        f"{prefix}_latency_min_ns": min(values),
        f"{prefix}_latency_p50_ns": percentile(values, 50),
        f"{prefix}_latency_p95_ns": percentile(values, 95),
        f"{prefix}_latency_p99_ns": percentile(values, 99),
        f"{prefix}_latency_max_ns": max(values),
        f"{prefix}_latency_avg_ns": sum(values) / len(values),
    }


def execution_stats(prefix: str, *, wall_time_ns: int, bytes_written: int, commands: int, appends: int) -> dict:
    wall_s = wall_time_ns / 1_000_000_000 if wall_time_ns > 0 else 0.0
    mib = bytes_written / (1024 * 1024)
    return {
        f"{prefix}_wall_time_ns": wall_time_ns,
        f"{prefix}_wall_time_s": wall_s,
        f"{prefix}_throughput_mib_s": (mib / wall_s) if wall_s else 0.0,
        f"{prefix}_command_ops_s": (commands / wall_s) if wall_s else 0.0,
        f"{prefix}_append_ops_s": (appends / wall_s) if wall_s else 0.0,
    }


@dataclass(frozen=True)
class ReplayConfig:
    backend: str
    device: Optional[str]
    zone_capacity: int
    emulator_zones: int
    emulator_state: Optional[Path]
    bin_width: int
    cert_epochs: int
    min_epoch_fill_blocks: int
    execute: bool
    allow_non_nullblk_device: bool = False


def tool_for_backend(backend: str) -> Optional[str]:
    return {
        "dry-run": None,
        "file-zns": None,
        "blkzone-zns": "blkzone",
        "nvme-zns": "nvme",
        "xnvme": "xnvme",
        "spdk": "spdk_nvme_perf",
    }.get(backend)


def backend_status(backend: str) -> dict:
    tool = tool_for_backend(backend)
    if tool is None:
        return {"backend": backend, "required_tool": None, "available": True, "path": None}
    path = shutil.which(tool)
    return {"backend": backend, "required_tool": tool, "available": path is not None, "path": path}


class FileZnsEmulator:
    def __init__(self, *, zone_count: int, zone_capacity: int) -> None:
        self.zone_count = zone_count
        self.zone_capacity = zone_capacity
        self.zones = [
            {"zone_id": zone_id, "family": None, "written_blocks": 0, "state": "empty"}
            for zone_id in range(zone_count)
        ]
        self.active_by_family: dict[str, int] = {}
        self.append_commands = 0
        self.reset_commands = 0
        self.reset_zones = 0
        self.opened_zones = 0
        self.max_used_zones = 0
        self.bytes_written = 0
        self.wall_time_ns = 0
        self.command_latencies_ns: list[int] = []
        self.append_latencies_ns: list[int] = []
        self.reset_latencies_ns: list[int] = []

    def _used_zones(self) -> int:
        return sum(1 for zone in self.zones if zone["state"] != "empty")

    def _note_used(self) -> None:
        self.max_used_zones = max(self.max_used_zones, self._used_zones())

    def _open_zone(self, family: str) -> int:
        for zone in self.zones:
            if zone["state"] == "empty":
                zone["family"] = family
                zone["written_blocks"] = 0
                zone["state"] = "open"
                self.active_by_family[family] = zone["zone_id"]
                self.opened_zones += 1
                self._note_used()
                return zone["zone_id"]
        raise RuntimeError("file-zns emulator out of zones")

    def append(self, family: str, blocks: int) -> None:
        remaining = blocks
        while remaining > 0:
            zone_id = self.active_by_family.get(family)
            if zone_id is None:
                zone_id = self._open_zone(family)
            zone = self.zones[zone_id]
            free = self.zone_capacity - int(zone["written_blocks"])
            if free <= 0:
                zone["state"] = "closed"
                self.active_by_family.pop(family, None)
                continue
            write_blocks = min(remaining, free)
            zone["written_blocks"] = int(zone["written_blocks"]) + write_blocks
            self.bytes_written += write_blocks * 4096
            remaining -= write_blocks
            if int(zone["written_blocks"]) == self.zone_capacity:
                zone["state"] = "closed"
                self.active_by_family.pop(family, None)
        self.append_commands += 1

    def reset_family(self, family: str) -> None:
        self.reset_commands += 1
        for zone in self.zones:
            if zone["family"] != family:
                continue
            zone["family"] = None
            zone["written_blocks"] = 0
            zone["state"] = "empty"
            self.reset_zones += 1
        self.active_by_family.pop(family, None)

    def execute(self, commands: list[dict]) -> dict:
        started = time.perf_counter_ns()
        try:
            for command in commands:
                op_started = time.perf_counter_ns()
                if command["op"] == "append":
                    self.append(command["family"], int(command["blocks"]))
                    elapsed = time.perf_counter_ns() - op_started
                    self.append_latencies_ns.append(elapsed)
                    self.command_latencies_ns.append(elapsed)
                elif command["op"] == "reset_family":
                    self.reset_family(command["family"])
                    elapsed = time.perf_counter_ns() - op_started
                    self.reset_latencies_ns.append(elapsed)
                    self.command_latencies_ns.append(elapsed)
        finally:
            self.wall_time_ns += time.perf_counter_ns() - started
        return self.summary()

    def summary(self) -> dict:
        used = self._used_zones()
        written_blocks = sum(int(zone["written_blocks"]) for zone in self.zones)
        family_zone_counts: Counter[str] = Counter(
            str(zone["family"]) for zone in self.zones if zone["family"] is not None
        )
        result = {
            "emulator_zone_count": self.zone_count,
            "emulator_zone_capacity": self.zone_capacity,
            "emulator_append_commands": self.append_commands,
            "emulator_reset_commands": self.reset_commands,
            "emulator_reset_zones": self.reset_zones,
            "emulator_opened_zones": self.opened_zones,
            "emulator_max_used_zones": self.max_used_zones,
            "emulator_final_used_zones": used,
            "emulator_final_written_blocks": written_blocks,
            "emulator_bytes_written": self.bytes_written,
            "emulator_family_zone_counts": dict(sorted(family_zone_counts.items())),
        }
        result.update(
            execution_stats(
                "emulator",
                wall_time_ns=self.wall_time_ns,
                bytes_written=self.bytes_written,
                commands=len(self.command_latencies_ns),
                appends=self.append_commands,
            )
        )
        result.update(latency_stats("emulator_command", self.command_latencies_ns))
        result.update(latency_stats("emulator_append", self.append_latencies_ns))
        result.update(latency_stats("emulator_reset_family", self.reset_latencies_ns))
        return result


def read_int(path: Path) -> int:
    return int(path.read_text(encoding="utf-8").strip())


def device_name(device: str) -> str:
    return Path(device).name


def device_is_nullblk(device: str) -> bool:
    return device_name(device).startswith("nullb")


def sysfs_queue(device: str) -> Path:
    return Path("/sys/block") / device_name(device) / "queue"


def run_checked(args: list[str]) -> None:
    proc = subprocess.run(args, check=False, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed rc={proc.returncode}: {' '.join(args)}\n"
            f"stdout={proc.stdout[:1000]}\nstderr={proc.stderr[:1000]}"
        )


class BlkzoneZnsExecutor:
    def __init__(self, *, device: str, allow_non_nullblk_device: bool = False, write_chunk_blocks: int = 256) -> None:
        if not allow_non_nullblk_device and not device_is_nullblk(device):
            raise RuntimeError(
                "blkzone-zns execution is guarded to /dev/nullb* by default; "
                "pass --allow-non-nullblk-device only after verifying the target can be reset"
            )
        queue = sysfs_queue(device)
        zoned = (queue / "zoned").read_text(encoding="utf-8").strip()
        if zoned == "none":
            raise RuntimeError(f"{device} is not a zoned block device")
        self.device = device
        self.queue = queue
        self.logical_block_size = read_int(queue / "logical_block_size")
        self.zone_size_bytes = read_int(queue / "chunk_sectors") * 512
        self.zone_count = read_int(queue / "nr_zones")
        self.blocks_per_zone = self.zone_size_bytes // 4096
        self.write_chunk_blocks = max(1, write_chunk_blocks)
        self.free_zones = list(range(self.zone_count))
        self.active_by_family: dict[str, int] = {}
        self.family_zones: dict[str, list[int]] = defaultdict(list)
        self.zone_written_blocks: dict[int, int] = {}
        self.append_commands = 0
        self.reset_commands = 0
        self.reset_zones = 0
        self.opened_zones = 0
        self.max_used_zones = 0
        self.bytes_written = 0
        self.wall_time_ns = 0
        self.prepare_latency_ns = 0
        self.fsync_latency_ns = 0
        self.command_latencies_ns: list[int] = []
        self.append_latencies_ns: list[int] = []
        self.reset_latencies_ns: list[int] = []

    def _used_zones(self) -> int:
        return self.zone_count - len(self.free_zones)

    def _note_used(self) -> None:
        self.max_used_zones = max(self.max_used_zones, self._used_zones())

    def _zone_offset(self, zone_id: int) -> int:
        return zone_id * self.zone_size_bytes

    def _zone_sector(self, zone_id: int) -> int:
        return self._zone_offset(zone_id) // 512

    def _reset_zone(self, zone_id: int) -> None:
        run_checked(
            [
                "blkzone",
                "reset",
                "-o",
                str(self._zone_sector(zone_id)),
                "-l",
                str(self.zone_size_bytes // 512),
                self.device,
            ]
        )
        self.reset_zones += 1

    def reset_all_zones(self) -> None:
        run_checked(["blkzone", "reset", self.device])
        self.free_zones = list(range(self.zone_count))
        self.active_by_family.clear()
        self.family_zones.clear()
        self.zone_written_blocks.clear()

    def _open_zone(self, family: str) -> int:
        if not self.free_zones:
            raise RuntimeError("blkzone-zns executor out of physical zones")
        zone_id = self.free_zones.pop(0)
        self.active_by_family[family] = zone_id
        self.family_zones[family].append(zone_id)
        self.zone_written_blocks[zone_id] = 0
        self.opened_zones += 1
        self._note_used()
        return zone_id

    def _write_blocks(self, fd: int, zone_id: int, blocks: int) -> None:
        remaining = blocks
        while remaining:
            written_blocks = self.zone_written_blocks[zone_id]
            zone_free = self.blocks_per_zone - written_blocks
            if zone_free <= 0:
                return
            chunk_blocks = min(remaining, zone_free, self.write_chunk_blocks)
            offset = self._zone_offset(zone_id) + written_blocks * 4096
            data = bytes(chunk_blocks * 4096)
            os.pwrite(fd, data, offset)
            self.zone_written_blocks[zone_id] += chunk_blocks
            self.bytes_written += len(data)
            remaining -= chunk_blocks

    def append(self, fd: int, family: str, blocks: int) -> None:
        remaining = blocks
        while remaining:
            zone_id = self.active_by_family.get(family)
            if zone_id is None:
                zone_id = self._open_zone(family)
            free = self.blocks_per_zone - self.zone_written_blocks[zone_id]
            if free <= 0:
                self.active_by_family.pop(family, None)
                continue
            chunk_blocks = min(remaining, free)
            self._write_blocks(fd, zone_id, chunk_blocks)
            remaining -= chunk_blocks
            if self.zone_written_blocks[zone_id] >= self.blocks_per_zone:
                self.active_by_family.pop(family, None)
        self.append_commands += 1

    def reset_family(self, family: str) -> None:
        self.reset_commands += 1
        zones = self.family_zones.pop(family, [])
        self.active_by_family.pop(family, None)
        for zone_id in zones:
            self._reset_zone(zone_id)
            self.zone_written_blocks.pop(zone_id, None)
            self.free_zones.append(zone_id)
        self.free_zones.sort()

    def execute(self, commands: list[dict]) -> dict:
        started = time.perf_counter_ns()
        prepare_started = time.perf_counter_ns()
        self.reset_all_zones()
        self.prepare_latency_ns = time.perf_counter_ns() - prepare_started
        fd = os.open(self.device, os.O_RDWR | getattr(os, "O_SYNC", 0))
        try:
            for command in commands:
                op_started = time.perf_counter_ns()
                if command["op"] == "append":
                    self.append(fd, command["family"], int(command["blocks"]))
                    elapsed = time.perf_counter_ns() - op_started
                    self.append_latencies_ns.append(elapsed)
                    self.command_latencies_ns.append(elapsed)
                elif command["op"] == "reset_family":
                    self.reset_family(command["family"])
                    elapsed = time.perf_counter_ns() - op_started
                    self.reset_latencies_ns.append(elapsed)
                    self.command_latencies_ns.append(elapsed)
            fsync_started = time.perf_counter_ns()
            os.fsync(fd)
            self.fsync_latency_ns = time.perf_counter_ns() - fsync_started
        finally:
            os.close(fd)
            self.wall_time_ns += time.perf_counter_ns() - started
        return self.summary()

    def summary(self) -> dict:
        result = {
            "real_backend": "blkzone-zns",
            "real_device": self.device,
            "real_logical_block_size": self.logical_block_size,
            "real_zone_size_bytes": self.zone_size_bytes,
            "real_zone_count": self.zone_count,
            "real_blocks_per_zone_4k": self.blocks_per_zone,
            "real_append_commands": self.append_commands,
            "real_reset_commands": self.reset_commands,
            "real_reset_zones": self.reset_zones,
            "real_opened_zones": self.opened_zones,
            "real_max_used_zones": self.max_used_zones,
            "real_final_used_zones": self._used_zones(),
            "real_bytes_written": self.bytes_written,
        }
        result.update(
            execution_stats(
                "real",
                wall_time_ns=self.wall_time_ns,
                bytes_written=self.bytes_written,
                commands=len(self.command_latencies_ns),
                appends=self.append_commands,
            )
        )
        result["real_prepare_latency_ns"] = self.prepare_latency_ns
        result["real_fsync_latency_ns"] = self.fsync_latency_ns
        result.update(latency_stats("real_command", self.command_latencies_ns))
        result.update(latency_stats("real_append", self.append_latencies_ns))
        result.update(latency_stats("real_reset_family", self.reset_latencies_ns))
        return result


def family_for(row: dict, *, bin_width: int, cert_epochs: int, epoch_seen_blocks: Counter[tuple[str, int]], min_epoch_fill_blocks: int) -> str:
    confidence = row.get("confidence", "exact")
    intent = row.get("intent", "UNKNOWN")
    if confidence == "UNKNOWN" or intent == "UNKNOWN":
        return f"OVERFLOW:{row.get('expire_class', 'UNKNOWN')}"
    epoch_id = int(row.get("epoch_id", 0))
    security = row.get("security_class", "SECRET")
    if intent in SECRET_INTENTS:
        seen_key = (intent, epoch_id)
        epoch_seen_blocks[seen_key] += int(row["size_blocks"])
        if epoch_seen_blocks[seen_key] >= min_epoch_fill_blocks:
            return f"EPOCH_SECRET:e{epoch_id}:{intent}:{security}"
        return f"EPOCH_BIN:b{epoch_id // max(1, bin_width)}:{intent}:{security}"
    if intent == "CERT_METADATA":
        return f"ROTATION:r{epoch_id // max(1, cert_epochs)}:{intent}"
    if intent == "SIGNATURE_LOG":
        return "APPEND_LOG:SIGNATURE_LOG"
    if intent == "PAYLOAD":
        return "PAYLOAD"
    return "OVERFLOW:UNKNOWN"


def family_type(family: str) -> str:
    return family.split(":", 1)[0]


def iter_trace(path: Path):
    with path.open("r", encoding="utf-8") as src:
        for line in src:
            if line.strip():
                yield json.loads(line)


def build_plan(trace: Path, config: ReplayConfig) -> tuple[list[dict], dict]:
    commands: list[dict] = []
    object_family: dict[int, str] = {}
    object_blocks: dict[int, int] = {}
    family_live_blocks: Counter[str] = Counter()
    family_write_blocks: Counter[str] = Counter()
    family_resets: Counter[str] = Counter()
    epoch_seen_blocks: Counter[tuple[str, int]] = Counter()
    intent_counts: Counter[str] = Counter()
    backend = backend_status(config.backend)
    trace_events = 0
    write_events = 0
    expire_events = 0

    for row in iter_trace(trace):
        trace_events += 1
        ts = int(row["ts"])
        if row["op"] == "write":
            write_events += 1
            family = family_for(
                row,
                bin_width=config.bin_width,
                cert_epochs=config.cert_epochs,
                epoch_seen_blocks=epoch_seen_blocks,
                min_epoch_fill_blocks=config.min_epoch_fill_blocks,
            )
            object_id = int(row["object_id"])
            blocks = int(row["size_blocks"])
            object_family[object_id] = family
            object_blocks[object_id] = blocks
            family_live_blocks[family] += blocks
            family_write_blocks[family] += blocks
            intent_counts[row.get("intent", "UNKNOWN")] += 1
            commands.append(
                {
                    "op": "append",
                    "ts": ts,
                    "backend": config.backend,
                    "device": config.device,
                    "family": family,
                    "lba": int(row["lba"]),
                    "blocks": blocks,
                    "bytes": blocks * 4096,
                }
            )
        elif row["op"] == "expire":
            expire_events += 1
            object_id = int(row["object_id"])
            family = object_family.pop(object_id, None)
            blocks = object_blocks.pop(object_id, 0)
            if family is None:
                continue
            family_live_blocks[family] = max(0, family_live_blocks[family] - blocks)
            if family_live_blocks[family] == 0 and family_type(family) in RESETTABLE_FAMILIES:
                family_resets[family] += 1
                commands.append(
                    {
                        "op": "reset_family",
                        "ts": ts,
                        "backend": config.backend,
                        "device": config.device,
                        "family": family,
                        "reason": "all tracked objects expired",
                    }
                )
    append_blocks = sum(command.get("blocks", 0) for command in commands if command["op"] == "append")
    summary = {
        "trace": str(trace),
        "backend": config.backend,
        "device": config.device,
        "execute": config.execute,
        "backend_status": backend,
        "trace_events": trace_events,
        "write_events": write_events,
        "expire_events": expire_events,
        "commands": len(commands),
        "append_commands": sum(1 for command in commands if command["op"] == "append"),
        "reset_family_commands": sum(1 for command in commands if command["op"] == "reset_family"),
        "append_blocks": append_blocks,
        "family_count": len(family_write_blocks),
        "family_write_blocks": dict(sorted(family_write_blocks.items())),
        "family_reset_count": dict(sorted(family_resets.items())),
        "intent_counts": dict(sorted(intent_counts.items())),
        "dry_run_only": not config.execute,
    }
    return commands, summary


def add_planner_metrics(summary: dict, wall_time_ns: int) -> None:
    trace_events = int(summary.get("trace_events", 0))
    commands = int(summary.get("commands", 0))
    wall_s = wall_time_ns / 1_000_000_000 if wall_time_ns > 0 else 0.0
    summary["planner_wall_time_ns"] = wall_time_ns
    summary["planner_wall_time_s"] = wall_s
    summary["planner_events_s"] = (trace_events / wall_s) if wall_s else 0.0
    summary["planner_commands_s"] = (commands / wall_s) if wall_s else 0.0
    summary["planner_ns_per_trace_event"] = (wall_time_ns / trace_events) if trace_events else 0.0
    summary["planner_ns_per_command"] = (wall_time_ns / commands) if commands else 0.0


def execute_plan(commands: list[dict], config: ReplayConfig) -> None:
    status = backend_status(config.backend)
    if config.backend == "dry-run":
        return
    if config.backend == "file-zns":
        emulator = FileZnsEmulator(zone_count=config.emulator_zones, zone_capacity=config.zone_capacity)
        result = emulator.execute(commands)
        if config.emulator_state:
            write_json(
                config.emulator_state,
                {
                    "backend": "file-zns",
                    "summary": result,
                    "zones": emulator.zones,
                },
            )
        return
    if config.backend == "blkzone-zns":
        if not status["available"]:
            raise RuntimeError("blkzone is required for blkzone-zns execution")
        if not config.device:
            raise RuntimeError("--device is required for blkzone-zns execution")
        executor = BlkzoneZnsExecutor(
            device=config.device,
            allow_non_nullblk_device=config.allow_non_nullblk_device,
        )
        result = executor.execute(commands)
        if config.emulator_state:
            write_json(
                config.emulator_state,
                {
                    "backend": "blkzone-zns",
                    "summary": result,
                },
            )
        return
    if not status["available"]:
        raise RuntimeError(f"backend tool {status['required_tool']} is not available")
    if not config.device:
        raise RuntimeError("--device is required when --execute is used")
    raise RuntimeError(
        "real-device execution is intentionally not implemented in this scaffold; "
        "use --plan-out to inspect commands, then bind a backend-specific executor"
    )


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--backend", choices=["dry-run", "file-zns", "blkzone-zns", "nvme-zns", "xnvme", "spdk"], default="dry-run")
    parser.add_argument("--device")
    parser.add_argument("--zone-capacity", type=int, default=512)
    parser.add_argument("--emulator-zones", type=int, default=2048)
    parser.add_argument("--emulator-state", type=Path)
    parser.add_argument("--bin-width", type=int, default=1)
    parser.add_argument("--cert-epochs", type=int, default=12)
    parser.add_argument("--min-epoch-fill-blocks", type=int, default=1)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-non-nullblk-device", action="store_true")
    parser.add_argument("--plan-out", type=Path)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()

    config = ReplayConfig(
        backend=args.backend,
        device=args.device,
        zone_capacity=args.zone_capacity,
        emulator_zones=args.emulator_zones,
        emulator_state=args.emulator_state,
        bin_width=args.bin_width,
        cert_epochs=args.cert_epochs,
        min_epoch_fill_blocks=args.min_epoch_fill_blocks,
        execute=args.execute,
        allow_non_nullblk_device=args.allow_non_nullblk_device,
    )
    plan_started = time.perf_counter_ns()
    commands, summary = build_plan(args.trace, config)
    add_planner_metrics(summary, time.perf_counter_ns() - plan_started)
    if args.execute:
        execute_plan(commands, config)
        summary["dry_run_only"] = False
        if args.backend == "file-zns" and args.emulator_state:
            state = load_json(args.emulator_state)
            summary.update(state["summary"])
        if args.backend == "blkzone-zns" and args.emulator_state:
            state = load_json(args.emulator_state)
            summary.update(state["summary"])
    if args.plan_out:
        write_json(args.plan_out, commands)
        print(f"wrote plan={args.plan_out}")
    if args.summary_out:
        write_json(args.summary_out, summary)
        print(f"wrote summary={args.summary_out}")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
