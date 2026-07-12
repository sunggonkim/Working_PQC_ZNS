#!/usr/bin/env python3
"""Summarize local ZNS security/sanitize capability evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def fmt_bool(value: bool) -> str:
    return "yes" if value else "no"


def summarize(id_ctrl: dict[str, Any], sanitize_log: dict[str, Any], id_ns: dict[str, Any]) -> dict[str, Any]:
    sanicap = int(id_ctrl.get("sanicap", 0))
    # NVMe Identify Controller SANICAP lower bits advertise sanitize operation support.
    supported = {
        "crypto_erase": bool(sanicap & (1 << 0)),
        "block_erase": bool(sanicap & (1 << 1)),
        "overwrite": bool(sanicap & (1 << 2)),
    }
    log = next(iter(sanitize_log.values()), {}) if sanitize_log else {}
    status = str(log.get("sstat", {}).get("status", ""))
    cdw10_info = log.get("cdw10_info")
    sanitize_completed = "completed successfully" in status.lower()
    crypto_erase_executed = sanitize_completed and cdw10_info == 4
    sanitize_execution_validated = bool(crypto_erase_executed and supported["crypto_erase"])
    if sanitize_execution_validated:
        claim_boundary = (
            "QUASAR proves reset eligibility and stale-secret exposure reduction, and this device's "
            "NVMe crypto-erase sanitize command path has been executed and validated as a destructive "
            "device/namespace-scoped operation. Zone reset alone is still not a physical erase proof, "
            "and sanitize must not be treated as a per-zone or per-epoch command on a shared namespace. "
            "A strong physical erase deployment requires a dedicated namespace/media pool, per-cohort "
            "encryption-key isolation, or future per-zone erase semantics whose blast radius matches "
            "the cohort being destroyed."
        )
    else:
        claim_boundary = (
            "QUASAR currently proves reset eligibility and stale-secret exposure reduction. "
            "A strong physical erase claim requires a device path whose erase blast radius matches "
            "the target cohort, such as a dedicated namespace/media pool, per-cohort encryption-key "
            "isolation, or future per-zone erase semantics."
        )
    return {
        "device_model": str(id_ctrl.get("mn", "")).strip(),
        "firmware": str(id_ctrl.get("fr", "")).strip(),
        "sanicap_raw": sanicap,
        "sanicap_hex": f"0x{sanicap:08x}",
        "sanitize_supported": any(supported.values()),
        "sanitize_operations_supported": supported,
        "sanitize_log_status": status,
        "sanitize_progress": log.get("sprog"),
        "sanitize_cdw10_info": cdw10_info,
        "sanitize_completed": sanitize_completed,
        "crypto_erase_executed": crypto_erase_executed,
        "sanitize_execution_validated": sanitize_execution_validated,
        "sanitize_time_crypto_erase": log.get("time_crypto_erase"),
        "sanitize_time_block_erase": log.get("time_block_erase"),
        "namespace_size_lba": id_ns.get("nsze"),
        "namespace_capacity_lba": id_ns.get("ncap"),
        "namespace_use_lba": id_ns.get("nuse"),
        "claim_boundary": claim_boundary,
    }


def markdown(summary: dict[str, Any]) -> str:
    ops = summary["sanitize_operations_supported"]
    lines = [
        "# Physical ZNS Security Capability Summary",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Device model | `{summary['device_model']}` |",
        f"| Firmware | `{summary['firmware']}` |",
        f"| SANICAP raw | `{summary['sanicap_raw']}` / `{summary['sanicap_hex']}` |",
        f"| Sanitize supported | `{fmt_bool(summary['sanitize_supported'])}` |",
        f"| Crypto erase sanitize op bit | `{fmt_bool(ops['crypto_erase'])}` |",
        f"| Block erase sanitize op bit | `{fmt_bool(ops['block_erase'])}` |",
        f"| Overwrite sanitize op bit | `{fmt_bool(ops['overwrite'])}` |",
        f"| Sanitize log status | `{summary['sanitize_log_status']}` |",
        f"| Sanitize progress | `{summary['sanitize_progress']}` |",
        f"| Sanitize cdw10 info | `{summary['sanitize_cdw10_info']}` |",
        f"| Crypto erase command executed | `{fmt_bool(summary['crypto_erase_executed'])}` |",
        f"| Sanitize execution validated | `{fmt_bool(summary['sanitize_execution_validated'])}` |",
        f"| Namespace capacity LBA | `{summary['namespace_capacity_lba']}` |",
        f"| Namespace use LBA | `{summary['namespace_use_lba']}` |",
        "",
        "## Claim Boundary",
        "",
        summary["claim_boundary"],
        "",
        "Paper wording should therefore say:",
        "",
        "```text",
        (
            "QUASAR aligns expired PQC secret cohorts with immediate zone-reset eligibility. "
            "On the evaluated ZNS SSD, the NVMe crypto-erase sanitize command path completed "
            "successfully as a destructive device/namespace-scoped operation. This validates the "
            "command path, but it is not a per-zone physical erase primitive for shared namespaces."
        ),
        "```",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id-ctrl", type=Path, default=Path("artifacts/results/physical-zns-id-ctrl.json"))
    parser.add_argument("--sanitize-log", type=Path, default=Path("artifacts/results/physical-zns-sanitize-log.json"))
    parser.add_argument("--id-ns", type=Path, default=Path("artifacts/results/physical-zns-id-ns-latest.json"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/physical-zns-security-capability.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/physical-zns-security-capability.md"))
    args = parser.parse_args()

    summary = summarize(load_json(args.id_ctrl), load_json(args.sanitize_log), load_json(args.id_ns))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "markdown_out": str(args.markdown_out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
