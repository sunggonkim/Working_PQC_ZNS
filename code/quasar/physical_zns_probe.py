#!/usr/bin/env python3
"""Build a paper-facing readiness report from physical ZNS command outputs.

The script is intentionally read-only. It can either parse saved `nvme`
outputs captured with root privileges, or use ordinary user-space discovery
such as `lsblk` and `findmnt` when available.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def load_text(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def lspci_zns_hint(text: str | None) -> dict[str, Any]:
    if not text:
        return {"zn540_seen": False, "matching_lines": []}
    lines = [line for line in text.splitlines() if "ZN540" in line.upper() or "WESTERN DIGITAL" in line.upper()]
    return {"zn540_seen": any("ZN540" in line.upper() for line in lines), "matching_lines": lines}


def run_json(args: list[str]) -> dict[str, Any] | None:
    if not shutil.which(args[0]):
        return None
    proc = subprocess.run(args, check=False, text=True, capture_output=True)
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def run_text(args: list[str]) -> str | None:
    if not shutil.which(args[0]):
        return None
    proc = subprocess.run(args, check=False, text=True, capture_output=True)
    if proc.returncode != 0:
        return None
    return proc.stdout


def lba_size_from_id_ns(id_ns: dict[str, Any] | None) -> int | None:
    if not id_ns:
        return None
    flbas = int(id_ns.get("flbas", 0)) & 0xF
    lbafs = id_ns.get("lbafs", [])
    if flbas >= len(lbafs):
        return None
    ds = lbafs[flbas].get("ds")
    if ds is None:
        return None
    return 1 << int(ds)


def parse_report_text(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    out: dict[str, Any] = {"raw_excerpt": "\n".join(text.splitlines()[:8])}
    match = re.search(r"nr_zones:\s*(\d+)", text)
    if match:
        out["nr_zones"] = int(match.group(1))
    zone = re.search(
        r"SLBA:\s*(0x[0-9a-fA-F]+|\d+)\s+WP:\s*(0x[0-9a-fA-F]+|\d+)\s+"
        r"Cap:\s*(0x[0-9a-fA-F]+|\d+)\s+State:\s*(0x[0-9a-fA-F]+|\d+)\s+"
        r"Type:\s*(0x[0-9a-fA-F]+|\d+)",
        text,
    )
    if zone:
        keys = ["slba", "wp", "cap", "state", "type"]
        out["first_zone"] = {key: int(value, 0) for key, value in zip(keys, zone.groups())}
    return out


def find_key_recursive(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = find_key_recursive(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_key_recursive(child, key)
            if found is not None:
                return found
    return None


def parse_report_json(report: dict[str, Any] | None) -> dict[str, Any]:
    if not report:
        return {}
    out: dict[str, Any] = {}
    nr_zones = find_key_recursive(report, "nr_zones")
    if nr_zones is not None:
        out["nr_zones"] = int(nr_zones)
    zones = find_key_recursive(report, "zones")
    if isinstance(zones, list) and zones:
        first = zones[0]
        if isinstance(first, dict):
            out["first_zone"] = first
    return out


def flatten_lsblk_devices(node: dict[str, Any]) -> list[dict[str, Any]]:
    out = [node]
    for child in node.get("children", []) or []:
        out.extend(flatten_lsblk_devices(child))
    return out


def lsblk_device(lsblk: dict[str, Any] | None, device: str) -> dict[str, Any] | None:
    if not lsblk:
        return None
    for root in lsblk.get("blockdevices", []):
        for item in flatten_lsblk_devices(root):
            if item.get("path") == device or f"/dev/{item.get('name')}" == device:
                return item
    return None


def findmnt_record(target: str) -> dict[str, Any] | None:
    data = run_json(["findmnt", "-J", "-T", target])
    if not data:
        return None
    filesystems = data.get("filesystems", [])
    if not filesystems:
        return None
    return filesystems[0]


def id_ns_summary(id_ns: dict[str, Any] | None) -> dict[str, Any]:
    if not id_ns:
        return {}
    lba_size = lba_size_from_id_ns(id_ns)
    summary: dict[str, Any] = {
        "nsze_lba": id_ns.get("nsze"),
        "ncap_lba": id_ns.get("ncap"),
        "nuse_lba": id_ns.get("nuse"),
        "flbas": id_ns.get("flbas"),
        "lba_size_bytes": lba_size,
        "eui64": id_ns.get("eui64"),
        "nguid": id_ns.get("nguid"),
    }
    if lba_size:
        for name in ("nsze", "ncap", "nuse"):
            if id_ns.get(name) is not None:
                summary[f"{name}_bytes"] = int(id_ns[name]) * lba_size
    return summary


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    id_ns = load_json(args.id_ns_json)
    report_json = parse_report_json(load_json(args.report_zones_json))
    report_text = parse_report_text(load_text(args.report_zones_text))
    lspci_hint = lspci_zns_hint(load_text(args.lspci_text))
    zns_report = report_json | report_text
    lsblk = load_json(args.lsblk_json) or run_json(
        ["lsblk", "--json", "-o", "NAME,PATH,TYPE,SIZE,MODEL,ZONED,MOUNTPOINT"]
    )
    block_device = lsblk_device(lsblk, args.device)
    mount = findmnt_record(args.mount) if args.mount else None
    id_summary = id_ns_summary(id_ns)
    model = (block_device or {}).get("model") or id_ns.get("mn") if id_ns else (block_device or {}).get("model")
    is_zns = bool(zns_report.get("nr_zones", 0) > 0)
    is_zonefs = bool(mount and mount.get("fstype") == "zonefs")
    ready = bool(id_summary.get("nsze_lba") and is_zns)
    paper_alignment = {
        "dogi_uses_wd_zn540": True,
        "matches_dogi_hardware_family": "ZN540" in str(model or "").upper() or lspci_hint["zn540_seen"],
        "dogi_paper_target": "Western Digital ZN540 2TB ZNS SSD via ZenFS",
    }
    return {
        "device": args.device,
        "mount": args.mount,
        "status": "physical-zns-detected" if ready else "incomplete",
        "read_only_probe": True,
        "id_ns": id_summary,
        "zns_report": zns_report,
        "lsblk_device": block_device,
        "mount_record": mount,
        "lspci_hint": lspci_hint,
        "detected": {
            "id_ns_seen": bool(id_summary),
            "zns_report_seen": is_zns,
            "zonefs_mount_seen": is_zonefs,
            "model": model,
        },
        "paper_alignment": paper_alignment,
        "next": [
            "Run a tiny zonefs append smoke test without resetting the device.",
            "Only run full replay after deciding whether zone reset is allowed on this physical SSD.",
            "Use the same DOGI-shaped traces for simulator, null_blk, and physical replay.",
        ],
    }


def markdown(report: dict[str, Any]) -> str:
    id_ns = report["id_ns"]
    zns = report["zns_report"]
    mount = report.get("mount_record") or {}
    lines = [
        "# Physical ZNS Readiness",
        "",
        f"- Status: `{report['status']}`",
        f"- Device: `{report['device']}`",
        f"- Mount: `{report.get('mount')}`",
        f"- Model: `{report['detected'].get('model')}`",
        f"- DOGI hardware-family match: `{report['paper_alignment']['matches_dogi_hardware_family']}`",
        "",
        "| Item | Value |",
        "| --- | ---: |",
        f"| LBA size | {id_ns.get('lba_size_bytes', 'n/a')} B |",
        f"| nsze | {id_ns.get('nsze_lba', 'n/a')} LBA |",
        f"| ncap | {id_ns.get('ncap_lba', 'n/a')} LBA |",
        f"| nuse | {id_ns.get('nuse_lba', 'n/a')} LBA |",
        f"| reported zones | {zns.get('nr_zones', 'n/a')} |",
        f"| mount fstype | {mount.get('fstype', 'n/a')} |",
        f"| mount options | {mount.get('options', 'n/a')} |",
        "",
        "## Next",
        "",
    ]
    lines.extend(f"- {item}" for item in report["next"])
    return "\n".join(lines) + "\n"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="/dev/nvme0n1")
    parser.add_argument("--mount", default="/mnt/zn540")
    parser.add_argument("--id-ns-json", type=Path)
    parser.add_argument("--report-zones-json", type=Path)
    parser.add_argument("--report-zones-text", type=Path)
    parser.add_argument("--lsblk-json", type=Path)
    parser.add_argument("--lspci-text", type=Path)
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/physical-zns-readiness.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/physical-zns-readiness.md"))
    args = parser.parse_args()

    report = build_report(args)
    write_json(args.out, report)
    write_text(args.markdown_out, markdown(report))
    print(json.dumps({"status": report["status"], "device": report["device"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
