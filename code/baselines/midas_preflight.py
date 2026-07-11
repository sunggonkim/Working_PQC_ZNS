#!/usr/bin/env python3
"""Read-only preflight for the external MiDAS artifact.

MiDAS is a real SSD/FlashDriver prototype. A full run can require a large trace
and large DRAM budget, so this preflight records what is ready locally without
building, downloading traces, or changing the artifact tree.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


REQUIRED_FILES = [
    "README.md",
    "Makefile",
    "algorithm/MiDAS/midas.c",
    "algorithm/MiDAS/model.c",
    "algorithm/MiDAS/gc.c",
    "algorithm/MiDAS/hot.c",
    "algorithm/MiDAS/Makefile",
]


def run_command(args: list[str], cwd: Path | None = None) -> dict:
    try:
        proc = subprocess.run(args, cwd=cwd, check=False, text=True, capture_output=True)
    except FileNotFoundError:
        return {"available": False, "returncode": None, "stdout": "", "stderr": "not found"}
    return {
        "available": True,
        "returncode": proc.returncode,
        "stdout": proc.stdout[:4000],
        "stderr": proc.stderr[:4000],
    }


def trace_summary(trace: Path | None, sample_lines: int) -> dict:
    if trace is None:
        return {"provided": False}
    result = {
        "provided": True,
        "path": str(trace),
        "exists": trace.exists(),
        "sampled_lines": 0,
        "valid_lines": 0,
        "write_lines": 0,
        "trim_lines": 0,
        "max_lba": 0,
        "max_request_size": 0,
        "all_sampled_lines_usable": False,
    }
    if not trace.exists():
        return result
    with trace.open("r", encoding="utf-8", errors="replace") as src:
        for line in src:
            if result["sampled_lines"] >= sample_lines:
                break
            if not line.strip():
                continue
            result["sampled_lines"] += 1
            parts = line.split()
            if len(parts) < 4:
                continue
            try:
                _ts = float(parts[0])
                req_type = int(parts[1])
                lba = int(parts[2])
                req_size = int(float(parts[3]))
            except ValueError:
                continue
            if req_type == 1:
                result["write_lines"] += 1
            if req_type == 3:
                result["trim_lines"] += 1
            result["max_lba"] = max(result["max_lba"], lba)
            result["max_request_size"] = max(result["max_request_size"], req_size)
            result["valid_lines"] += 1
    result["all_sampled_lines_usable"] = result["sampled_lines"] > 0 and result["sampled_lines"] == result["valid_lines"]
    return result


def preflight(repo: Path, trace: Path | None, sample_lines: int) -> dict:
    required = {rel: (repo / rel).exists() for rel in REQUIRED_FILES}
    readme = repo / "README.md"
    readme_text = readme.read_text(encoding="utf-8", errors="replace") if readme.exists() else ""
    make_dry_run = run_command(["make", "-n", "GIGAUNIT=8L", "_PPS=128"], cwd=repo) if repo.exists() else {
        "available": False,
        "returncode": None,
        "stdout": "",
        "stderr": "repo missing",
    }
    git_head = run_command(["git", "rev-parse", "--short", "HEAD"], cwd=repo) if (repo / ".git").exists() else {
        "available": False,
        "returncode": None,
        "stdout": "",
        "stderr": "not a git repo",
    }
    trace_info = trace_summary(trace, sample_lines)
    return {
        "repo": str(repo),
        "exists": repo.exists(),
        "git_head": git_head,
        "required_files": required,
        "tools": {
            "make": shutil.which("make"),
            "gcc": shutil.which("gcc"),
            "g++": shutil.which("g++"),
            "wget": shutil.which("wget"),
        },
        "readme_mentions": {
            "hardware_flashdriver": "FlashDriver" in readme_text,
            "requires_large_dram": "DRAM" in readme_text and "140GB" in readme_text,
            "test_fio_small": "test-fio-small" in readme_text,
            "midas_simulation_link": "MiDAS-Simulation" in readme_text,
        },
        "make_dry_run": make_dry_run,
        "trace": trace_info,
        "can_attempt_local_memory_run": (
            repo.exists()
            and all(required.values())
            and bool(shutil.which("make"))
            and bool(shutil.which("g++"))
            and trace_info.get("all_sampled_lines_usable", False)
        ),
        "notes": [
            "This preflight is read-only and does not compile or run MiDAS.",
            "The MiDAS README states that full paper-scale traces are too large to upload; the public path uses a smaller FIO test trace.",
            "A full exact MiDAS run should use the artifact's own trace format and memory-backed prototype, not the compact simulator baseline.",
        ],
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("artifacts/external/MiDAS"))
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--sample-lines", type=int, default=1000)
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/midas-preflight.json"))
    args = parser.parse_args()

    result = preflight(args.repo, args.trace, args.sample_lines)
    write_json(args.out, result)
    print(f"wrote {args.out}")
    print(
        json.dumps(
            {
                "exists": result["exists"],
                "can_attempt_local_memory_run": result["can_attempt_local_memory_run"],
                "required_files_ok": all(result["required_files"].values()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
