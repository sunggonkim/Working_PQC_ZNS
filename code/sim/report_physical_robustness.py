#!/usr/bin/env python3
"""Summarize physical ZNS bad-hint/straggler robustness replays."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def fmt_float(value: float | None, digits: int = 4) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def fmt_int(value: int | float | None) -> str:
    return "N/A" if value is None else f"{int(value):,}"


def row(report: dict[str, Any], policy: str, packing: str) -> dict[str, Any]:
    return report.get("summary", {}).get("by_policy_packing", {}).get(f"{policy}::{packing}", {})


def summarize_row(item: dict[str, Any]) -> dict[str, Any]:
    physical_waf = item.get("physical_waf")
    if physical_waf is None and item.get("user_blocks"):
        physical_waf = (int(item.get("user_blocks", 0)) + int(item.get("gc_blocks", 0))) / max(
            1, int(item.get("user_blocks", 0))
        )
    return {
        "sim_waf": item.get("sim_waf"),
        "physical_waf": physical_waf,
        "sim_gc_blocks": item.get("sim_gc_blocks"),
        "sim_stale_secret_blocks": item.get("sim_stale_secret_blocks"),
        "failed_rows": item.get("failed_rows"),
        "physical_reset_commands": item.get("physical_reset_commands"),
        "secret_waiting_end": item.get("secret_blocks_waiting_for_physical_reset"),
        "max_secret_waiting": item.get("max_secret_blocks_waiting_for_physical_reset"),
        "max_live_physical_zones": item.get("max_live_physical_zones"),
        "max_active_pack_keys": item.get("max_active_pack_keys"),
        "avg_space_utilization": item.get("avg_space_utilization"),
        "physical_bytes_written": item.get("physical_bytes_written"),
        "residual_migration_commands": item.get("residual_migration_commands"),
        "residual_migrated_blocks": item.get("residual_migrated_blocks"),
    }


def summarize(args: argparse.Namespace) -> dict[str, Any]:
    clean = load_json(args.clean)
    missing = load_json(args.missing)
    wrong = load_json(args.wrong)
    straggler_exact = load_json(args.straggler_exact)
    straggler_nobatch = load_json(args.straggler_nobatch)
    straggler_epochbin = load_json(args.straggler_epochbin)
    straggler_residual = load_json(args.straggler_residual)
    zns = load_json(args.zns_id_ns)

    return {
        "scope": "actual ZNS bad-hint and straggler replay on YCSB-A p4000",
        "trace": "artifacts/traces/fast-ycsb-pressure/ycsb-a-pqc4000.jsonl",
        "device_limits": {
            "mar": zns.get("mar"),
            "mor": zns.get("mor"),
            "numzrwa": zns.get("numzrwa"),
        },
        "clean": {
            "dogi": summarize_row(row(clean, "dogi-history", "secret-group")),
            "hybrid": summarize_row(row(clean, "quasar-dogi-hybrid", "secret-group")),
            "failed_rows": clean.get("summary", {}).get("failed_rows"),
            "rows": clean.get("summary", {}).get("row_count"),
        },
        "missing_hint_5pct": {
            "hybrid": summarize_row(row(missing, "quasar-dogi-hybrid", "secret-group")),
            "failed_rows": missing.get("summary", {}).get("failed_rows"),
            "rows": missing.get("summary", {}).get("row_count"),
        },
        "wrong_epoch_5pct": {
            "hybrid": summarize_row(row(wrong, "quasar-dogi-hybrid", "secret-group")),
            "failed_rows": wrong.get("summary", {}).get("failed_rows"),
            "rows": wrong.get("summary", {}).get("row_count"),
        },
        "straggler_5pct_exact_secret_group": {
            "hybrid": summarize_row(row(straggler_exact, "quasar-dogi-hybrid", "secret-group")),
            "failed_rows": straggler_exact.get("summary", {}).get("failed_rows"),
            "rows": straggler_exact.get("summary", {}).get("row_count"),
        },
        "straggler_5pct_exact_secret_group_nobatch": {
            "hybrid": summarize_row(row(straggler_nobatch, "quasar-dogi-hybrid", "secret-group")),
            "failed_rows": straggler_nobatch.get("summary", {}).get("failed_rows"),
            "rows": straggler_nobatch.get("summary", {}).get("row_count"),
        },
        "straggler_5pct_epoch_bin_4": {
            "hybrid": summarize_row(row(straggler_epochbin, "quasar-dogi-hybrid", "epoch-bin-4")),
            "failed_rows": straggler_epochbin.get("summary", {}).get("failed_rows"),
            "rows": straggler_epochbin.get("summary", {}).get("row_count"),
        },
        "straggler_5pct_epoch_bin_5_residual_12288": {
            "hybrid": summarize_row(row(straggler_residual, "quasar-dogi-hybrid", "epoch-bin-5")),
            "failed_rows": straggler_residual.get("summary", {}).get("failed_rows"),
            "rows": straggler_residual.get("summary", {}).get("row_count"),
        },
        "decision": "add-open-zone-aware-residual-fallback",
        "decision_reason": (
            "Exact secret-group packing is best for clean hints, missing hints, and wrong epochs, "
            "but delayed expiry/stragglers can exceed the WD ZN540 open-zone budget. "
            "Epoch-bin-4 keeps max live physical zones at the device limit and completes, "
            "but leaves stale-secret exposure. Epoch-bin-5 plus residual migration completes on the actual ZNS device, "
            "keeps max live physical zones within mor/mar, and reduces final secret waiting to zero at explicit GC-copy cost."
        ),
    }


def markdown(data: dict[str, Any]) -> str:
    rows = [
        (
            "DOGI clean",
            data["clean"]["dogi"],
            data["clean"]["failed_rows"],
        ),
        (
            "Hybrid clean",
            data["clean"]["hybrid"],
            data["clean"]["failed_rows"],
        ),
        (
            "Hybrid missing hints 5%",
            data["missing_hint_5pct"]["hybrid"],
            data["missing_hint_5pct"]["failed_rows"],
        ),
        (
            "Hybrid wrong epoch 5%",
            data["wrong_epoch_5pct"]["hybrid"],
            data["wrong_epoch_5pct"]["failed_rows"],
        ),
        (
            "Hybrid straggler 5%, secret-group",
            data["straggler_5pct_exact_secret_group"]["hybrid"],
            data["straggler_5pct_exact_secret_group"]["failed_rows"],
        ),
        (
            "Hybrid straggler 5%, secret-group no-batch",
            data["straggler_5pct_exact_secret_group_nobatch"]["hybrid"],
            data["straggler_5pct_exact_secret_group_nobatch"]["failed_rows"],
        ),
        (
            "Hybrid straggler 5%, epoch-bin-4",
            data["straggler_5pct_epoch_bin_4"]["hybrid"],
            data["straggler_5pct_epoch_bin_4"]["failed_rows"],
        ),
        (
            "Hybrid straggler 5%, epoch-bin-5 + residual",
            data["straggler_5pct_epoch_bin_5_residual_12288"]["hybrid"],
            data["straggler_5pct_epoch_bin_5_residual_12288"]["failed_rows"],
        ),
    ]

    lines = [
        "# Physical ZNS Hint Robustness",
        "",
        f"- Scope: {data['scope']}",
        f"- Trace: `{data['trace']}`",
        f"- Device ZNS limits: `mar={data['device_limits']['mar']}`, `mor={data['device_limits']['mor']}`",
        "",
        "| Case | Sim WAF | Physical WAF | GC Blocks | Sim Stale Secrets | Secret Waiting End | Physical Resets | Residual Migrations | Residual Blocks | Max Live Phys Zones | Max Pack Keys | Avg Util | Failed Rows |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, item, failed_rows in rows:
        lines.append(
            "| {label} | {waf} | {physical_waf} | {gc} | {stale} | {waiting} | {resets} | {migrations} | {migration_blocks} | {max_z} | {keys} | {util} | {failed} |".format(
                label=label,
                waf=fmt_float(item["sim_waf"]),
                physical_waf=fmt_float(item["physical_waf"]),
                gc=fmt_int(item["sim_gc_blocks"]),
                stale=fmt_int(item["sim_stale_secret_blocks"]),
                waiting=fmt_int(item["secret_waiting_end"]),
                resets=fmt_int(item["physical_reset_commands"]),
                migrations=fmt_int(item["residual_migration_commands"]),
                migration_blocks=fmt_int(item["residual_migrated_blocks"]),
                max_z=fmt_int(item["max_live_physical_zones"]),
                keys=fmt_int(item["max_active_pack_keys"]),
                util=fmt_float(item["avg_space_utilization"], 3),
                failed=fmt_int(failed_rows),
            )
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Clean hybrid removes stale secrets and issues semantic zone resets on the real ZNS device.",
            "- Missing hints degrade security exposure: some secret data falls back to non-semantic placement.",
            "- Wrong epoch hints preserve stale-secret removal in this trace but increase reset activity.",
            "- Stragglers are the hardest case. Exact secret-group packing can exceed the device open-zone budget and trigger zonefs error handling.",
            "- `epoch-bin-4` is the first open-zone-aware fallback: it completes within the device limit, but it keeps stale secrets waiting. This is a deployment mode, not the default.",
            "- `epoch-bin-5 + residual migration` is the improved fallback: it copies bounded live residue, resets stale-secret zones, and ends with zero secret waiting on the actual ZNS device.",
            "",
            f"Decision: `{data['decision']}`.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    base = Path("artifacts/results/physical-robustness-ycsb-a-pqc4000")
    parser.add_argument("--clean", type=Path, default=base / "clean.json")
    parser.add_argument("--missing", type=Path, default=base / "missing005.json")
    parser.add_argument("--wrong", type=Path, default=base / "wrong005.json")
    parser.add_argument("--straggler-exact", type=Path, default=base / "straggler005.json")
    parser.add_argument("--straggler-nobatch", type=Path, default=base / "straggler005-nobatch.json")
    parser.add_argument("--straggler-epochbin", type=Path, default=base / "straggler005-epochbin4.json")
    parser.add_argument(
        "--straggler-residual",
        type=Path,
        default=base / "straggler005-residual-th12288-epochbin5-physical.json",
    )
    parser.add_argument("--zns-id-ns", type=Path, default=Path("artifacts/results/physical-zns-zns-id-ns-latest.json"))
    parser.add_argument("--out", type=Path, default=base / "summary.json")
    parser.add_argument("--markdown-out", type=Path, default=base / "summary.md")
    args = parser.parse_args()

    data = summarize(args)
    args.out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown(data), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "markdown_out": str(args.markdown_out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
