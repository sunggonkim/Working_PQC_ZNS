#!/usr/bin/env python3
"""Adapt QUASAR rich JSONL traces to the public DOGI prototype trace shape.

DOGI's prototype consumes write-like records:

    <timestamp> 1 <lba_4k> <length_bytes>

PQC expiry is a delete/epoch-close event rather than a normal overwrite, so this
adapter can emit one-block tombstone writes at expiry time. The approximation is
explicitly summarized in a JSON sidecar for paper reproducibility.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


BLOCK_SIZE = 4096


def iter_trace(path: Path):
    with path.open("r", encoding="utf-8") as src:
        for line_no, line in enumerate(src, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            validate_row(row, line_no)
            yield row


def validate_row(row: dict, line_no: int) -> None:
    op = row.get("op")
    if op not in {"prefill", "write", "expire"}:
        raise ValueError(f"line {line_no}: unsupported op {op!r}")
    for field in ("ts", "lba", "size_blocks"):
        if field not in row:
            raise ValueError(f"line {line_no}: missing {field}")
        if int(row[field]) < 0:
            raise ValueError(f"line {line_no}: negative {field}")
    if op == "write" and "object_id" not in row:
        raise ValueError(f"line {line_no}: write event missing object_id")


def logical_size_gb(max_lba: int, max_size_blocks: int) -> int:
    bytes_needed = (max_lba + max_size_blocks + 1) * BLOCK_SIZE
    return max(1, math.ceil(bytes_needed / (1024**3)))


def build_compact_lba_map(jsonl: Path) -> tuple[dict[int, int], int]:
    max_size_by_lba: dict[int, int] = {}
    for row in iter_trace(jsonl):
        lba = int(row["lba"])
        max_size_by_lba[lba] = max(max_size_by_lba.get(lba, 1), int(row["size_blocks"]))
    mapping: dict[int, int] = {}
    next_lba = 0
    for lba in sorted(max_size_by_lba):
        mapping[lba] = next_lba
        next_lba += max_size_by_lba[lba]
    return mapping, next_lba


def adapt_trace(jsonl: Path, dogi_trace: Path, *, delete_markers: bool, compact_lba: bool = False) -> dict:
    dogi_trace.parent.mkdir(parents=True, exist_ok=True)
    writes = 0
    tombstones = 0
    skipped_expires = 0
    max_lba = 0
    max_size_blocks = 1
    max_ts = 0
    user_write_bytes = 0
    original_max_lba = 0
    compact_map: dict[int, int] = {}
    compact_span_blocks = 0
    if compact_lba:
        compact_map, compact_span_blocks = build_compact_lba_map(jsonl)

    with dogi_trace.open("w", encoding="utf-8") as out:
        for row in iter_trace(jsonl):
            ts = int(row["ts"])
            original_lba = int(row["lba"])
            lba = compact_map[original_lba] if compact_lba else original_lba
            size_blocks = int(row["size_blocks"])
            max_ts = max(max_ts, ts)
            max_lba = max(max_lba, lba)
            original_max_lba = max(original_max_lba, original_lba)
            max_size_blocks = max(max_size_blocks, size_blocks)
            if row["op"] in {"prefill", "write"}:
                length = size_blocks * BLOCK_SIZE
                out.write(f"{ts} 1 {lba} {length}\n")
                writes += 1
                user_write_bytes += length
            elif delete_markers:
                out.write(f"{ts} 1 {lba} {BLOCK_SIZE}\n")
                tombstones += 1
            else:
                skipped_expires += 1

    size_gb = logical_size_gb(max_lba, max_size_blocks)
    return {
        "source_jsonl": str(jsonl),
        "dogi_trace": str(dogi_trace),
        "dogi_lines": writes + tombstones,
        "dogi_writes": writes,
        "dogi_tombstones": tombstones,
        "skipped_expires": skipped_expires,
        "user_write_bytes": user_write_bytes,
        "max_lba": max_lba,
        "original_max_lba": original_max_lba,
        "max_ts": max_ts,
        "logical_size_gb": size_gb,
        "compact_lba": compact_lba,
        "compact_lba_entries": len(compact_map),
        "compact_span_blocks": compact_span_blocks,
        "tombstone_model": "one 4KiB overwrite at expired object LBA" if delete_markers else "expire events omitted",
        "global_cc_snippet": (
            f'char wk_name[128] = "{dogi_trace.resolve()}";\n'
            f"int LogicalSizeGb = {size_gb};\n"
            'const char kZnsDevicePath[] = "/dev/<zns-device>";\n'
            'const char kZbdDeviceName[] = "<zns-device-name>";'
        ),
    }


def write_summary(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--dogi-trace", type=Path, required=True)
    parser.add_argument("--delete-markers", action="store_true")
    parser.add_argument("--compact-lba", action="store_true")
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()

    summary = adapt_trace(args.jsonl, args.dogi_trace, delete_markers=args.delete_markers, compact_lba=args.compact_lba)
    if args.summary_out:
        write_summary(args.summary_out, summary)
        print(f"wrote summary={args.summary_out}")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
