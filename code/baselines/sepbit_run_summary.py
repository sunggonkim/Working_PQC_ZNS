#!/usr/bin/env python3
"""Parse SepBIT trace_replay simulator logs into JSON artifacts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SUMMARY_RE = re.compile(
    r"SUMMARY:\s+"
    r"Requests\s+:\s+(?P<requests>[0-9]+)\s+"
    r"nGC\s+:\s+(?P<ngc>[0-9]+)\s+"
    r"LBAs\s+:\s+(?P<lbas>[0-9]+)\s+"
    r"bytes_to_System:\s+(?P<system>[0-9]+)\s+"
    r"bytes_to_Storage:\s+(?P<storage>[0-9]+)\s+"
    r"\*\* WA \*\*\s+:\s+(?P<wa>[0-9.]+)\s+"
    r"nBlocks:\s+:\s+(?P<blocks>[0-9]+)\s+"
    r"nInvalidBlks\s+:\s+(?P<invalid>[0-9]+)\s+"
    r"garb prop\s+:\s+(?P<garbage>[0-9.]+)\s+"
    r"removed avg gp:\s+(?P<removed>[0-9.NaNnan-]+)\s+"
    r"Run time\(s\)\s+:\s+(?P<runtime>[0-9.]+)",
    re.MULTILINE,
)
SEGMENT_WA_RE = re.compile(r"(?P<log_id>\S+): nBlocks: (?P<blocks>[0-9]+), nInvalidBlocks: (?P<invalid>[0-9]+) .* segment WA = (?P<wa>[0-9.]+)")


def load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def load_returncode(path: Path | None) -> int | None:
    if path is None or not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8", errors="replace").strip())
    except ValueError:
        return None


def parse_float(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def parse_sepbit_log(
    log: Path,
    *,
    returncode: int | None,
    method: str,
    selection: str,
    adapter_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = log.read_text(encoding="utf-8", errors="replace")
    match = SUMMARY_RE.search(text)
    segment_match = SEGMENT_WA_RE.search(text)
    completed = returncode == 0 and match is not None
    summary = {
        "requests": int(match.group("requests")) if match else 0,
        "ngc": int(match.group("ngc")) if match else 0,
        "lbas": int(match.group("lbas")) if match else 0,
        "bytes_to_system": int(match.group("system")) if match else 0,
        "bytes_to_storage": int(match.group("storage")) if match else 0,
        "wa": float(match.group("wa")) if match else None,
        "nblocks": int(match.group("blocks")) if match else 0,
        "invalid_blocks": int(match.group("invalid")) if match else 0,
        "garbage_proportion": float(match.group("garbage")) if match else None,
        "removed_avg_gp": parse_float(match.group("removed")) if match else None,
        "runtime_seconds": float(match.group("runtime")) if match else None,
    }
    return {
        "log": str(log),
        "returncode": returncode,
        "completed": completed,
        "method": method,
        "selection": selection,
        "summary": summary,
        "segment_summary": {
            "log_id": segment_match.group("log_id") if segment_match else None,
            "nblocks": int(segment_match.group("blocks")) if segment_match else None,
            "invalid_blocks": int(segment_match.group("invalid")) if segment_match else None,
            "segment_wa": float(segment_match.group("wa")) if segment_match else None,
        },
        "adapter_summary": adapter_summary,
        "notes": [
            "This is the external SepBIT trace_replay simulator, not the compact SepBIT-style simulator baseline.",
            "The adapter uses SepBIT's Ali CSV input format and models PQC expiry as a one-block tombstone overwrite.",
        ],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--returncode-file", type=Path)
    parser.add_argument("--adapter-summary", type=Path)
    parser.add_argument("--method", required=True)
    parser.add_argument("--selection", default="Greedy")
    args = parser.parse_args()

    summary = parse_sepbit_log(
        args.log,
        returncode=load_returncode(args.returncode_file),
        method=args.method,
        selection=args.selection,
        adapter_summary=load_optional_json(args.adapter_summary),
    )
    write_json(args.out, summary)
    print(f"wrote {args.out}")
    print(json.dumps({"completed": summary["completed"], "wa": summary["summary"]["wa"]}, sort_keys=True))
    return 0 if summary["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
