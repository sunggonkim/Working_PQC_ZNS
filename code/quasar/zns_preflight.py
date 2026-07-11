#!/usr/bin/env python3
"""Read-only preflight for QUASAR real ZNS/FDP replay."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def scan_zoned_devices(sys_block: Path = Path("/sys/block")) -> list[dict]:
    devices = []
    for dev in sorted(sys_block.iterdir()):
        zoned = read_text(dev / "queue/zoned")
        if zoned is None:
            continue
        dev_path = Path("/dev") / dev.name
        devices.append(
            {
                "name": dev.name,
                "path": str(dev_path),
                "zoned": zoned,
                "is_zoned": zoned != "none",
                "path_exists": dev_path.exists(),
                "readable": os.access(dev_path, os.R_OK),
                "writable": os.access(dev_path, os.W_OK),
            }
        )
    return devices


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


def probe_zone_report(device: str, tools: dict[str, str | None]) -> dict:
    if tools.get("blkzone"):
        result = run_command(["blkzone", "report", device])
        result["tool"] = "blkzone"
        return result
    if tools.get("zbd"):
        result = run_command(["zbd", "report", device])
        result["tool"] = "zbd"
        return result
    return {
        "available": False,
        "returncode": None,
        "stdout": "",
        "stderr": "no blkzone or zbd tool found",
        "tool": None,
    }


def device_replay_ready(device: dict, report: dict | None) -> bool:
    return (
        bool(device.get("is_zoned"))
        and bool(device.get("path_exists"))
        and bool(device.get("readable"))
        and bool(device.get("writable"))
        and bool(report)
        and bool(report.get("available"))
        and report.get("returncode") == 0
    )


def preflight(device: str | None = None) -> dict:
    tools = {tool: shutil.which(tool) for tool in ("nvme", "blkzone", "zbd", "xnvme", "spdk_nvme_perf")}
    devices = scan_zoned_devices()
    zoned_devices = [dev for dev in devices if dev["is_zoned"]]
    null_blk_modinfo = run_command(["modinfo", "null_blk"])
    configfs_root = Path("/sys/kernel/config/nullb")
    selected = None
    selected_report = None
    zoned_reports = {}
    if device:
        selected = next((dev for dev in devices if dev["path"] == device or dev["name"] == Path(device).name), None)
        if selected:
            selected_report = probe_zone_report(selected["path"], tools)
    else:
        for dev in zoned_devices:
            zoned_reports[dev["path"]] = probe_zone_report(dev["path"], tools)
    can_run = (
        device_replay_ready(selected, selected_report)
        if selected
        else any(device_replay_ready(dev, zoned_reports.get(dev["path"])) for dev in zoned_devices)
    )
    return {
        "tools": tools,
        "devices": devices,
        "zoned_devices": zoned_devices,
        "selected_device": selected,
        "selected_report": selected_report,
        "zoned_device_reports": zoned_reports,
        "can_run_real_zns_replay": can_run,
        "null_blk": {
            "module_available": null_blk_modinfo["available"] and null_blk_modinfo["returncode"] == 0,
            "configfs_parent_exists": configfs_root.parent.exists(),
            "configfs_root_exists": configfs_root.exists(),
            "current_user_is_root": os.geteuid() == 0,
            "can_create_zoned_nullblk_now": (
                os.geteuid() == 0
                and configfs_root.parent.exists()
                and null_blk_modinfo["available"]
                and null_blk_modinfo["returncode"] == 0
            ),
            "helper": "code/quasar/nullblk_zoned.py",
        },
        "notes": [
            "This preflight is read-only.",
            "A zoned device is not considered replay-ready unless the current user has read/write access and a zone-report command succeeds.",
            "Real replay requires a zoned block device or a configured emulator such as null_blk/NVMeVirt.",
            "If no zoned device is present, use code/quasar/nullblk_zoned.py as root to create a virtual zoned null_blk target.",
        ],
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device")
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/zns-preflight.json"))
    args = parser.parse_args()

    result = preflight(args.device)
    write_json(args.out, result)
    print(f"wrote {args.out}")
    print(json.dumps({"can_run_real_zns_replay": result["can_run_real_zns_replay"], "zoned_devices": len(result["zoned_devices"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
