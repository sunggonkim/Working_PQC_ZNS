#!/usr/bin/env python3
"""Summarize multi-tenant QUASAR pressure and tenant-isolation results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CURRENT = "quasar-dogi-hybrid"
TENANT_ISOLATION = "quasar-adaptive-hybrid"
PHYSICAL_POLICY_LABELS = [
    ("fifo", "FIFO"),
    ("sepbit-style", "SepBIT-style"),
    ("midas-style", "MiDAS-style"),
    ("dogi-history", "DOGI-style"),
    ("quasar", "QUASAR"),
    (CURRENT, "Current hybrid"),
    (TENANT_ISOLATION, "Tenant-isolation mode"),
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def pct_reduction(before: float, after: float) -> float | None:
    if before == 0:
        return None
    return (before - after) / before


def fmt_float(value: float | None, digits: int = 4) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def fmt_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def fmt_int(value: int | float | None) -> str:
    return "N/A" if value is None else f"{int(value):,}"


def by_workload(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(row["workload"], {})[row["policy"]] = row
    return out


def summarize_sim(rows: list[dict[str, Any]]) -> dict[str, Any]:
    workloads: dict[str, Any] = {}
    for workload, policies in sorted(by_workload(rows).items()):
        dogi = policies["dogi-history"]
        current = policies[CURRENT]
        tenant = policies[TENANT_ISOLATION]
        workloads[workload] = {
            "zones": current.get("zones"),
            "dogi": pick(dogi),
            "current": pick(current),
            "tenant_isolation": pick(tenant),
            "tenant_isolation_vs_current": {
                "reset_secret_tenant_impurity_reduction": pct_reduction(
                    float(current.get("reset_secret_tenant_impurity", 0.0)),
                    float(tenant.get("reset_secret_tenant_impurity", 0.0)),
                ),
                "waf_increase": float(tenant.get("waf", 0.0)) - float(current.get("waf", 0.0)),
                "gc_extra_blocks": int(tenant.get("gc_write_blocks", 0)) - int(current.get("gc_write_blocks", 0)),
                "family_extra_count": int(tenant.get("quasar_family_count", 0))
                - int(current.get("quasar_family_count", 0)),
            },
        }
    return workloads


def pick(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "waf": row.get("waf"),
        "gc_write_blocks": row.get("gc_write_blocks"),
        "stale_secret_blocks_remaining": row.get("stale_secret_blocks_remaining"),
        "zone_utilization": row.get("zone_utilization"),
        "tenant_impurity": row.get("tenant_impurity"),
        "reset_secret_tenant_impurity": row.get("reset_secret_tenant_impurity"),
        "reset_secret_epoch_impurity": row.get("reset_secret_epoch_impurity"),
        "reset_secret_impurity_blocks": row.get("reset_secret_impurity_blocks"),
        "quasar_family_count": row.get("quasar_family_count"),
        "quasar_tenant_bin_writes": row.get("quasar_tenant_bin_writes"),
        "quasar_coarse_bin_writes": row.get("quasar_coarse_bin_writes"),
    }


def summarize_physical(report: dict[str, Any]) -> dict[str, Any]:
    rows = report.get("summary", {}).get("by_policy_packing", {})
    by_policy = {}
    for policy, _ in PHYSICAL_POLICY_LABELS:
        item = rows.get(f"{policy}::secret-group", {})
        detailed = next((row for row in report.get("rows", []) if row["policy"] == policy), {})
        sim = detailed.get("sim", {})
        by_policy[policy] = {
            "sim_waf": item.get("sim_waf"),
            "sim_gc_blocks": item.get("sim_gc_blocks"),
            "sim_stale_secret_blocks": item.get("sim_stale_secret_blocks"),
            "physical_reset_commands": item.get("physical_reset_commands"),
            "secret_blocks_waiting_for_physical_reset": item.get("secret_blocks_waiting_for_physical_reset"),
            "max_secret_blocks_waiting_for_physical_reset": item.get("max_secret_blocks_waiting_for_physical_reset"),
            "avg_space_utilization": item.get("avg_space_utilization"),
            "max_live_physical_zones": item.get("max_live_physical_zones"),
            "reset_secret_tenant_impurity": sim.get("reset_secret_tenant_impurity"),
            "reset_secret_epoch_impurity": sim.get("reset_secret_epoch_impurity"),
            "quasar_family_count": sim.get("quasar_family_count"),
        }
    current = by_policy[CURRENT]
    tenant = by_policy[TENANT_ISOLATION]
    return {
        "rows": report.get("summary", {}).get("row_count"),
        "failed_rows": report.get("summary", {}).get("failed_rows"),
        "wall_time_s": report.get("summary", {}).get("wall_time_s"),
        "traces": report.get("traces"),
        "logical_zones": report.get("logical_zones"),
        "append_engine": report.get("append_engine"),
        "helper_chunk_blocks": report.get("helper_chunk_blocks"),
        "by_policy": by_policy,
        "tenant_isolation_vs_current": {
            "reset_secret_tenant_impurity_reduction": pct_reduction(
                float(current.get("reset_secret_tenant_impurity", 0.0)),
                float(tenant.get("reset_secret_tenant_impurity", 0.0)),
            ),
            "waf_increase": float(tenant.get("sim_waf", 0.0)) - float(current.get("sim_waf", 0.0)),
            "gc_extra_blocks": int(tenant.get("sim_gc_blocks", 0)) - int(current.get("sim_gc_blocks", 0)),
            "physical_reset_extra_commands": int(tenant.get("physical_reset_commands", 0))
            - int(current.get("physical_reset_commands", 0)),
            "max_live_physical_zone_extra_count": int(tenant.get("max_live_physical_zones", 0))
            - int(current.get("max_live_physical_zones", 0)),
        },
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Multi-Tenant Pressure Summary",
        "",
        "- Default policy remains `quasar-dogi-hybrid`.",
        "- New optional mode: `tenant-isolation adaptive hybrid`, implemented as tuned `quasar-adaptive-hybrid`.",
        "- This workload is not a DOGI paper workload. It stress-tests multi-tenant PQC secret placement and reset isolation.",
        "",
        "## Simulator",
        "",
        "| Workload | Zones | Policy | WAF | GC Blocks | Stale Secrets | Reset Secret Tenant Impurity | Reset Secret Epoch Impurity | Families |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for workload, item in summary["simulator"].items():
        for label, key in [
            ("DOGI-style", "dogi"),
            ("Current hybrid", "current"),
            ("Tenant-isolation mode", "tenant_isolation"),
        ]:
            row = item[key]
            lines.append(
                "| `{workload}` | {zones} | {label} | {waf} | {gc} | {stale} | {tenant_imp} | {epoch_imp} | {families} |".format(
                    workload=workload,
                    zones=fmt_int(item["zones"]),
                    label=label,
                    waf=fmt_float(row["waf"]),
                    gc=fmt_int(row["gc_write_blocks"]),
                    stale=fmt_int(row["stale_secret_blocks_remaining"]),
                    tenant_imp=fmt_float(row["reset_secret_tenant_impurity"], 3),
                    epoch_imp=fmt_float(row["reset_secret_epoch_impurity"], 3),
                    families=fmt_int(row["quasar_family_count"]),
                )
            )
    lines.extend(["", "## Physical ZNS Representative Replay", ""])
    physical = summary["physical"]
    lines.extend(
        [
            f"- Rows: `{physical['rows']}`, failed rows: `{physical['failed_rows']}`",
            f"- Logical zones: `{physical['logical_zones']}`",
            f"- Wall time: `{physical['wall_time_s']:.3f}` s",
            f"- Append engine: `{physical['append_engine']}`, helper chunk blocks: `{physical['helper_chunk_blocks']}`",
            "",
            "| Policy | WAF | GC Blocks | Stale Secrets | Semantic Resets | Secret Waiting End | Max Secret Waiting | Reset Secret Tenant Impurity | Avg Util | Max Live Phys Zones | Families |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for policy, label in PHYSICAL_POLICY_LABELS:
        row = physical["by_policy"][policy]
        lines.append(
            "| {label} | {waf} | {gc} | {stale} | {resets} | {wait} | {max_wait} | {tenant_imp} | {util} | {zones} | {families} |".format(
                label=label,
                waf=fmt_float(row["sim_waf"]),
                gc=fmt_int(row["sim_gc_blocks"]),
                stale=fmt_int(row["sim_stale_secret_blocks"]),
                resets=fmt_int(row["physical_reset_commands"]),
                wait=fmt_int(row["secret_blocks_waiting_for_physical_reset"]),
                max_wait=fmt_int(row["max_secret_blocks_waiting_for_physical_reset"]),
                tenant_imp=fmt_float(row["reset_secret_tenant_impurity"], 3),
                util=fmt_float(row["avg_space_utilization"], 3),
                zones=fmt_int(row["max_live_physical_zones"]),
                families=fmt_int(row["quasar_family_count"]),
            )
        )
    comparison = physical["tenant_isolation_vs_current"]
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- Keep `quasar-dogi-hybrid` as the default for single-tenant or tenant-agnostic deployments.",
            "- Add a tenant-isolation mode for deployments where secret-bearing zones must not mix tenants.",
            f"- Physical replay tenant impurity reduction: `{fmt_pct(comparison['reset_secret_tenant_impurity_reduction'])}`.",
            f"- Cost in the representative physical replay: WAF +`{fmt_float(comparison['waf_increase'])}`, GC +`{fmt_int(comparison['gc_extra_blocks'])}` blocks, semantic resets +`{fmt_int(comparison['physical_reset_extra_commands'])}`, max live physical zones +`{fmt_int(comparison['max_live_physical_zone_extra_count'])}`.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sim",
        type=Path,
        default=Path("artifacts/results/multitenant-pressure/multitenant-tenantbin-adaptive-op005.json"),
    )
    parser.add_argument(
        "--physical",
        type=Path,
        default=Path(
            "artifacts/results/multitenant-pressure/"
            "packed-physical-zonefs-multitenant-t032-pqc4000-z373-fullbaselines-helper.json"
        ),
    )
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/multitenant-pressure/multitenant-pressure-summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/multitenant-pressure/multitenant-pressure-summary.md"))
    args = parser.parse_args()

    summary = {
        "simulator": summarize_sim(load_json(args.sim)),
        "physical": summarize_physical(load_json(args.physical)),
        "decision": "add-tenant-isolation-mode",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "markdown_out": str(args.markdown_out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
