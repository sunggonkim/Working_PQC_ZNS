#!/usr/bin/env python3
"""Parse a MiDAS prototype run log into a reproducible JSON artifact."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


STORAGE_RE = re.compile(r"Storage Capacity:\s*(?P<gib>[0-9.]+)GiB\s*\(LBA NUMBER:\s*(?P<lbas>[0-9]+)\)")
PROGRESS_RE = re.compile(r"\[progress:\s*(?P<progress>[0-9.]+GB)\]")
PROGRESS_WAF_RE = re.compile(r"TOTAL WAF:\s*(?P<total>[0-9.]+),\s*TMP WAF:\s*(?P<tmp>[0-9.]+)")
RUNTIME_RE = re.compile(r"runtime:\s*(?P<seconds>[0-9.]+)\s*sec")
TOTAL_WAF_RE = re.compile(r"^Total WAF:\s*(?P<waf>[0-9.]+)\s*$", re.MULTILINE)
TRAFFIC_RE = re.compile(r"^(?P<name>Total Read Traffic|Total Write Traffic)\s*:\s*(?P<value>[0-9]+)\s*$", re.MULTILINE)
COUNTER_RE = re.compile(r"^(?P<name>TRIM|DATAR|DATAW|GCDR|GCDW)\s+(?P<value>[0-9]+)\s*$", re.MULTILINE)


def load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def load_returncode(path: Path | None) -> int | None:
    if path is None or not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def parse_midas_log(
    log: Path,
    *,
    trace: Path | None = None,
    returncode: int | None = None,
    build_gigaunit: str | None = None,
    pps: int | None = None,
    adapter_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = log.read_text(encoding="utf-8", errors="replace")
    storage_match = STORAGE_RE.search(text)
    runtime_match = RUNTIME_RE.search(text)
    total_waf_match = TOTAL_WAF_RE.search(text)
    progress_matches = []
    for progress_match in PROGRESS_RE.finditer(text):
        waf_match = PROGRESS_WAF_RE.search(text, progress_match.end())
        progress_matches.append(
            {
                "progress": progress_match.group("progress"),
                "total_waf": float(waf_match.group("total")) if waf_match else None,
                "tmp_waf": float(waf_match.group("tmp")) if waf_match else None,
            }
        )
    traffic = {m.group("name").lower().replace(" ", "_"): int(m.group("value")) for m in TRAFFIC_RE.finditer(text)}
    counters = {m.group("name").lower(): int(m.group("value")) for m in COUNTER_RE.finditer(text)}
    dataw = counters.get("dataw", 0)
    gcdw = counters.get("gcdw", 0)
    recomputed_waf = (dataw + gcdw) / dataw if dataw > 0 else None
    completed = returncode == 0 and total_waf_match is not None and dataw > 0
    return {
        "log": str(log),
        "trace": str(trace) if trace else None,
        "returncode": returncode,
        "completed": completed,
        "build": {
            "gigaunit": build_gigaunit,
            "pps": pps,
        },
        "storage_capacity_gib": float(storage_match.group("gib")) if storage_match else None,
        "lba_number": int(storage_match.group("lbas")) if storage_match else None,
        "runtime_seconds": float(runtime_match.group("seconds")) if runtime_match else None,
        "total_waf": float(total_waf_match.group("waf")) if total_waf_match else None,
        "recomputed_waf_from_dataw_gcdw": recomputed_waf,
        "traffic": traffic,
        "counters": counters,
        "progress_reports": progress_matches,
        "adapter_summary": adapter_summary,
        "notes": [
            "This is the external MiDAS memory-backed prototype, not the compact MiDAS-style simulator baseline.",
            "MiDAS counts DATAW/GCDW in its own internal page/traffic units; compare exact numbers carefully against QUASAR simulator units.",
        ],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--returncode-file", type=Path)
    parser.add_argument("--adapter-summary", type=Path)
    parser.add_argument("--build-gigaunit", default=None)
    parser.add_argument("--pps", type=int, default=None)
    args = parser.parse_args()

    summary = parse_midas_log(
        args.log,
        trace=args.trace,
        returncode=load_returncode(args.returncode_file),
        build_gigaunit=args.build_gigaunit,
        pps=args.pps,
        adapter_summary=load_optional_json(args.adapter_summary),
    )
    write_json(args.out, summary)
    print(f"wrote {args.out}")
    print(json.dumps({"completed": summary["completed"], "total_waf": summary["total_waf"]}, sort_keys=True))
    return 0 if summary["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
