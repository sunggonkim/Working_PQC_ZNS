#!/usr/bin/env python3
"""Build a compact QUASAR component-ablation report from existing artifacts."""

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


def fmt_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{100.0 * value:.1f}%"


def fmt_int(value: int | float | None) -> str:
    return "N/A" if value is None else f"{int(value):,}"


def reduction(before: int | float | None, after: int | float | None) -> float | None:
    if before is None or float(before) == 0.0 or after is None:
        return None
    return 1.0 - (float(after) / float(before))


def physical_ycsb_rows(data: dict[str, Any], workload: str) -> dict[str, Any]:
    physical = data.get("physical", {}).get(workload, {})
    return physical.get("by_policy", {})


def physical_sysbench_rows(data: dict[str, Any]) -> dict[str, Any]:
    rows = data.get("physical", {}).get("by_policy_packing", {})
    return {
        "dogi-history": rows.get("dogi-history::secret-group", {}),
        "quasar": rows.get("quasar::secret-group", {}),
        "quasar-dogi-hybrid": rows.get("quasar-dogi-hybrid::secret-group", {}),
    }


def physical_dynamic_rows(data: dict[str, Any], name_fragment: str) -> dict[str, Any]:
    for item in data.get("physical", []):
        path = str(item.get("path", ""))
        traces = " ".join(str(trace) for trace in item.get("traces", []))
        if name_fragment in path or name_fragment in traces:
            return item.get("policies", {})
    return {}


def metric_row(workload: str, policy: str, item: dict[str, Any]) -> dict[str, Any]:
    waiting = item.get("secret_blocks_waiting_for_physical_reset")
    if waiting is None:
        waiting = item.get("secret_waiting_end")
    return {
        "workload": workload,
        "policy": policy,
        "waf": item.get("sim_waf") or item.get("physical_waf"),
        "gc_blocks": item.get("sim_gc_blocks"),
        "stale_secret_blocks": item.get("sim_stale_secret_blocks"),
        "secret_waiting_end": waiting,
        "semantic_resets": item.get("physical_reset_commands"),
        "avg_space_utilization": item.get("avg_space_utilization"),
        "max_live_physical_zones": item.get("max_live_physical_zones"),
    }


def summarize_main_components(
    ycsb: dict[str, Any], sysbench: dict[str, Any], dynamic: dict[str, Any]
) -> list[dict[str, Any]]:
    cases = [
        ("YCSB-A pqc4000", physical_ycsb_rows(ycsb, "ycsb-a-pqc4000")),
        ("Sysbench-OLTP pqc2000+pqc4000", physical_sysbench_rows(sysbench)),
        ("Exchange-like pqc8000", physical_dynamic_rows(dynamic, "exchange-pqc8000")),
    ]
    rows: list[dict[str, Any]] = []
    for workload, policies in cases:
        dogi = metric_row(workload, "history-only DOGI-style", policies.get("dogi-history", {}))
        quasar = metric_row(workload, "lifecycle hints only", policies.get("quasar", {}))
        hybrid = metric_row(workload, "hints + DOGI payload fallback", policies.get("quasar-dogi-hybrid", {}))
        rows.extend([dogi, quasar, hybrid])
        rows.append(
            {
                "workload": workload,
                "policy": "component delta",
                "dogi_to_quasar_gc_reduction": reduction(dogi.get("gc_blocks"), quasar.get("gc_blocks")),
                "dogi_to_hybrid_gc_reduction": reduction(dogi.get("gc_blocks"), hybrid.get("gc_blocks")),
                "quasar_to_hybrid_gc_reduction": reduction(quasar.get("gc_blocks"), hybrid.get("gc_blocks")),
                "dogi_to_hybrid_stale_reduction_blocks": (
                    int(dogi.get("stale_secret_blocks") or 0) - int(hybrid.get("stale_secret_blocks") or 0)
                ),
            }
        )
    return rows


def summarize_adaptive(adaptive: dict[str, Any]) -> dict[str, Any]:
    ycsb = adaptive.get("ycsb_pressure", {})
    sysbench = adaptive.get("sysbench_pressure", {})
    return {
        "decision": adaptive.get("decision"),
        "current_wins": int(ycsb.get("current_wins", 0)) + int(sysbench.get("current_wins", 0)),
        "adaptive_wins": int(ycsb.get("adaptive_wins", 0)) + int(sysbench.get("adaptive_wins", 0)),
        "ties": int(ycsb.get("ties", 0)) + int(sysbench.get("ties", 0)),
        "reason": adaptive.get("decision_reason"),
    }


def summarize_residual(robustness: dict[str, Any], residual: dict[str, Any]) -> dict[str, Any]:
    exact = robustness.get("straggler_5pct_exact_secret_group", {}).get("hybrid", {})
    binned = robustness.get("straggler_5pct_epoch_bin_4", {}).get("hybrid", {})
    fallback = robustness.get("straggler_5pct_epoch_bin_5_residual_12288", {}).get("hybrid", {})
    strict = {}
    for row in residual.get("physical_rows", []):
        if row.get("workload") == "ycsb-f-pqc8000" and row.get("profile") == "strict_zero_wait":
            strict = row
            break
    return {
        "device_limits": robustness.get("device_limits", {}),
        "exact_secret_group": {
            "failed_rows": robustness.get("straggler_5pct_exact_secret_group", {}).get("failed_rows"),
            "secret_waiting_end": exact.get("secret_waiting_end"),
            "max_live_physical_zones": exact.get("max_live_physical_zones"),
        },
        "epoch_bin_no_residual": {
            "failed_rows": robustness.get("straggler_5pct_epoch_bin_4", {}).get("failed_rows"),
            "secret_waiting_end": binned.get("secret_waiting_end"),
            "max_live_physical_zones": binned.get("max_live_physical_zones"),
        },
        "epoch_bin_with_residual": {
            "failed_rows": robustness.get("straggler_5pct_epoch_bin_5_residual_12288", {}).get("failed_rows"),
            "physical_waf": fallback.get("physical_waf"),
            "secret_waiting_end": fallback.get("secret_waiting_end"),
            "residual_migrated_blocks": fallback.get("residual_migrated_blocks"),
            "max_live_physical_zones": fallback.get("max_live_physical_zones"),
        },
        "strict_ycsb_f_boundary": {
            "physical_waf": strict.get("physical_waf"),
            "secret_waiting_end": strict.get("secret_waiting_end"),
            "residual_migrated_blocks": strict.get("residual_migrated_blocks"),
        },
    }


def summarize(
    ycsb: dict[str, Any],
    sysbench: dict[str, Any],
    dynamic: dict[str, Any],
    adaptive: dict[str, Any],
    robustness: dict[str, Any],
    residual: dict[str, Any],
) -> dict[str, Any]:
    return {
        "claim": (
            "Lifecycle hints remove stale-secret exposure; DOGI payload fallback removes remaining payload-GC cost; "
            "adaptive binning is not the default for current single-tenant pressure; residual migration is a strict "
            "straggler fallback with explicit copy cost."
        ),
        "main_components": summarize_main_components(ycsb, sysbench, dynamic),
        "adaptive_admission": summarize_adaptive(adaptive),
        "residual_fallback": summarize_residual(robustness, residual),
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# QUASAR Component Ablation",
        "",
        summary["claim"],
        "",
        "## Main Components",
        "",
        "| Workload | Policy / Component | WAF | GC Blocks | Stale Secrets | Waiting End | Resets | Avg Util | Max Zones |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary["main_components"]:
        if row["policy"] == "component delta":
            lines.append(
                "| `{workload}` | `delta: DOGI->QUASAR / DOGI->Hybrid / QUASAR->Hybrid` | {dq} | {dh} | {qh} | stale removed {stale} |  |  |  |".format(
                    workload=row["workload"],
                    dq=fmt_pct(row.get("dogi_to_quasar_gc_reduction")),
                    dh=fmt_pct(row.get("dogi_to_hybrid_gc_reduction")),
                    qh=fmt_pct(row.get("quasar_to_hybrid_gc_reduction")),
                    stale=fmt_int(row.get("dogi_to_hybrid_stale_reduction_blocks")),
                )
            )
            continue
        lines.append(
            "| `{workload}` | `{policy}` | {waf} | {gc} | {stale} | {waiting} | {resets} | {util} | {zones} |".format(
                workload=row["workload"],
                policy=row["policy"],
                waf=fmt_float(row.get("waf")),
                gc=fmt_int(row.get("gc_blocks")),
                stale=fmt_int(row.get("stale_secret_blocks")),
                waiting=fmt_int(row.get("secret_waiting_end")),
                resets=fmt_int(row.get("semantic_resets")),
                util=fmt_float(row.get("avg_space_utilization"), 3),
                zones=fmt_int(row.get("max_live_physical_zones")),
            )
        )

    adaptive = summary["adaptive_admission"]
    residual = summary["residual_fallback"]
    exact = residual["exact_secret_group"]
    binned = residual["epoch_bin_no_residual"]
    fallback = residual["epoch_bin_with_residual"]
    strict = residual["strict_ycsb_f_boundary"]
    lines.extend(
        [
            "",
            "## Admission And Fallback Decisions",
            "",
            "| Mechanism | Evidence | Decision |",
            "| --- | --- | --- |",
            (
                "| Adaptive admission/binning | current hybrid wins "
                f"{fmt_int(adaptive['current_wins'])}; adaptive wins {fmt_int(adaptive['adaptive_wins'])}; ties {fmt_int(adaptive['ties'])} "
                "| Keep current hybrid as default for current single-tenant pressure; keep adaptive mode for multi-tenant/open-zone stress. |"
            ),
            (
                "| Open-zone-aware binning | exact straggler mode fails "
                f"{fmt_int(exact['failed_rows'])} row and reaches {fmt_int(exact['max_live_physical_zones'])} live zones; "
                f"epoch-bin completes at {fmt_int(binned['max_live_physical_zones'])} zones but leaves {fmt_int(binned['secret_waiting_end'])} waiting secrets "
                "| Binning is required for device open-zone limits, but it is not enough for strict exposure. |"
            ),
            (
                "| Residual migration | residual fallback ends with "
                f"{fmt_int(fallback['secret_waiting_end'])} waiting secrets at WAF {fmt_float(fallback['physical_waf'])} "
                f"after copying {fmt_int(fallback['residual_migrated_blocks'])} blocks; strict YCSB-F costs WAF {fmt_float(strict['physical_waf'])} "
                "| Expose residual migration as a strict mode with explicit cost, not as the default for every workload. |"
            ),
            "",
            "## Interpretation",
            "",
            "- Lifecycle hints are the security-critical component: they drive stale-secret blocks to zero in the clean pressure rows.",
            "- The DOGI payload fallback is the performance component: it preserves history placement for ordinary payload and removes GC that pure semantic grouping can leave behind.",
            "- Admission/binning and residual migration are boundary mechanisms. They make QUASAR deployable under open-zone limits and stragglers, but they introduce visible WAF or exposure tradeoffs.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ycsb", type=Path, default=Path("artifacts/results/fast-ycsb-pressure/ycsb-pressure-summary.json"))
    parser.add_argument("--sysbench", type=Path, default=Path("artifacts/results/fast-db-pressure/sysbench-pressure-summary.json"))
    parser.add_argument("--dynamic", type=Path, default=Path("artifacts/results/fast-dynamic-pressure/dynamic-pressure-summary.json"))
    parser.add_argument("--adaptive", type=Path, default=Path("artifacts/results/adaptive-policy-comparison.json"))
    parser.add_argument("--robustness", type=Path, default=Path("artifacts/results/physical-robustness-ycsb-a-pqc4000/summary.json"))
    parser.add_argument("--residual", type=Path, default=Path("artifacts/results/residual-fallback-sweep/summary.json"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/component-ablation.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/component-ablation.md"))
    args = parser.parse_args()

    summary = summarize(
        load_json(args.ycsb),
        load_json(args.sysbench),
        load_json(args.dynamic),
        load_json(args.adaptive),
        load_json(args.robustness),
        load_json(args.residual),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "markdown_out": str(args.markdown_out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
