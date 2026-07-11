#!/usr/bin/env python3
"""Tiny non-resetting zonefs append smoke test.

The default mode is dry-run. With `--execute`, the script appends a small
aligned buffer to one sequential zonefs file and records before/after state.
It never issues zone reset or sanitize commands.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


def findmnt_record(target: Path) -> dict[str, Any]:
    proc = subprocess.run(["findmnt", "-J", "-T", str(target)], check=False, text=True, capture_output=True)
    if proc.returncode != 0:
        return {"available": False, "stderr": proc.stderr.strip()}
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"available": False, "stderr": "findmnt JSON parse failed"}
    filesystems = data.get("filesystems", [])
    if not filesystems:
        return {"available": False, "stderr": "no filesystem record"}
    record = filesystems[0]
    record["available"] = True
    return record


def is_read_only(mount_record: dict[str, Any]) -> bool:
    options = str(mount_record.get("options", ""))
    return "ro" in {item.strip() for item in options.split(",")}


def numeric_key(path: Path) -> tuple[int, str]:
    try:
        return (int(path.name), path.name)
    except ValueError:
        return (10**18, path.name)


def choose_zone_file_from_report(mount: Path, report_path: Path | None) -> Path | None:
    if report_path is None or not report_path.exists():
        return None
    try:
        with report_path.open("r", encoding="utf-8") as src:
            report = json.load(src)
    except (OSError, json.JSONDecodeError):
        return None
    zone_list = report.get("zone_list", [])
    appendable_states = {"EMPTY", "OPEN", "IMP_OPEN", "EXP_OPEN"}
    for index, zone in enumerate(zone_list):
        if str(zone.get("state", "")).upper() not in appendable_states:
            continue
        candidate = mount / "seq" / str(index)
        if candidate.is_file():
            return candidate
    return None


def choose_zone_file(mount: Path, max_existing_bytes: int = 0, report_path: Path | None = None) -> Path | None:
    reported = choose_zone_file_from_report(mount, report_path)
    if reported is not None:
        return reported
    roots = [mount / "seq", mount]
    for root in roots:
        if not root.is_dir():
            continue
        candidates = sorted([path for path in root.iterdir() if path.is_file()], key=numeric_key)
        for path in candidates:
            try:
                if path.stat().st_size <= max_existing_bytes:
                    return path
            except OSError:
                continue
    return None


def append_bytes(target: Path, byte_count: int) -> dict[str, Any]:
    before = target.stat().st_size
    data = bytes(byte_count)
    started = time.perf_counter_ns()
    fd = os.open(str(target), os.O_WRONLY | os.O_APPEND | getattr(os, "O_SYNC", 0))
    written = 0
    try:
        while written < byte_count:
            written += os.write(fd, data[written:])
        os.fsync(fd)
    finally:
        os.close(fd)
    elapsed = time.perf_counter_ns() - started
    after = target.stat().st_size
    return {
        "method": "python-append",
        "target": str(target),
        "bytes_requested": byte_count,
        "bytes_written": written,
        "before_size": before,
        "after_size": after,
        "append_latency_ns": elapsed,
        "write_succeeded": written == byte_count and after >= before + written,
    }


def append_bytes_dd_direct(target: Path, byte_count: int) -> dict[str, Any]:
    before = target.stat().st_size
    started = time.perf_counter_ns()
    proc = subprocess.run(
        [
            "dd",
            "if=/dev/zero",
            f"of={target}",
            "bs=4096",
            f"count={byte_count // 4096}",
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
        "method": "dd-direct",
        "target": str(target),
        "bytes_requested": byte_count,
        "bytes_written": byte_count if proc.returncode == 0 else 0,
        "before_size": before,
        "after_size": after,
        "append_latency_ns": elapsed,
        "dd_returncode": proc.returncode,
        "dd_stdout": proc.stdout[:1000],
        "dd_stderr": proc.stderr[:1000],
        "write_succeeded": proc.returncode == 0 and after >= before + byte_count,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    mount = args.mount
    mount_record = findmnt_record(mount)
    target = args.target or choose_zone_file(mount, args.max_existing_bytes, args.report_zones_json)
    report: dict[str, Any] = {
        "mount": str(mount),
        "execute": args.execute,
        "method": args.method,
        "bytes": args.bytes,
        "mount_record": mount_record,
        "target": str(target) if target else None,
        "issues": [],
        "write_succeeded": False,
        "reset_issued": False,
    }
    if not target:
        report["status"] = "blocked-no-zone-file"
        report["issues"].append("No writable-looking zonefs file candidate found.")
        return report
    if mount_record.get("available") and is_read_only(mount_record):
        report["status"] = "blocked-read-only-mount"
        report["issues"].append("The selected mount is read-only according to findmnt.")
        return report
    if not args.execute:
        report["status"] = "dry-run"
        report["issues"].append("Pass --execute to perform the tiny append.")
        return report
    try:
        if args.method == "dd-direct":
            result = append_bytes_dd_direct(target, args.bytes)
        else:
            result = append_bytes(target, args.bytes)
    except OSError as exc:
        report["status"] = "append-failed"
        report["issues"].append(str(exc))
        return report
    report.update(result)
    report["status"] = "append-succeeded" if result["write_succeeded"] else "append-incomplete"
    return report


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Zonefs Append Smoke",
        "",
        f"- Status: `{report['status']}`",
        f"- Mount: `{report['mount']}`",
        f"- Target: `{report.get('target')}`",
        f"- Executed: `{report['execute']}`",
        f"- Method: `{report.get('method')}`",
        f"- Reset issued: `{report['reset_issued']}`",
        f"- Write succeeded: `{report['write_succeeded']}`",
        "",
        "| Item | Value |",
        "| --- | ---: |",
        f"| bytes requested | {report.get('bytes_requested', report.get('bytes'))} |",
        f"| bytes written | {report.get('bytes_written', 0)} |",
        f"| before size | {report.get('before_size', 'n/a')} |",
        f"| after size | {report.get('after_size', 'n/a')} |",
        f"| append latency ns | {report.get('append_latency_ns', 'n/a')} |",
        "",
    ]
    issues = report.get("issues", [])
    if issues:
        lines.extend(["## Issues", ""])
        lines.extend(f"- {issue}" for issue in issues)
        lines.append("")
    return "\n".join(lines)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mount", type=Path, default=Path("/mnt/zn540"))
    parser.add_argument("--target", type=Path)
    parser.add_argument("--bytes", type=int, default=4096)
    parser.add_argument("--max-existing-bytes", type=int, default=0)
    parser.add_argument("--report-zones-json", type=Path)
    parser.add_argument("--method", choices=["python-append", "dd-direct"], default="python-append")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/physical-zonefs-append.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/physical-zonefs-append.md"))
    args = parser.parse_args()

    if args.bytes <= 0 or args.bytes % 4096 != 0:
        raise SystemExit("--bytes must be a positive multiple of 4096")
    report = build_report(args)
    write_json(args.out, report)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "write_succeeded": report["write_succeeded"]}, sort_keys=True))
    return 0 if report["status"] in {"dry-run", "append-succeeded", "blocked-read-only-mount"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
