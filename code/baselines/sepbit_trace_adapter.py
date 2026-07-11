#!/usr/bin/env python3
"""Adapt QUASAR JSONL traces to the SepBIT trace_replay Ali format."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


BLOCK_SIZE = 4096


def iter_rows(path: Path):
    with path.open("r", encoding="utf-8") as src:
        for line_no, line in enumerate(src, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("op") not in {"prefill", "write", "expire"}:
                raise ValueError(f"line {line_no}: unsupported op {row.get('op')!r}")
            yield row


def build_compact_lba_map(path: Path) -> tuple[dict[int, int], int]:
    max_size_by_lba: dict[int, int] = {}
    for row in iter_rows(path):
        lba = int(row["lba"])
        max_size_by_lba[lba] = max(max_size_by_lba.get(lba, 1), int(row["size_blocks"]))
    mapping: dict[int, int] = {}
    next_lba = 0
    for lba in sorted(max_size_by_lba):
        mapping[lba] = next_lba
        next_lba += max_size_by_lba[lba]
    return mapping, next_lba


def add_range(unique: set[int], lba: int, size_blocks: int) -> None:
    for block in range(lba, lba + size_blocks):
        unique.add(block)


def adapt_trace(
    jsonl: Path,
    *,
    trace_out: Path,
    group_out: Path,
    property_out: Path,
    log_id: str,
    delete_markers: bool,
    compact_lba: bool = False,
) -> dict[str, Any]:
    trace_out.parent.mkdir(parents=True, exist_ok=True)
    group_out.parent.mkdir(parents=True, exist_ok=True)
    property_out.parent.mkdir(parents=True, exist_ok=True)

    writes = 0
    tombstones = 0
    skipped_expires = 0
    max_lba = 0
    max_size_blocks = 1
    max_ts = 0
    unique_lbas: set[int] = set()
    original_max_lba = 0
    compact_map: dict[int, int] = {}
    compact_span_blocks = 0
    if compact_lba:
        compact_map, compact_span_blocks = build_compact_lba_map(jsonl)

    with trace_out.open("w", encoding="utf-8") as out:
        for row in iter_rows(jsonl):
            ts = int(row["ts"])
            original_lba = int(row["lba"])
            lba = compact_map[original_lba] if compact_lba else original_lba
            size_blocks = max(1, int(row["size_blocks"]))
            max_ts = max(max_ts, ts)
            max_lba = max(max_lba, lba)
            original_max_lba = max(original_max_lba, original_lba)
            max_size_blocks = max(max_size_blocks, size_blocks)
            if row["op"] in {"prefill", "write"}:
                out.write(f"{log_id},W,{lba * BLOCK_SIZE},{size_blocks * BLOCK_SIZE},{ts * 1000}\n")
                writes += 1
                add_range(unique_lbas, lba, size_blocks)
            elif delete_markers:
                out.write(f"{log_id},W,{lba * BLOCK_SIZE},{BLOCK_SIZE},{ts * 1000}\n")
                tombstones += 1
                unique_lbas.add(lba)
            else:
                skipped_expires += 1

    max_lba_bytes = (max_lba + max_size_blocks + 1) * BLOCK_SIZE
    group_out.write_text(str(trace_out.resolve()) + "\n", encoding="utf-8")
    property_out.write_text(f"{log_id} {len(unique_lbas)} {max_lba_bytes}\n", encoding="utf-8")
    return {
        "source_jsonl": str(jsonl),
        "sepbit_trace": str(trace_out),
        "group_file": str(group_out),
        "property_file": str(property_out),
        "log_id": log_id,
        "writes": writes,
        "tombstones": tombstones,
        "skipped_expires": skipped_expires,
        "unique_lbas": len(unique_lbas),
        "max_lba": max_lba,
        "original_max_lba": original_max_lba,
        "max_lba_bytes": max_lba_bytes,
        "max_ts": max_ts,
        "compact_lba": compact_lba,
        "compact_lba_entries": len(compact_map),
        "compact_span_blocks": compact_span_blocks,
        "format": "logId,W,lba_bytes,length_bytes,timestamp_us",
        "tombstone_model": "one 4KiB overwrite at expired object LBA" if delete_markers else "expire events omitted",
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--trace-out", type=Path, required=True)
    parser.add_argument("--group-out", type=Path, required=True)
    parser.add_argument("--property-out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    parser.add_argument("--log-id", default="pqc")
    parser.add_argument("--delete-markers", action="store_true")
    parser.add_argument("--compact-lba", action="store_true")
    args = parser.parse_args()

    summary = adapt_trace(
        args.jsonl,
        trace_out=args.trace_out,
        group_out=args.group_out,
        property_out=args.property_out,
        log_id=args.log_id,
        delete_markers=args.delete_markers,
        compact_lba=args.compact_lba,
    )
    write_json(args.summary_out, summary)
    print(f"wrote summary={args.summary_out}")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
