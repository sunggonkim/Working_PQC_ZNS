#!/usr/bin/env python3
"""Preflight checker for running the external DOGI prototype.

The checker verifies that a cloned DOGI repository matches the trace-adapter
assumptions and records which host dependencies are missing before attempting a
full prototype run. It is deliberately non-destructive: it does not edit DOGI
files, reset ZNS devices, or invoke sudo.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


REQUIRED_FILES = [
    "prototype/app/global.cc",
    "prototype/app/main.cc",
    "prototype/CMakeLists.txt",
    "prototype/app/CMakeLists.txt",
]

HOST_TOOLS = ["cmake", "make", "python3", "nvme", "zbd"]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def grep(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.MULTILINE) is not None


def check_trace(trace: Path) -> dict:
    if not trace.exists():
        return {"exists": False}
    lines = 0
    valid = 0
    max_lba = 0
    max_len = 0
    with trace.open("r", encoding="utf-8") as src:
        for line in src:
            if not line.strip():
                continue
            lines += 1
            parts = line.split()
            if len(parts) == 4 and parts[1] == "1":
                valid += 1
                max_lba = max(max_lba, int(parts[2]))
                max_len = max(max_len, int(parts[3]))
    return {
        "exists": True,
        "lines": lines,
        "valid_dogi_lines": valid,
        "all_lines_usable": lines == valid,
        "max_lba": max_lba,
        "max_length_bytes": max_len,
    }


def run_command(args: list[str]) -> dict:
    try:
        proc = subprocess.run(args, check=False, text=True, capture_output=True)
    except FileNotFoundError:
        return {"available": False, "returncode": None, "stdout": "", "stderr": "not found"}
    return {
        "available": True,
        "returncode": proc.returncode,
        "stdout": proc.stdout[:4000],
        "stderr": proc.stderr[:4000],
    }


def check_repo(repo: Path) -> dict:
    files = {rel: (repo / rel).exists() for rel in REQUIRED_FILES}
    result = {"exists": repo.exists(), "required_files": files}
    if not all(files.values()):
        result["parser_matches_adapter"] = False
        return result
    global_cc = read_text(repo / "prototype/app/global.cc")
    main_cc = read_text(repo / "prototype/app/main.cc")
    result.update(
        {
            "has_wk_name": grep(r"wk_name\s*\[", global_cc),
            "has_logical_size_gb": grep(r"LogicalSizeGb", global_cc),
            "has_zns_device_path": grep(r"kZnsDevicePath", global_cc),
            "parser_filters_type_1": 'result[1] != "1"' in main_cc,
            "parser_uses_lba_4k": "result[2]" in main_cc and "*4096" in main_cc,
            "parser_uses_length_bytes": "result[3]" in main_cc and "atoi" in main_cc,
        }
    )
    result["parser_matches_adapter"] = all(
        result[key]
        for key in (
            "has_wk_name",
            "has_logical_size_gb",
            "has_zns_device_path",
            "parser_filters_type_1",
            "parser_uses_lba_4k",
            "parser_uses_length_bytes",
        )
    )
    return result


def preflight(repo: Path, trace: Path | None, device: str | None = None) -> dict:
    repo_check = check_repo(repo)
    tools = {tool: shutil.which(tool) for tool in HOST_TOOLS}
    nvme_list = run_command(["nvme", "list"]) if tools.get("nvme") else {"available": False}
    zbd_list = run_command(["zbd", "report", device]) if tools.get("zbd") and device else {"available": False}
    trace_check = check_trace(trace) if trace else None
    can_configure = repo_check.get("parser_matches_adapter", False) and bool(tools.get("cmake")) and bool(tools.get("make"))
    trace_ready = trace_check is not None and trace_check.get("all_lines_usable", False)
    device_ready = bool(device) and Path(device).exists()
    can_run_full = can_configure and trace_ready and device_ready and bool(tools.get("zbd")) and bool(tools.get("nvme"))
    return {
        "dogi_repo": str(repo),
        "device": device,
        "repo": repo_check,
        "trace": trace_check,
        "tools": tools,
        "nvme_list": nvme_list,
        "zbd_probe": zbd_list,
        "can_configure_build": can_configure,
        "can_run_full_prototype": can_run_full,
        "notes": [
            "This preflight does not edit DOGI global.cc or reset devices.",
            "Full DOGI execution still requires configured RocksDB/ZenFS and a real or emulated ZNS target.",
            "can_run_full_prototype is false unless --device points to an existing target.",
        ],
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dogi-repo", type=Path, default=Path("artifacts/external/DOGI"))
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--device")
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()

    result = preflight(args.dogi_repo, args.trace, args.device)
    if args.summary_out:
        write_json(args.summary_out, result)
        print(f"wrote preflight={args.summary_out}")
    print(json.dumps({k: result[k] for k in ("can_configure_build", "can_run_full_prototype")}, sort_keys=True))
    return 0 if result["repo"].get("parser_matches_adapter", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
