#!/usr/bin/env python3
"""Summarize residual-migration fallback sweeps for straggler workloads."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


DRYRUN_RE = re.compile(r"(?P<workload>.+)-th(?P<threshold>\d+)-dryrun\.json$")
BUDGET_DRYRUN_RE = re.compile(r"(?P<workload>.+)-th(?P<threshold>\d+)-budget(?P<budget>\d+)(?P<suffix>k?)-dryrun\.json$")
BUDGET_PHYSICAL_RE = re.compile(
    r"(?P<workload>.+)-th(?P<threshold>\d+)-budget(?P<budget>\d+)(?P<suffix>k?)-(?P<packing>epoch-bin-\d+)-physical\.json$"
)
PHYSICAL_RE = re.compile(r"(?P<workload>.+)-th(?P<threshold>\d+)-(?P<packing>epoch-bin-\d+)-physical\.json$")

CONTROLLER_PROFILES = [
    {
        "profile": "low_overhead",
        "description": "minimize copy/WAF cost; accept bounded stale-secret waiting",
        "max_physical_waf": 1.15,
        "max_secret_waiting": None,
        "zero_wait": False,
    },
    {
        "profile": "balanced",
        "description": "reduce waiting while keeping physical WAF below a deployable cap",
        "max_physical_waf": 1.50,
        "max_secret_waiting": 50_000,
        "zero_wait": False,
    },
    {
        "profile": "strict_zero_wait",
        "description": "force zero final stale-secret waiting if any in-budget candidate exists",
        "max_physical_waf": None,
        "max_secret_waiting": 0,
        "zero_wait": True,
    },
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def fmt_float(value: float | None, digits: int = 4) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def fmt_int(value: int | float | None) -> str:
    return "N/A" if value is None else f"{int(value):,}"


def get_int(row: dict[str, Any], key: str, default: int = 0) -> int:
    value = row.get(key)
    return default if value is None else int(value)


def get_float(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key)
    return default if value is None else float(value)


def row_metrics(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "sim_waf": item.get("sim_waf"),
        "physical_waf": item.get("physical_waf"),
        "sim_gc_blocks": item.get("sim_gc_blocks"),
        "physical_gc_blocks": item.get("gc_blocks"),
        "sim_stale_secret_blocks": item.get("sim_stale_secret_blocks"),
        "secret_waiting_end": item.get("secret_blocks_waiting_for_physical_reset"),
        "max_secret_waiting": item.get("max_secret_blocks_waiting_for_physical_reset"),
        "physical_reset_commands": item.get("physical_reset_commands"),
        "residual_migration_commands": item.get("residual_migration_commands"),
        "residual_migrated_blocks": item.get("residual_migrated_blocks"),
        "residual_migration_budget_skips": item.get("residual_migration_budget_skips"),
        "max_live_physical_zones": item.get("max_live_physical_zones"),
        "max_active_pack_keys": item.get("max_active_pack_keys"),
        "failed_rows": item.get("failed_rows"),
        "physical_bytes_written": item.get("physical_bytes_written"),
    }


def iter_policy_rows(report: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows = report.get("summary", {}).get("by_policy_packing", {})
    return [(key, item) for key, item in sorted(rows.items()) if key.startswith("quasar-dogi-hybrid::")]


def collect_dryruns(base: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(base.glob("*-th*-dryrun.json")):
        match = DRYRUN_RE.match(path.name)
        if not match:
            continue
        report = load_json(path)
        workload = match.group("workload")
        threshold = int(match.group("threshold"))
        for key, item in iter_policy_rows(report):
            packing = key.split("::", 1)[1]
            rows.append(
                {
                    "workload": workload,
                    "threshold": threshold,
                    "packing": packing,
                    "artifact": str(path),
                    **row_metrics(item),
                }
            )
    return rows


def collect_budget_dryruns(base: Path) -> list[dict[str, Any]]:
    rows_by_key: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    for path in sorted(base.glob("*-th*-budget*dryrun.json")):
        match = BUDGET_DRYRUN_RE.match(path.name)
        if not match:
            continue
        report = load_json(path)
        workload = match.group("workload")
        threshold = int(match.group("threshold"))
        budget = int(match.group("budget"))
        if match.group("suffix") == "k":
            budget *= 1000
        for key, item in iter_policy_rows(report):
            packing = key.split("::", 1)[1]
            row_key = (workload, threshold, budget, packing)
            rows_by_key[row_key] = {
                "workload": workload,
                "threshold": threshold,
                "copy_budget": budget,
                "packing": packing,
                "artifact": str(path),
                **row_metrics(item),
            }
    return [rows_by_key[key] for key in sorted(rows_by_key)]


def collect_budget_physical(base: Path) -> list[dict[str, Any]]:
    rows_by_key: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    for path in sorted(base.glob("*-th*-budget*physical.json")):
        match = BUDGET_PHYSICAL_RE.match(path.name)
        if not match:
            continue
        report = load_json(path)
        workload = match.group("workload")
        threshold = int(match.group("threshold"))
        budget = int(match.group("budget"))
        if match.group("suffix") == "k":
            budget *= 1000
        packing_from_name = match.group("packing")
        for key, item in iter_policy_rows(report):
            packing = key.split("::", 1)[1] or packing_from_name
            row_key = (workload, threshold, budget, packing)
            rows_by_key[row_key] = {
                "workload": workload,
                "threshold": threshold,
                "copy_budget": budget,
                "packing": packing,
                "artifact": str(path),
                "execute": report.get("execute"),
                "evidence": "actual-zns",
                **row_metrics(item),
            }
    return [rows_by_key[key] for key in sorted(rows_by_key)]


def collect_physical(base: Path, extra: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    paths = list(sorted(base.glob("*-th*-physical.json"))) + extra
    for path in paths:
        if not path.exists():
            continue
        if BUDGET_PHYSICAL_RE.match(path.name):
            continue
        report = load_json(path)
        profile = ""
        if "controller-low-overhead-physical" in path.name:
            profile = "low_overhead"
        elif "controller-balanced-physical" in path.name:
            profile = "balanced"
        elif "controller-strict-physical" in path.name:
            profile = "strict_zero_wait"
        match = PHYSICAL_RE.match(path.name)
        if match:
            workload = match.group("workload")
            threshold = int(match.group("threshold"))
            packing_from_name = match.group("packing")
        else:
            workload = Path(report.get("traces", [path.stem])[0]).stem
            threshold = int(report.get("physical_residual_threshold", 0))
            packing_from_name = ""
        for key, item in iter_policy_rows(report):
            packing = key.split("::", 1)[1] or packing_from_name
            rows.append(
                {
                    "workload": workload,
                    "profile": profile,
                    "threshold": threshold,
                    "packing": packing,
                    "artifact": str(path),
                    "execute": report.get("execute"),
                    **row_metrics(item),
                }
            )
    return rows


def best_candidates(rows: list[dict[str, Any]], mor: int | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    workloads = sorted({row["workload"] for row in rows})
    for workload in workloads:
        candidates = [
            row
            for row in rows
            if row["workload"] == workload
            and row.get("failed_rows") == 0
            and (mor is None or int(row.get("max_live_physical_zones") or 10**9) <= mor)
        ]
        zero_wait = [row for row in candidates if int(row.get("secret_waiting_end") or 0) == 0]
        out[workload] = {
            "best_zero_wait": sorted(
                zero_wait,
                key=lambda row: (
                    float(row.get("physical_waf") or 10**9),
                    int(row.get("residual_migrated_blocks") or 0),
                ),
            )[:5],
            "best_low_waf": sorted(
                candidates,
                key=lambda row: (
                    float(row.get("physical_waf") or 10**9),
                    int(row.get("secret_waiting_end") or 10**9),
                ),
            )[:5],
        }
    return out


def candidate_mode(row: dict[str, Any]) -> str:
    if get_int(row, "secret_waiting_end") == 0:
        return "strict-zero-wait"
    if get_int(row, "copy_budget") > 0:
        return "bounded-copy-budget"
    if get_int(row, "residual_migrated_blocks") > 0:
        return "threshold-only-residual"
    return "no-residual-copy"


def valid_controller_candidates(rows: list[dict[str, Any]], mor: int | None) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if get_int(row, "failed_rows") != 0:
            continue
        if mor is not None and get_int(row, "max_live_physical_zones", 10**9) > mor:
            continue
        out.append(row)
    return out


def choose_controller_candidate(rows: list[dict[str, Any]], profile: dict[str, Any], mor: int | None) -> dict[str, Any]:
    candidates = valid_controller_candidates(rows, mor)
    relaxed: list[str] = []
    if profile["zero_wait"]:
        candidates = [row for row in candidates if get_int(row, "secret_waiting_end") == 0]
        if not candidates:
            return {"selected": None, "relaxed_constraints": ["no-zero-wait-candidate"]}
    max_waf = profile.get("max_physical_waf")
    if max_waf is not None:
        under_waf = [row for row in candidates if get_float(row, "physical_waf", 10**9) <= float(max_waf)]
        if under_waf:
            candidates = under_waf
        else:
            relaxed.append("physical-waf-cap")
    max_waiting = profile.get("max_secret_waiting")
    if max_waiting is not None:
        under_waiting = [row for row in candidates if get_int(row, "secret_waiting_end", 10**18) <= int(max_waiting)]
        if under_waiting:
            candidates = under_waiting
        elif not profile["zero_wait"]:
            relaxed.append("secret-waiting-target")
    if not candidates:
        return {"selected": None, "relaxed_constraints": relaxed or ["no-valid-candidate"]}

    if profile["zero_wait"]:
        selected = sorted(
            candidates,
            key=lambda row: (
                get_float(row, "physical_waf", 10**9),
                get_int(row, "residual_migrated_blocks"),
            ),
        )[0]
    elif max_waiting is not None and "secret-waiting-target" not in relaxed:
        selected = sorted(
            candidates,
            key=lambda row: (
                get_int(row, "secret_waiting_end", 10**18),
                get_float(row, "physical_waf", 10**9),
            ),
        )[0]
    else:
        selected = sorted(
            candidates,
            key=lambda row: (
                get_float(row, "physical_waf", 10**9),
                get_int(row, "secret_waiting_end", 10**18),
            ),
        )[0]
    selected_copy_budget = selected.get("copy_budget")
    if selected_copy_budget is None:
        if profile["zero_wait"]:
            recommended_copy_budget = None
        else:
            recommended_copy_budget = get_int(selected, "residual_migrated_blocks")
    else:
        recommended_copy_budget = int(selected_copy_budget)
    return {
        "selected": {
            "workload": selected.get("workload"),
            "packing": selected.get("packing"),
            "threshold": selected.get("threshold"),
            "copy_budget": selected_copy_budget,
            "recommended_copy_budget": recommended_copy_budget,
            "mode": candidate_mode(selected),
            "sim_waf": selected.get("sim_waf"),
            "physical_waf": selected.get("physical_waf"),
            "sim_gc_blocks": selected.get("sim_gc_blocks"),
            "physical_gc_blocks": selected.get("physical_gc_blocks"),
            "sim_stale_secret_blocks": selected.get("sim_stale_secret_blocks"),
            "secret_waiting_end": selected.get("secret_waiting_end"),
            "max_secret_waiting": selected.get("max_secret_waiting"),
            "physical_reset_commands": selected.get("physical_reset_commands"),
            "residual_migration_commands": selected.get("residual_migration_commands"),
            "residual_migrated_blocks": selected.get("residual_migrated_blocks"),
            "residual_migration_budget_skips": selected.get("residual_migration_budget_skips"),
            "max_live_physical_zones": selected.get("max_live_physical_zones"),
            "max_active_pack_keys": selected.get("max_active_pack_keys"),
            "failed_rows": selected.get("failed_rows"),
            "physical_bytes_written": selected.get("physical_bytes_written"),
        },
        "relaxed_constraints": relaxed,
    }


def controller_decisions(
    dryrun_rows: list[dict[str, Any]],
    budget_rows: list[dict[str, Any]],
    mor: int | None,
) -> list[dict[str, Any]]:
    rows = dryrun_rows + budget_rows
    decisions = []
    for workload in sorted({row["workload"] for row in rows}):
        workload_rows = [row for row in rows if row["workload"] == workload]
        for profile in CONTROLLER_PROFILES:
            choice = choose_controller_candidate(workload_rows, profile, mor)
            decisions.append(
                {
                    "workload": workload,
                    "profile": profile["profile"],
                    "description": profile["description"],
                    "constraints": {
                        "max_physical_waf": profile["max_physical_waf"],
                        "max_secret_waiting": profile["max_secret_waiting"],
                        "zero_wait": profile["zero_wait"],
                        "mor": mor,
                    },
                    **choice,
                }
            )
    return decisions


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Residual Fallback Sweep",
        "",
        "This report evaluates the strict straggler fallback: epoch-bin packing plus bounded residual migration. The goal is to keep the number of live physical zones within the ZNS `mor/mar` budget while reducing stale-secret waiting.",
        "",
        f"- Device `mor`: `{summary['device_limits'].get('mor')}`",
        f"- Device `mar`: `{summary['device_limits'].get('mar')}`",
        "",
        "## Dry-Run Frontier",
        "",
        "| Workload | Best Zero-Wait Candidate | Physical WAF | Residual Blocks | Resets | Max Zones | Notes |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for workload, item in summary["best_candidates"].items():
        best_zero = item["best_zero_wait"][0] if item["best_zero_wait"] else None
        if best_zero is None:
            low = item["best_low_waf"][0] if item["best_low_waf"] else {}
            lines.append(
                "| `{workload}` | none under device budget | N/A | N/A | N/A | {max_z} | best low-WAF leaves `{wait}` waiting blocks |".format(
                    workload=workload,
                    max_z=fmt_int(low.get("max_live_physical_zones")),
                    wait=fmt_int(low.get("secret_waiting_end")),
                )
            )
            continue
        note = "strict mode practical" if float(best_zero.get("physical_waf") or 99.0) <= 2.0 else "strict mode is expensive"
        lines.append(
            "| `{workload}` | `{packing}`, th={threshold} | {waf} | {residual} | {resets} | {max_z} | {note} |".format(
                workload=workload,
                packing=best_zero["packing"],
                threshold=best_zero["threshold"],
                waf=fmt_float(best_zero.get("physical_waf")),
                residual=fmt_int(best_zero.get("residual_migrated_blocks")),
                resets=fmt_int(best_zero.get("physical_reset_commands")),
                max_z=fmt_int(best_zero.get("max_live_physical_zones")),
                note=note,
            )
        )

    if summary.get("budget_rows"):
        lines.extend(
            [
                "",
                "## Bounded-Overhead Budget Curve",
                "",
                "These dry-run rows keep the same residual threshold but cap total copied residual blocks. They define the low-overhead mode between no residual migration and strict zero-wait migration.",
                "",
                "| Workload | Packing | Threshold | Copy Budget | Physical WAF | Secret Waiting End | Residual Blocks | Budget Skips | Max Zones |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in sorted(
            summary["budget_rows"],
            key=lambda row: (row["workload"], row["packing"], int(row["threshold"]), int(row["copy_budget"])),
        ):
            lines.append(
                "| `{workload}` | `{packing}` | {threshold} | {budget} | {waf} | {waiting} | {residual} | {skips} | {max_z} |".format(
                    workload=row["workload"],
                    packing=row["packing"],
                    threshold=fmt_int(row.get("threshold")),
                    budget=fmt_int(row.get("copy_budget")),
                    waf=fmt_float(row.get("physical_waf")),
                    waiting=fmt_int(row.get("secret_waiting_end")),
                    residual=fmt_int(row.get("residual_migrated_blocks")),
                    skips=fmt_int(row.get("residual_migration_budget_skips")),
                    max_z=fmt_int(row.get("max_live_physical_zones")),
                )
            )

    if summary.get("budget_physical_rows"):
        lines.extend(
            [
                "",
                "## Actual ZNS Budget Curve",
                "",
                "These rows execute the bounded-copy budget points on the physical ZNS zonefs path. They are the hardware evidence for the WAF/exposure curve used by the residual controller.",
                "",
                "| Workload | Packing | Threshold | Copy Budget | Physical WAF | Secret Waiting End | Residual Blocks | Budget Skips | Resets | Max Zones | Failed Rows |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in sorted(
            summary["budget_physical_rows"],
            key=lambda row: (row["workload"], row["packing"], int(row["threshold"]), int(row["copy_budget"])),
        ):
            lines.append(
                "| `{workload}` | `{packing}` | {threshold} | {budget} | {waf} | {waiting} | {residual} | {skips} | {resets} | {max_z} | {failed} |".format(
                    workload=row["workload"],
                    packing=row["packing"],
                    threshold=fmt_int(row.get("threshold")),
                    budget=fmt_int(row.get("copy_budget")),
                    waf=fmt_float(row.get("physical_waf")),
                    waiting=fmt_int(row.get("secret_waiting_end")),
                    residual=fmt_int(row.get("residual_migrated_blocks")),
                    skips=fmt_int(row.get("residual_migration_budget_skips")),
                    resets=fmt_int(row.get("physical_reset_commands")),
                    max_z=fmt_int(row.get("max_live_physical_zones")),
                    failed=fmt_int(row.get("failed_rows")),
                )
            )

    if summary.get("controller_decisions"):
        lines.extend(
            [
                "",
                "## Residual Policy Controller",
                "",
                "The controller chooses among no-copy, bounded-copy, and strict zero-wait candidates using only the observed frontier, a physical WAF cap, a secret-waiting target, and the device `mor` limit.",
                "",
                "| Workload | Profile | Selected Mode | Packing | Threshold | Recommended Copy Budget | Physical WAF | Secret Waiting End | Residual Blocks | Relaxed Constraints |",
                "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for decision in sorted(summary["controller_decisions"], key=lambda row: (row["workload"], row["profile"])):
            selected = decision.get("selected") or {}
            relaxed = ", ".join(decision.get("relaxed_constraints", [])) or "none"
            lines.append(
                "| `{workload}` | `{profile}` | `{mode}` | `{packing}` | {threshold} | {budget} | {waf} | {waiting} | {residual} | {relaxed} |".format(
                    workload=decision["workload"],
                    profile=decision["profile"],
                    mode=selected.get("mode", "none"),
                    packing=selected.get("packing", "N/A"),
                    threshold=fmt_int(selected.get("threshold")),
                    budget=(
                        "unbounded"
                        if selected.get("recommended_copy_budget") is None
                        else fmt_int(selected.get("recommended_copy_budget"))
                    ),
                    waf=fmt_float(selected.get("physical_waf")),
                    waiting=fmt_int(selected.get("secret_waiting_end")),
                    residual=fmt_int(selected.get("residual_migrated_blocks")),
                    relaxed=relaxed,
                )
            )

    lines.extend(
        [
            "",
            "## Actual ZNS Representatives",
            "",
            "| Workload | Profile | Candidate | Sim WAF | Physical WAF | Secret Waiting End | Residual Blocks | Resets | Max Zones | Failed Rows |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in sorted(summary["physical_rows"], key=lambda row: (row["workload"], row.get("profile", ""))):
        lines.append(
            "| `{workload}` | `{profile}` | `{packing}`, th={threshold} | {sim_waf} | {physical_waf} | {waiting} | {residual} | {resets} | {max_z} | {failed} |".format(
                workload=row["workload"],
                profile=row.get("profile") or "representative",
                packing=row["packing"],
                threshold=row["threshold"],
                sim_waf=fmt_float(row.get("sim_waf")),
                physical_waf=fmt_float(row.get("physical_waf")),
                waiting=fmt_int(row.get("secret_waiting_end")),
                residual=fmt_int(row.get("residual_migrated_blocks")),
                resets=fmt_int(row.get("physical_reset_commands")),
                max_z=fmt_int(row.get("max_live_physical_zones")),
                failed=fmt_int(row.get("failed_rows")),
            )
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Residual migration is useful, but not universally cheap.",
            "- Exchange-like dynamic workload reaches zero final secret waiting with tiny copy cost.",
            "- Sysbench-like DB pressure reaches zero final secret waiting with moderate copy cost.",
            "- YCSB-F p8000 reaches zero final secret waiting only with very high physical WAF, now confirmed on actual ZNS, so strict residual mode should not be the default for that profile.",
            "- A residual copy budget creates a bounded-overhead mode: it preserves the open-zone bound and limits WAF, while explicitly reporting remaining stale-secret waiting.",
            "- The residual controller turns that frontier into deployable choices: low-overhead mode minimizes WAF, balanced mode enforces a waiting target under a WAF cap when possible, and strict mode chooses the cheapest zero-wait candidate.",
            "- The deployable design should expose two modes: low-overhead bounded exposure and strict zero-wait exposure.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=Path("artifacts/results/residual-fallback-sweep"))
    parser.add_argument(
        "--extra-physical",
        type=Path,
        action="append",
        default=[
            Path("artifacts/results/physical-robustness-ycsb-a-pqc4000/straggler005-residual-th12288-epochbin5-physical.json"),
            Path("artifacts/results/residual-fallback-sweep/ycsb-f-pqc8000-controller-low-overhead-physical.json"),
            Path("artifacts/results/residual-fallback-sweep/ycsb-f-pqc8000-controller-balanced-physical.json"),
            Path("artifacts/results/residual-fallback-sweep/ycsb-f-pqc8000-controller-strict-physical.json"),
        ],
    )
    parser.add_argument("--zns-id-ns", type=Path, default=Path("artifacts/results/physical-zns-zns-id-ns-latest.json"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/residual-fallback-sweep/summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/residual-fallback-sweep/summary.md"))
    args = parser.parse_args()

    zns = load_json(args.zns_id_ns)
    dryrun_rows = collect_dryruns(args.base)
    budget_rows = collect_budget_dryruns(args.base)
    budget_physical_rows = collect_budget_physical(args.base)
    physical_rows = collect_physical(args.base, args.extra_physical)
    controller_rows = controller_decisions(dryrun_rows, budget_rows, zns.get("mor"))
    summary = {
        "scope": "residual fallback threshold sweep across straggler workloads",
        "device_limits": {
            "mar": zns.get("mar"),
            "mor": zns.get("mor"),
            "numzrwa": zns.get("numzrwa"),
        },
        "dryrun_rows": dryrun_rows,
        "budget_rows": budget_rows,
        "budget_physical_rows": budget_physical_rows,
        "physical_rows": physical_rows,
        "best_candidates": best_candidates(dryrun_rows, zns.get("mor")),
        "controller_profiles": CONTROLLER_PROFILES,
        "controller_decisions": controller_rows,
        "decision": "use-residual-fallback-as-strict-exposure-mode",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "markdown_out": str(args.markdown_out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
