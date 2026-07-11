#!/usr/bin/env python3
"""Prepare a zoned null_blk target for QUASAR replay experiments.

The helper is intentionally explicit. `plan` and `preflight` are read-only.
`create` and `destroy` require root because they write under configfs.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIGFS_ROOT = Path("/sys/kernel/config/nullb")


@dataclass(frozen=True)
class NullBlkConfig:
    name: str
    size_mib: int
    blocksize: int
    zone_size_mib: int
    zone_capacity_mib: int
    zone_max_open: int
    zone_max_active: int
    memory_backed: bool


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


def config_params(config: NullBlkConfig) -> dict[str, str]:
    return {
        "size": str(config.size_mib),
        "blocksize": str(config.blocksize),
        "memory_backed": "1" if config.memory_backed else "0",
        "zoned": "1",
        "zone_size": str(config.zone_size_mib),
        "zone_capacity": str(config.zone_capacity_mib),
        "zone_max_open": str(config.zone_max_open),
        "zone_max_active": str(config.zone_max_active),
        "zone_nr_conv": "0",
    }


def command_plan(config: NullBlkConfig, configfs_root: Path = DEFAULT_CONFIGFS_ROOT) -> list[str]:
    dev_dir = configfs_root / config.name
    lines = [
        "sudo modprobe null_blk configfs=1",
        f"sudo mkdir -p {dev_dir}",
    ]
    for key, value in config_params(config).items():
        lines.append(f"echo {value} | sudo tee {dev_dir / key} >/dev/null")
    lines.append(f"echo 1 | sudo tee {dev_dir / 'power'} >/dev/null")
    lines.append(f"cat /sys/block/{config.name}/queue/zoned")
    lines.append(f"blkzone report /dev/{config.name} | head")
    return lines


def destroy_plan(name: str, configfs_root: Path = DEFAULT_CONFIGFS_ROOT) -> list[str]:
    dev_dir = configfs_root / name
    return [
        f"echo 0 | sudo tee {dev_dir / 'power'} >/dev/null",
        f"sudo rmdir {dev_dir}",
    ]


def preflight(configfs_root: Path = DEFAULT_CONFIGFS_ROOT) -> dict:
    modinfo = run_command(["modinfo", "null_blk"])
    return {
        "euid": os.geteuid(),
        "is_root": os.geteuid() == 0,
        "configfs_root": str(configfs_root),
        "configfs_root_exists": configfs_root.exists(),
        "configfs_parent_exists": configfs_root.parent.exists(),
        "null_blk_module_available": modinfo["available"] and modinfo["returncode"] == 0,
        "null_blk_configfs_available": configfs_root.exists(),
        "can_create_without_sudo": os.geteuid() == 0 and configfs_root.parent.exists(),
        "modinfo": modinfo,
        "notes": [
            "Creating a null_blk device requires root and writes to configfs.",
            "This helper never invokes sudo itself; run it as root or run the printed plan manually.",
            "The target is virtual null_blk, not a physical SSD, but it exposes zoned block-device semantics.",
        ],
    }


def write_attr(path: Path, value: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"missing null_blk configfs attribute: {path}")
    path.write_text(value, encoding="utf-8")


def create(config: NullBlkConfig, configfs_root: Path = DEFAULT_CONFIGFS_ROOT, *, force: bool = False) -> dict:
    if os.geteuid() != 0:
        raise PermissionError("create requires root because it writes to configfs")
    dev_dir = configfs_root / config.name
    if dev_dir.exists() and not force:
        raise FileExistsError(f"{dev_dir} already exists; use --force to overwrite attributes")
    dev_dir.mkdir(parents=True, exist_ok=True)
    for key, value in config_params(config).items():
        write_attr(dev_dir / key, value)
    write_attr(dev_dir / "power", "1")
    device = Path("/dev") / config.name
    return {
        "created": True,
        "configfs_dir": str(dev_dir),
        "device": str(device),
        "zoned_queue": str(Path("/sys/block") / config.name / "queue/zoned"),
    }


def destroy(name: str, configfs_root: Path = DEFAULT_CONFIGFS_ROOT) -> dict:
    if os.geteuid() != 0:
        raise PermissionError("destroy requires root because it writes to configfs")
    dev_dir = configfs_root / name
    if not dev_dir.exists():
        return {"destroyed": False, "reason": "missing", "configfs_dir": str(dev_dir)}
    power = dev_dir / "power"
    if power.exists():
        power.write_text("0", encoding="utf-8")
    dev_dir.rmdir()
    return {"destroyed": True, "configfs_dir": str(dev_dir)}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_config(args: argparse.Namespace) -> NullBlkConfig:
    return NullBlkConfig(
        name=args.name,
        size_mib=args.size_mib,
        blocksize=args.blocksize,
        zone_size_mib=args.zone_size_mib,
        zone_capacity_mib=args.zone_capacity_mib,
        zone_max_open=args.zone_max_open,
        zone_max_active=args.zone_max_active,
        memory_backed=not args.no_memory_backed,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=["plan", "preflight", "create", "destroy"], default="plan")
    parser.add_argument("--name", default="nullb0")
    parser.add_argument("--size-mib", type=int, default=4096)
    parser.add_argument("--blocksize", type=int, default=4096)
    parser.add_argument("--zone-size-mib", type=int, default=64)
    parser.add_argument("--zone-capacity-mib", type=int, default=64)
    parser.add_argument("--zone-max-open", type=int, default=128)
    parser.add_argument("--zone-max-active", type=int, default=0)
    parser.add_argument("--no-memory-backed", action="store_true")
    parser.add_argument("--configfs-root", type=Path, default=DEFAULT_CONFIGFS_ROOT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    config = build_config(args)
    if args.action == "preflight":
        payload = preflight(args.configfs_root)
    elif args.action == "plan":
        payload = {
            "create_commands": command_plan(config, args.configfs_root),
            "destroy_commands": destroy_plan(config.name, args.configfs_root),
            "config": config.__dict__,
        }
    elif args.action == "create":
        payload = create(config, args.configfs_root, force=args.force)
    else:
        payload = destroy(config.name, args.configfs_root)

    if args.out:
        write_json(args.out, payload)
        print(f"wrote {args.out}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
