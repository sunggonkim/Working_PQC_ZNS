#!/usr/bin/env python3
"""Parse a DOGI prototype run log into a reproducible JSON artifact."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


TRACE_RE = re.compile(r"Trace Path:\s*(?P<trace>\S+)")
PLACEMENT_RE = re.compile(r"PlacementName:\s*(?P<placement>\S+)")
PLACEMENT_ALGO_RE = re.compile(r"Placement algorithm:\s*(?P<placement_algo>\S+)")
SELECTION_RE = re.compile(r"Selection algorithm:\s*(?P<selection>\S+)")
USER_GC_RE = re.compile(r"UserWrite:\s*(?P<user>[0-9.]+),\s*GCWrite:\s*(?P<gc>[0-9.]+)")
FREE_RE = re.compile(r"ZenFS file system created\. Free space:\s*(?P<free_mb>[0-9.]+)\s*MB")


def parse_dogi_log(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    trace_match = TRACE_RE.search(text)
    placement_match = PLACEMENT_RE.search(text)
    placement_algo_match = PLACEMENT_ALGO_RE.search(text)
    selection_match = SELECTION_RE.search(text)
    user_gc_match = USER_GC_RE.search(text)
    free_match = FREE_RE.search(text)
    completed = user_gc_match is not None
    user_write_gib = float(user_gc_match.group("user")) if user_gc_match else 0.0
    gc_write_gib = float(user_gc_match.group("gc")) if user_gc_match else 0.0
    waf = (user_write_gib + gc_write_gib) / user_write_gib if user_write_gib > 0 else None
    return {
        "log": str(path),
        "completed": completed,
        "trace_path": trace_match.group("trace") if trace_match else None,
        "placement_name": placement_match.group("placement") if placement_match else None,
        "placement_algorithm": placement_algo_match.group("placement_algo") if placement_algo_match else None,
        "selection_algorithm": selection_match.group("selection") if selection_match else None,
        "zenfs_free_mb": float(free_match.group("free_mb")) if free_match else None,
        "user_write_gib": user_write_gib,
        "gc_write_gib": gc_write_gib,
        "waf": waf,
        "saw_zenfs_mount": "ZenFS file system created" in text,
        "saw_dogi_select": "Selection algorithm: DogiSelect" in text,
        "saw_mlp_status": "[MLP]" in text,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    summary = parse_dogi_log(args.log)
    write_json(args.out, summary)
    print(f"wrote {args.out}")
    print(json.dumps({"completed": summary["completed"], "waf": summary["waf"]}, sort_keys=True))
    return 0 if summary["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
