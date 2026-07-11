#!/usr/bin/env python3
"""Generate paper-facing QUASAR result summaries from artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


POLICY_LABELS = {
    "fifo": "FIFO",
    "sepbit-style": "SepBIT-style",
    "midas-style": "MiDAS-style",
    "dogi-history": "DOGI-style",
    "quasar": "QUASAR",
    "quasar-dogi-hybrid": "QUASAR-DOGI hybrid",
    "epoch-oracle": "Epoch oracle",
}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def fmt_float(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def fmt_int(value: int | float) -> str:
    return f"{int(value):,}"


def rows_by_policy(rows: list[dict]) -> dict[str, dict]:
    return {row["policy"]: row for row in rows}


def workload_table(rows: list[dict]) -> tuple[list[str], list[list[str]]]:
    by_workload: dict[str, dict[str, dict]] = {}
    for row in rows:
        by_workload.setdefault(row["workload"], {})[row["policy"]] = row
    policies = [
        "fifo",
        "sepbit-style",
        "midas-style",
        "dogi-history",
        "quasar",
        "quasar-dogi-hybrid",
        "epoch-oracle",
    ]
    header = ["Workload", *[POLICY_LABELS[p] for p in policies]]
    body = []
    for workload in sorted(by_workload):
        policy_rows = by_workload[workload]
        body.append(
            [
                f"`{workload}`",
                *[fmt_float(policy_rows[p]["waf"]) if p in policy_rows else "N/A" for p in policies],
            ]
        )
    return header, body


def mixed_table(rows: list[dict]) -> tuple[list[str], list[list[str]]]:
    header = ["Policy", "WAF", "GC Blocks", "Zone Util.", "Epoch Imp.", "Intent Imp.", "Stale Secrets"]
    body = []
    for row in rows:
        body.append(
            [
                POLICY_LABELS.get(row["policy"], row["policy"]),
                fmt_float(row["waf"]),
                fmt_int(row["gc_write_blocks"]),
                fmt_float(row["zone_utilization"]),
                fmt_float(row["epoch_impurity"]),
                fmt_float(row["intent_impurity"]),
                fmt_int(row["stale_secret_blocks_remaining"]),
            ]
        )
    return header, body


def exposure_summary(rows: list[dict]) -> tuple[list[str], list[list[str]], dict]:
    by_policy: dict[str, list[dict]] = {}
    for row in rows:
        by_policy.setdefault(row["policy"], []).append(row)
    summary = {}
    body = []
    for policy in ["fifo", "dogi-history", "quasar"]:
        vals = sorted(by_policy.get(policy, []), key=lambda row: row["ts"])
        if not vals:
            continue
        max_stale = max(row["stale_secret_blocks"] for row in vals)
        final_stale = vals[-1]["stale_secret_blocks"]
        summary[policy] = {"max_stale_secret_blocks": max_stale, "final_stale_secret_blocks": final_stale}
        body.append([POLICY_LABELS.get(policy, policy), fmt_int(max_stale), fmt_int(final_stale)])
    return ["Policy", "Max Stale Secret Blocks", "Final Stale Secret Blocks"], body, summary


def markdown_table(header: list[str], body: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def make_report(args: argparse.Namespace) -> tuple[dict, str]:
    mixed = load_json(args.mixed)
    e1 = load_json(args.e1)
    timeline = load_json(args.timeline)
    acceptance = load_json(args.acceptance)
    liboqs_summary = load_json(args.liboqs_summary)
    liboqs_verification = load_json(args.liboqs_verification)
    file_zns = load_json(args.file_zns_summary)
    nullblk_summary = load_json(args.nullblk_summary)
    zns_preflight = load_json(args.zns_preflight)
    dogi_preflight = load_json(args.dogi_preflight)
    dogi_nullblk_preflight = load_json(args.dogi_nullblk_preflight)
    dogi_run = load_json(args.dogi_run)
    nullblk_preflight = load_json(args.nullblk_preflight)

    mixed_header, mixed_body = mixed_table(mixed)
    e1_header, e1_body = workload_table(e1)
    exposure_header, exposure_body, exposure = exposure_summary(timeline)
    liboqs_by_policy = rows_by_policy(liboqs_verification)
    summary = {
        "acceptance": {
            "passed": acceptance["passed"],
            "passed_gates": acceptance["passed_gates"],
            "total_gates": acceptance["total_gates"],
        },
        "mixed": {row["policy"]: {"waf": row["waf"], "gc_write_blocks": row["gc_write_blocks"]} for row in mixed},
        "dogi_feature_model": {
            "feature_count": rows_by_policy(mixed).get("dogi-history", {}).get("dogi_feature_count"),
            "feature_samples": rows_by_policy(mixed).get("dogi-history", {}).get("dogi_feature_samples"),
            "runtime_feature_keys": rows_by_policy(mixed).get("dogi-history", {}).get("dogi_runtime_feature_keys"),
        },
        "workload_waf": {
            row["workload"] + "/" + row["policy"]: row["waf"]
            for row in e1
        },
        "exposure": exposure,
        "liboqs": {
            "sessions": liboqs_summary["sessions"],
            "kem": liboqs_summary["kem"],
            "sig": liboqs_summary["sig"],
            "all_kem_ok": liboqs_summary["all_kem_ok"],
            "all_sig_ok": liboqs_summary["all_sig_ok"],
            "quasar_waf": liboqs_by_policy["quasar"]["waf"],
            "dogi_waf": liboqs_by_policy["dogi-history"]["waf"],
            "quasar_stale_secret_blocks": liboqs_by_policy["quasar"]["stale_secret_blocks_remaining"],
        },
        "file_zns": {
            "append_commands": file_zns["append_commands"],
            "reset_family_commands": file_zns["reset_family_commands"],
            "emulator_reset_zones": file_zns["emulator_reset_zones"],
            "emulator_final_used_zones": file_zns["emulator_final_used_zones"],
            "emulator_zone_count": file_zns["emulator_zone_count"],
        },
        "nullblk_replay": {
            "append_commands": nullblk_summary["append_commands"],
            "reset_family_commands": nullblk_summary["reset_family_commands"],
            "real_reset_zones": nullblk_summary["real_reset_zones"],
            "real_bytes_written": nullblk_summary["real_bytes_written"],
            "real_final_used_zones": nullblk_summary["real_final_used_zones"],
            "real_zone_count": nullblk_summary["real_zone_count"],
        },
        "dogi_real_nullblk_run": {
            "completed": dogi_run["completed"],
            "trace_path": dogi_run["trace_path"],
            "user_write_gib": dogi_run["user_write_gib"],
            "gc_write_gib": dogi_run["gc_write_gib"],
            "waf": dogi_run["waf"],
            "zenfs_free_mb": dogi_run["zenfs_free_mb"],
        },
        "preflight": {
            "zoned_devices": len(zns_preflight["zoned_devices"]),
            "can_run_real_zns_replay": zns_preflight["can_run_real_zns_replay"],
            "dogi_parser_matches_adapter": dogi_preflight["repo"]["parser_matches_adapter"],
            "dogi_can_run_full_prototype": dogi_preflight["can_run_full_prototype"],
            "dogi_nullblk_can_run_full_prototype": dogi_nullblk_preflight["can_run_full_prototype"],
            "null_blk_module_available": nullblk_preflight.get("null_blk_module_available"),
            "null_blk_can_create_without_sudo": nullblk_preflight.get("can_create_without_sudo"),
        },
    }

    md = [
        "# QUASAR Results Summary",
        "",
        f"- Acceptance: {acceptance['passed_gates']}/{acceptance['total_gates']} gates passed.",
        f"- liboqs trace: {liboqs_summary['sessions']} sessions, {liboqs_summary['kem']} + {liboqs_summary['sig']}, KEM/SIG verified.",
        f"- File-ZNS replay: {file_zns['append_commands']:,} appends, {file_zns['reset_family_commands']:,} reset-family commands, {file_zns['emulator_reset_zones']:,} zone resets.",
        f"- null_blk ZNS replay: {nullblk_summary['append_commands']:,} appends, {nullblk_summary['real_reset_zones']:,} real zone resets, {nullblk_summary['real_bytes_written']:,} bytes written.",
        f"- External DOGI null_blk run: completed={dogi_run['completed']}, WAF={fmt_float(dogi_run['waf'])}, user={dogi_run['user_write_gib']:.3f} GiB, GC={dogi_run['gc_write_gib']:.3f} GiB.",
        f"- Real ZNS preflight: {len(zns_preflight['zoned_devices'])} zoned devices detected.",
        f"- null_blk path: module_available={nullblk_preflight.get('null_blk_module_available')}, can_create_without_sudo={nullblk_preflight.get('can_create_without_sudo')}.",
        f"- DOGI null_blk preflight: can_run_full_prototype={dogi_nullblk_preflight['can_run_full_prototype']}.",
        f"- DOGI-style model: {rows_by_policy(mixed).get('dogi-history', {}).get('dogi_feature_count', 0)} runtime features, {rows_by_policy(mixed).get('dogi-history', {}).get('dogi_feature_samples', 0):,} write samples.",
        "",
        "## Mixed Trace",
        "",
        markdown_table(mixed_header, mixed_body),
        "",
        "## Workload Suite WAF",
        "",
        markdown_table(e1_header, e1_body),
        "",
        "## Exposure Timeline",
        "",
        markdown_table(exposure_header, exposure_body),
        "",
        "## liboqs Trace",
        "",
        markdown_table(
            ["Metric", "Value"],
            [
                ["Sessions", fmt_int(liboqs_summary["sessions"])],
                ["KEM", liboqs_summary["kem"]],
                ["Signature", liboqs_summary["sig"]],
                ["KEM OK", str(liboqs_summary["all_kem_ok"])],
                ["Signature OK", str(liboqs_summary["all_sig_ok"])],
                ["DOGI-style WAF", fmt_float(liboqs_by_policy["dogi-history"]["waf"])],
                ["QUASAR WAF", fmt_float(liboqs_by_policy["quasar"]["waf"])],
                ["QUASAR Stale Secrets", fmt_int(liboqs_by_policy["quasar"]["stale_secret_blocks_remaining"])],
            ],
        ),
        "",
        "## External DOGI Prototype",
        "",
        markdown_table(
            ["Metric", "Value"],
            [
                ["Completed", str(dogi_run["completed"])],
                ["Trace", f"`{dogi_run['trace_path']}`"],
                ["ZenFS Free MB", fmt_float(dogi_run["zenfs_free_mb"])],
                ["User Write GiB", fmt_float(dogi_run["user_write_gib"])],
                ["GC Write GiB", fmt_float(dogi_run["gc_write_gib"])],
                ["WAF", fmt_float(dogi_run["waf"])],
            ],
        ),
    ]
    return summary, "\n".join(md) + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mixed", type=Path, default=Path("artifacts/results/pqc-mixed-verification.json"))
    parser.add_argument("--e1", type=Path, default=Path("artifacts/results/e1-workloads.json"))
    parser.add_argument("--timeline", type=Path, default=Path("artifacts/results/e4-exposure-timeline.json"))
    parser.add_argument("--acceptance", type=Path, default=Path("artifacts/results/acceptance-report.json"))
    parser.add_argument("--liboqs-summary", type=Path, default=Path("artifacts/results/liboqs-pqc-summary.json"))
    parser.add_argument("--liboqs-verification", type=Path, default=Path("artifacts/results/liboqs-pqc-verification.json"))
    parser.add_argument("--file-zns-summary", type=Path, default=Path("artifacts/results/pqc-mixed-file-zns-summary.json"))
    parser.add_argument("--nullblk-summary", type=Path, default=Path("artifacts/results/pqc-mixed-nullblk-summary.json"))
    parser.add_argument("--zns-preflight", type=Path, default=Path("artifacts/results/zns-preflight.json"))
    parser.add_argument("--dogi-preflight", type=Path, default=Path("artifacts/results/dogi-preflight.json"))
    parser.add_argument("--dogi-nullblk-preflight", type=Path, default=Path("artifacts/results/dogi-preflight-nullblk.json"))
    parser.add_argument("--dogi-run", type=Path, default=Path("artifacts/results/dogi-nullblk-full-run.json"))
    parser.add_argument("--nullblk-preflight", type=Path, default=Path("artifacts/results/nullblk-zoned-preflight.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/quasar-results-summary.md"))
    parser.add_argument("--json-out", type=Path, default=Path("artifacts/results/quasar-results-summary.json"))
    args = parser.parse_args()

    summary, markdown = make_report(args)
    write_json(args.json_out, summary)
    write_text(args.markdown_out, markdown)
    print(f"wrote {args.json_out}")
    print(f"wrote {args.markdown_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
