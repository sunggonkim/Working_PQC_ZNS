#!/usr/bin/env python3
"""Check plan.md acceptance criteria against generated artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Gate:
    name: str
    passed: bool
    evidence: dict


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def e1_by_workload(rows: list[dict]) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for row in rows:
        out.setdefault(row["workload"], {})[row["policy"]] = row
    return out


def gate_quasar_beats_dogi(e1_rows: list[dict], min_workloads: int) -> Gate:
    by_workload = e1_by_workload(e1_rows)
    wins = []
    comparisons = {}
    for workload, policies in sorted(by_workload.items()):
        quasar = policies.get("quasar")
        dogi = policies.get("dogi-history")
        if not quasar or not dogi:
            continue
        won = quasar["waf"] < dogi["waf"]
        comparisons[workload] = {"quasar_waf": quasar["waf"], "dogi_waf": dogi["waf"], "won": won}
        if won:
            wins.append(workload)
    return Gate(
        "quasar_beats_dogi_on_at_least_three_workloads",
        len(wins) >= min_workloads,
        {"wins": wins, "win_count": len(wins), "required": min_workloads, "comparisons": comparisons},
    )


def gate_waf_and_utilization(e1_rows: list[dict]) -> Gate:
    quasar_rows = [row for row in e1_rows if row.get("policy") == "quasar"]
    missing = [
        row.get("workload", "<unknown>")
        for row in quasar_rows
        if "waf" not in row or "zone_utilization" not in row
    ]
    valid = [
        row.get("workload", "<unknown>")
        for row in quasar_rows
        if row.get("waf", 0) > 0 and row.get("zone_utilization", 0) > 0
    ]
    return Gate(
        "quasar_reports_waf_and_zone_utilization",
        bool(quasar_rows) and not missing and len(valid) == len(quasar_rows),
        {"quasar_rows": len(quasar_rows), "valid_workloads": valid, "missing": missing},
    )


def gate_bad_hints(e5_rows: list[dict], waf_threshold: float) -> Gate:
    stressed = [
        row
        for row in e5_rows
        if row.get("hint_missing_rate", 0) >= 0.05
        or row.get("wrong_epoch_rate", 0) >= 0.05
        or row.get("straggler_rate", 0) >= 0.05
    ]
    max_waf = max((row.get("waf", 0.0) for row in stressed), default=0.0)
    failed_gc = max((row.get("failed_gc_attempts", 0) for row in stressed), default=0)
    return Gate(
        "quasar_survives_5_percent_bad_hints",
        bool(stressed) and max_waf <= waf_threshold and failed_gc == 0,
        {
            "stressed_rows": len(stressed),
            "max_waf": max_waf,
            "waf_threshold": waf_threshold,
            "max_failed_gc_attempts": failed_gc,
        },
    )


def gate_exposure_window(timeline_rows: list[dict]) -> Gate:
    by_policy: dict[str, list[dict]] = {}
    for row in timeline_rows:
        by_policy.setdefault(row["policy"], []).append(row)
    max_by_policy = {
        policy: max(row["stale_secret_blocks"] for row in rows)
        for policy, rows in by_policy.items()
        if rows
    }
    final_by_policy = {
        policy: sorted(rows, key=lambda row: row["ts"])[-1]["stale_secret_blocks"]
        for policy, rows in by_policy.items()
        if rows
    }
    quasar_max = max_by_policy.get("quasar", 0)
    dogi_max = max_by_policy.get("dogi-history", 0)
    fifo_max = max_by_policy.get("fifo", 0)
    passed = quasar_max < dogi_max and quasar_max < fifo_max and final_by_policy.get("quasar", 1) == 0
    return Gate(
        "exposure_window_graph_shows_secret_drop",
        passed,
        {"max_stale_secret_blocks": max_by_policy, "final_stale_secret_blocks": final_by_policy},
    )


def gate_dogi_baseline(dogi_adapter: dict, dogi_preflight: dict) -> Gate:
    passed = (
        dogi_adapter.get("dogi_lines", 0) > 0
        and dogi_adapter.get("dogi_tombstones", 0) > 0
        and dogi_preflight.get("repo", {}).get("parser_matches_adapter", False)
        and dogi_preflight.get("trace", {}).get("all_lines_usable", False)
    )
    return Gate(
        "dogi_full_or_justified_dogi_style_included",
        passed,
        {
            "dogi_lines": dogi_adapter.get("dogi_lines", 0),
            "dogi_tombstones": dogi_adapter.get("dogi_tombstones", 0),
            "parser_matches_adapter": dogi_preflight.get("repo", {}).get("parser_matches_adapter", False),
            "trace_all_lines_usable": dogi_preflight.get("trace", {}).get("all_lines_usable", False),
            "can_run_full_prototype": dogi_preflight.get("can_run_full_prototype", False),
        },
    )


def gate_dogi_feature_coverage(mixed_rows: list[dict]) -> Gate:
    dogi = next((row for row in mixed_rows if row.get("policy") == "dogi-history"), {})
    required = [
        "dogi_uses_lba",
        "dogi_uses_freq_bit",
        "dogi_uses_freq_bit2",
        "dogi_uses_interval_bit",
        "dogi_uses_seg_accessed",
        "dogi_uses_prev_lba",
    ]
    missing = [name for name in required if dogi.get(name) != 1]
    passed = (
        dogi.get("dogi_feature_count") == 6
        and not missing
        and dogi.get("dogi_feature_samples", 0) > 0
        and dogi.get("prediction_samples", 0) > 0
    )
    return Gate(
        "dogi_style_models_six_runtime_features",
        passed,
        {
            "dogi_feature_count": dogi.get("dogi_feature_count"),
            "missing_feature_flags": missing,
            "dogi_feature_samples": dogi.get("dogi_feature_samples"),
            "prediction_samples": dogi.get("prediction_samples"),
            "runtime_feature_keys": dogi.get("dogi_runtime_feature_keys"),
        },
    )


def gate_liboqs_trace(liboqs_summary: dict, liboqs_verification: list[dict]) -> Gate:
    by_policy = {row.get("policy"): row for row in liboqs_verification}
    quasar = by_policy.get("quasar", {})
    dogi = by_policy.get("dogi-history", {})
    passed = (
        liboqs_summary.get("sessions", 0) > 0
        and liboqs_summary.get("all_kem_ok", False)
        and liboqs_summary.get("all_sig_ok", False)
        and quasar.get("stale_secret_blocks_remaining", 1) == 0
        and quasar.get("waf", 99) < dogi.get("waf", 0)
    )
    return Gate(
        "liboqs_trace_generated_and_verified",
        passed,
        {
            "sessions": liboqs_summary.get("sessions", 0),
            "all_kem_ok": liboqs_summary.get("all_kem_ok", False),
            "all_sig_ok": liboqs_summary.get("all_sig_ok", False),
            "kem": liboqs_summary.get("kem"),
            "sig": liboqs_summary.get("sig"),
            "quasar_waf": quasar.get("waf"),
            "dogi_waf": dogi.get("waf"),
            "quasar_stale_secret_blocks": quasar.get("stale_secret_blocks_remaining"),
        },
    )


def gate_file_zns_replay(file_zns_summary: dict) -> Gate:
    passed = (
        file_zns_summary.get("backend") == "file-zns"
        and not file_zns_summary.get("dry_run_only", True)
        and file_zns_summary.get("emulator_append_commands", 0) == file_zns_summary.get("append_commands", -1)
        and file_zns_summary.get("emulator_reset_commands", 0) == file_zns_summary.get("reset_family_commands", -1)
        and file_zns_summary.get("emulator_reset_zones", 0) > 0
        and file_zns_summary.get("emulator_final_used_zones", 1) <= file_zns_summary.get("emulator_zone_count", 0)
    )
    return Gate(
        "file_zns_emulated_replay_executed",
        passed,
        {
            "backend": file_zns_summary.get("backend"),
            "dry_run_only": file_zns_summary.get("dry_run_only"),
            "append_commands": file_zns_summary.get("append_commands"),
            "emulator_append_commands": file_zns_summary.get("emulator_append_commands"),
            "reset_family_commands": file_zns_summary.get("reset_family_commands"),
            "emulator_reset_commands": file_zns_summary.get("emulator_reset_commands"),
            "emulator_reset_zones": file_zns_summary.get("emulator_reset_zones"),
            "emulator_final_used_zones": file_zns_summary.get("emulator_final_used_zones"),
            "emulator_zone_count": file_zns_summary.get("emulator_zone_count"),
        },
    )


def gate_real_nullblk_replay(nullblk_summary: dict) -> Gate:
    append_blocks = nullblk_summary.get("append_blocks", 0)
    passed = (
        nullblk_summary.get("backend") == "blkzone-zns"
        and nullblk_summary.get("real_backend") == "blkzone-zns"
        and str(nullblk_summary.get("real_device", "")).startswith("/dev/nullb")
        and not nullblk_summary.get("dry_run_only", True)
        and nullblk_summary.get("append_commands", 0) == nullblk_summary.get("real_append_commands", -1)
        and nullblk_summary.get("reset_family_commands", 0) == nullblk_summary.get("real_reset_commands", -1)
        and nullblk_summary.get("real_reset_zones", 0) > 0
        and nullblk_summary.get("real_bytes_written", 0) == append_blocks * 4096
        and nullblk_summary.get("real_final_used_zones", 1) <= nullblk_summary.get("real_zone_count", 0)
    )
    return Gate(
        "real_nullblk_zoned_replay_executed",
        passed,
        {
            "backend": nullblk_summary.get("backend"),
            "real_device": nullblk_summary.get("real_device"),
            "append_commands": nullblk_summary.get("append_commands"),
            "real_append_commands": nullblk_summary.get("real_append_commands"),
            "reset_family_commands": nullblk_summary.get("reset_family_commands"),
            "real_reset_commands": nullblk_summary.get("real_reset_commands"),
            "real_reset_zones": nullblk_summary.get("real_reset_zones"),
            "real_bytes_written": nullblk_summary.get("real_bytes_written"),
            "real_final_used_zones": nullblk_summary.get("real_final_used_zones"),
            "real_zone_count": nullblk_summary.get("real_zone_count"),
        },
    )


def gate_physical_zonefs_replay(physical_replay: dict) -> Gate:
    latency = physical_replay.get("latency", {})
    passed = (
        physical_replay.get("execute", False)
        and physical_replay.get("reset_issued") is False
        and physical_replay.get("append_commands", 0) > 0
        and physical_replay.get("bytes_written", 0) > 0
        and physical_replay.get("zone_files_used", 0) >= 2
        and physical_replay.get("unique_families", 0) >= 2
        and latency.get("p99_ns", 0) > 0
    )
    return Gate(
        "physical_zonefs_direct_replay_executed",
        passed,
        {
            "execute": physical_replay.get("execute"),
            "reset_issued": physical_replay.get("reset_issued"),
            "append_commands": physical_replay.get("append_commands"),
            "bytes_written": physical_replay.get("bytes_written"),
            "zone_files_used": physical_replay.get("zone_files_used"),
            "unique_families": physical_replay.get("unique_families"),
            "p99_append_latency_ns": latency.get("p99_ns"),
        },
    )


def gate_physical_zonefs_dogi_suite(physical_suite: dict) -> Gate:
    rows = physical_suite.get("rows", [])
    failed = physical_suite.get("failed_workloads", [])
    passed = (
        physical_suite.get("all_passed", False)
        and physical_suite.get("workloads", 0) >= 6
        and physical_suite.get("total_bytes_written", 0) >= 3 * 1024 * 1024 * 1024
        and physical_suite.get("total_append_commands", 0) > 100_000
        and physical_suite.get("total_reset_family_commands", 0) > 0
        and physical_suite.get("max_active_zone_files", 999) <= 13
        and all(row.get("append_p99_ns", 0) > 0 for row in rows)
        and not failed
    )
    return Gate(
        "physical_zonefs_dogi_pqc2000_suite_completed",
        passed,
        {
            "workloads": physical_suite.get("workloads"),
            "failed_workloads": failed,
            "total_gib_written": physical_suite.get("total_gib_written"),
            "total_append_commands": physical_suite.get("total_append_commands"),
            "total_reset_family_commands": physical_suite.get("total_reset_family_commands"),
            "max_active_zone_files": physical_suite.get("max_active_zone_files"),
            "median_p99_append_latency_ns": physical_suite.get("median_p99_append_latency_ns"),
        },
    )


def gate_physical_zonefs_write_pressure(physical_pressure: dict) -> Gate:
    summary = physical_pressure.get("summary", {})
    comparison = summary.get("dogi_vs_hybrid", {})
    passed = (
        physical_pressure.get("execute", False)
        and not physical_pressure.get("failed", True)
        and summary.get("all_passed", False)
        and summary.get("row_count", 0) >= 30
        and summary.get("total_bytes_written", 0) >= 100 * 1024 * 1024 * 1024
        and comparison.get("hybrid_block_reduction_vs_dogi", 0.0) > 0.0
        and comparison.get("stale_secret_blocks_avoided", 0) > 0
    )
    return Gate(
        "physical_zonefs_write_pressure_scale_completed",
        passed,
        {
            "execute": physical_pressure.get("execute"),
            "failed": physical_pressure.get("failed"),
            "scale": physical_pressure.get("scale"),
            "rows": summary.get("row_count"),
            "total_gib_written": summary.get("total_bytes_written", 0) / (1024**3),
            "hybrid_block_reduction_vs_dogi": comparison.get("hybrid_block_reduction_vs_dogi"),
            "stale_secret_blocks_avoided": comparison.get("stale_secret_blocks_avoided"),
        },
    )


def gate_physical_policy_zonefs_replay(physical_policy: dict) -> Gate:
    summary = physical_policy.get("summary", {})
    by_policy = summary.get("by_policy", {})
    dogi = by_policy.get("dogi-history", {})
    hybrid = by_policy.get("quasar-dogi-hybrid", {})
    quasar = by_policy.get("quasar", {})
    passed = (
        physical_policy.get("execute", False)
        and summary.get("failed_rows", 1) == 0
        and summary.get("row_count", 0) >= 20
        and hybrid.get("physical_resets", 0) > 0
        and quasar.get("physical_resets", 0) > 0
        and dogi.get("sim_stale_secret_blocks", 0) > 0
        and hybrid.get("sim_stale_secret_blocks", 1) == 0
        and hybrid.get("max_active_zone_files", 999) <= 13
    )
    return Gate(
        "physical_policy_zonefs_replay_completed",
        passed,
        {
            "execute": physical_policy.get("execute"),
            "rows": summary.get("row_count"),
            "failed_rows": summary.get("failed_rows"),
            "dogi_stale_secret_blocks": dogi.get("sim_stale_secret_blocks"),
            "hybrid_stale_secret_blocks": hybrid.get("sim_stale_secret_blocks"),
            "quasar_resets": quasar.get("physical_resets"),
            "hybrid_resets": hybrid.get("physical_resets"),
            "hybrid_max_active_zone_files": hybrid.get("max_active_zone_files"),
            "dogi_vs_hybrid": summary.get("dogi_vs_hybrid", {}),
        },
    )


def gate_physical_policy_dogi_zonefs_replay(physical_policy: dict) -> Gate:
    summary = physical_policy.get("summary", {})
    by_policy = summary.get("by_policy", {})
    dogi = by_policy.get("dogi-history", {})
    hybrid = by_policy.get("quasar-dogi-hybrid", {})
    quasar = by_policy.get("quasar", {})
    passed = (
        physical_policy.get("execute", False)
        and summary.get("failed_rows", 1) == 0
        and summary.get("row_count", 0) >= 30
        and physical_policy.get("zone_capacity", 0) >= 275_712
        and hybrid.get("physical_resets", 0) > 0
        and quasar.get("physical_resets", 0) > 0
        and dogi.get("sim_stale_secret_blocks", 0) > 0
        and hybrid.get("sim_stale_secret_blocks", 1) == 0
        and hybrid.get("max_open_zone_files", hybrid.get("max_active_zone_files", 999)) <= 13
        and hybrid.get("max_allocated_zone_files", 999) <= 13
    )
    return Gate(
        "physical_policy_dogi_zonefs_replay_completed",
        passed,
        {
            "execute": physical_policy.get("execute"),
            "rows": summary.get("row_count"),
            "failed_rows": summary.get("failed_rows"),
            "zone_capacity": physical_policy.get("zone_capacity"),
            "dogi_stale_secret_blocks": dogi.get("sim_stale_secret_blocks"),
            "hybrid_stale_secret_blocks": hybrid.get("sim_stale_secret_blocks"),
            "quasar_resets": quasar.get("physical_resets"),
            "hybrid_resets": hybrid.get("physical_resets"),
            "hybrid_max_open_zone_files": hybrid.get("max_open_zone_files", hybrid.get("max_active_zone_files")),
            "hybrid_max_allocated_zone_files": hybrid.get("max_allocated_zone_files"),
            "dogi_vs_hybrid": summary.get("dogi_vs_hybrid", {}),
        },
    )


def gate_packed_policy_replay_analysis(packed_analysis: dict) -> Gate:
    summary = packed_analysis.get("summary", {})
    rows = summary.get("by_policy_packing", {})
    any_hybrid = rows.get("quasar-dogi-hybrid::any", {})
    group_hybrid = rows.get("quasar-dogi-hybrid::group", {})
    logical_hybrid = rows.get("quasar-dogi-hybrid::logical-zone", {})
    physical_zones = packed_analysis.get("physical_zones", 0)
    passed = (
        summary.get("failed_rows", 1) == 0
        and summary.get("row_count", 0) >= 120
        and physical_zones >= 905
        and any_hybrid.get("secret_blocks_waiting_for_physical_reset", 0) > 0
        and any_hybrid.get("delayed_reset_ratio", 0.0) >= 1.0
        and group_hybrid.get("secret_blocks_waiting_for_physical_reset", 1) == 0
        and group_hybrid.get("max_live_physical_zones", 9999) <= 16
        and logical_hybrid.get("secret_blocks_waiting_for_physical_reset", 1) == 0
        and logical_hybrid.get("delayed_reset_ratio", 1.0) == 0.0
        and logical_hybrid.get("max_live_physical_zones", 0) > group_hybrid.get("max_live_physical_zones", 0)
    )
    return Gate(
        "packed_logical_zone_replay_analysis_completed",
        passed,
        {
            "rows": summary.get("row_count"),
            "failed_rows": summary.get("failed_rows"),
            "physical_zones": physical_zones,
            "physical_zone_capacity": packed_analysis.get("physical_zone_capacity"),
            "logical_zone_capacity": packed_analysis.get("logical_zone_capacity"),
            "any_secret_waiting_end": any_hybrid.get("secret_blocks_waiting_for_physical_reset"),
            "any_delayed_reset_ratio": any_hybrid.get("delayed_reset_ratio"),
            "group_secret_waiting_end": group_hybrid.get("secret_blocks_waiting_for_physical_reset"),
            "group_max_live_physical_zones": group_hybrid.get("max_live_physical_zones"),
            "group_max_secret_waiting": group_hybrid.get("max_secret_blocks_waiting_for_physical_reset"),
            "logical_zone_max_live_physical_zones": logical_hybrid.get("max_live_physical_zones"),
            "logical_zone_delayed_reset_ratio": logical_hybrid.get("delayed_reset_ratio"),
        },
    )


def gate_packed_physical_zonefs_replay(packed_physical: dict) -> Gate:
    summary = packed_physical.get("summary", {})
    rows = summary.get("by_policy_packing", {})
    group_hybrid = rows.get("quasar-dogi-hybrid::group", {})
    secret_group_hybrid = rows.get("quasar-dogi-hybrid::secret-group", {})
    required_baselines = ["fifo", "sepbit-style", "midas-style", "dogi-history"]
    baseline_evidence = {
        policy: {
            "group_stale": rows.get(f"{policy}::group", {}).get("sim_stale_secret_blocks"),
            "secret_group_stale": rows.get(f"{policy}::secret-group", {}).get("sim_stale_secret_blocks"),
            "group_resets": rows.get(f"{policy}::group", {}).get("physical_reset_commands"),
            "secret_group_resets": rows.get(f"{policy}::secret-group", {}).get("physical_reset_commands"),
        }
        for policy in required_baselines
    }
    baselines_present = all(
        f"{policy}::group" in rows and f"{policy}::secret-group" in rows
        for policy in required_baselines
    )
    baselines_leave_stale = all(
        rows.get(f"{policy}::group", {}).get("sim_stale_secret_blocks", 0) > 0
        and rows.get(f"{policy}::secret-group", {}).get("sim_stale_secret_blocks", 0) > 0
        and rows.get(f"{policy}::group", {}).get("physical_reset_commands", 1) == 0
        and rows.get(f"{policy}::secret-group", {}).get("physical_reset_commands", 1) == 0
        for policy in required_baselines
    )
    passed = (
        packed_physical.get("execute", False)
        and summary.get("failed_rows", 1) == 0
        and summary.get("row_count", 0) >= 72
        and packed_physical.get("physical_zone_capacity", 0) >= 275_712
        and baselines_present
        and baselines_leave_stale
        and group_hybrid.get("physical_reset_commands", 0) > 0
        and group_hybrid.get("secret_blocks_waiting_for_physical_reset", 1) == 0
        and group_hybrid.get("max_live_physical_zones", 9999) <= 16
        and secret_group_hybrid.get("physical_reset_commands", 0) > 0
        and secret_group_hybrid.get("secret_blocks_waiting_for_physical_reset", 1) == 0
        and secret_group_hybrid.get("max_secret_blocks_waiting_for_physical_reset", 9999)
        <= group_hybrid.get("max_secret_blocks_waiting_for_physical_reset", 0)
        and secret_group_hybrid.get("max_live_physical_zones", 9999)
        < group_hybrid.get("max_live_physical_zones", 0)
        and secret_group_hybrid.get("avg_space_utilization", 0.0)
        > group_hybrid.get("avg_space_utilization", 1.0)
        and secret_group_hybrid.get("avg_space_utilization", 0.0) >= 0.5
    )
    return Gate(
        "packed_physical_zonefs_replay_completed",
        passed,
        {
            "execute": packed_physical.get("execute"),
            "rows": summary.get("row_count"),
            "failed_rows": summary.get("failed_rows"),
            "wall_time_s": summary.get("wall_time_s"),
            "append_engine": packed_physical.get("append_engine"),
            "helper_chunk_blocks": packed_physical.get("helper_chunk_blocks"),
            "physical_zone_capacity": packed_physical.get("physical_zone_capacity"),
            "group_physical_resets": group_hybrid.get("physical_reset_commands"),
            "group_secret_waiting_end": group_hybrid.get("secret_blocks_waiting_for_physical_reset"),
            "group_max_live_physical_zones": group_hybrid.get("max_live_physical_zones"),
            "group_max_secret_waiting": group_hybrid.get("max_secret_blocks_waiting_for_physical_reset"),
            "group_avg_utilization": group_hybrid.get("avg_space_utilization"),
            "secret_group_physical_resets": secret_group_hybrid.get("physical_reset_commands"),
            "secret_group_secret_waiting_end": secret_group_hybrid.get("secret_blocks_waiting_for_physical_reset"),
            "secret_group_max_live_physical_zones": secret_group_hybrid.get("max_live_physical_zones"),
            "secret_group_max_secret_waiting": secret_group_hybrid.get("max_secret_blocks_waiting_for_physical_reset"),
            "secret_group_avg_utilization": secret_group_hybrid.get("avg_space_utilization"),
            "baseline_evidence": baseline_evidence,
        },
    )


def gate_dogi_nullblk_preflight(dogi_nullblk_preflight: dict) -> Gate:
    passed = (
        dogi_nullblk_preflight.get("can_configure_build", False)
        and dogi_nullblk_preflight.get("can_run_full_prototype", False)
        and str(dogi_nullblk_preflight.get("device", "")).startswith("/dev/nullb")
        and dogi_nullblk_preflight.get("trace", {}).get("all_lines_usable", False)
    )
    return Gate(
        "dogi_nullblk_target_preflight_ready",
        passed,
        {
            "device": dogi_nullblk_preflight.get("device"),
            "can_configure_build": dogi_nullblk_preflight.get("can_configure_build"),
            "can_run_full_prototype": dogi_nullblk_preflight.get("can_run_full_prototype"),
            "trace_all_lines_usable": dogi_nullblk_preflight.get("trace", {}).get("all_lines_usable"),
        },
    )


def gate_dogi_real_nullblk_run(dogi_run: dict, dogi_adapter: dict) -> Gate:
    expected_trace = str(Path(dogi_adapter.get("dogi_trace", "")).resolve())
    observed_trace = dogi_run.get("trace_path")
    passed = (
        dogi_run.get("completed", False)
        and dogi_run.get("saw_zenfs_mount", False)
        and dogi_run.get("saw_dogi_select", False)
        and dogi_run.get("user_write_gib", 0) > 0
        and dogi_run.get("gc_write_gib", 0) > 0
        and dogi_run.get("waf", 0) > 1.0
        and (not observed_trace or observed_trace == expected_trace)
    )
    return Gate(
        "external_dogi_real_nullblk_run_completed",
        passed,
        {
            "trace_path": observed_trace,
            "expected_trace_path": expected_trace,
            "completed": dogi_run.get("completed"),
            "zenfs_free_mb": dogi_run.get("zenfs_free_mb"),
            "user_write_gib": dogi_run.get("user_write_gib"),
            "gc_write_gib": dogi_run.get("gc_write_gib"),
            "waf": dogi_run.get("waf"),
            "saw_zenfs_mount": dogi_run.get("saw_zenfs_mount"),
            "saw_dogi_select": dogi_run.get("saw_dogi_select"),
        },
    )


def gate_dogi_physical_compact_run(dogi_physical_run: dict) -> Gate:
    passed = (
        dogi_physical_run.get("completed", False)
        and dogi_physical_run.get("saw_zenfs_mount", False)
        and dogi_physical_run.get("saw_dogi_select", False)
        and dogi_physical_run.get("selection_algorithm") == "DogiSelect"
        and dogi_physical_run.get("waf", 0) > 1.0
        and dogi_physical_run.get("user_write_gib", 0) > 0
        and dogi_physical_run.get("gc_write_gib", 0) > 0
    )
    return Gate(
        "external_dogi_physical_compact_run_completed",
        passed,
        {
            "completed": dogi_physical_run.get("completed"),
            "trace_path": dogi_physical_run.get("trace_path"),
            "placement_name": dogi_physical_run.get("placement_name"),
            "selection_algorithm": dogi_physical_run.get("selection_algorithm"),
            "saw_zenfs_mount": dogi_physical_run.get("saw_zenfs_mount"),
            "saw_dogi_select": dogi_physical_run.get("saw_dogi_select"),
            "waf": dogi_physical_run.get("waf"),
            "user_write_gib": dogi_physical_run.get("user_write_gib"),
            "gc_write_gib": dogi_physical_run.get("gc_write_gib"),
        },
    )


def gate_dogi_physical_full_suite(dogi_physical_suite: dict) -> Gate:
    rows = dogi_physical_suite.get("rows", [])
    passed = (
        dogi_physical_suite.get("completed", False)
        and dogi_physical_suite.get("workloads", 0) >= 6
        and dogi_physical_suite.get("aggregate_waf", 0) > 1.0
        and dogi_physical_suite.get("total_user_write_gib", 0) > 0
        and dogi_physical_suite.get("total_gc_write_gib", 0) > 0
        and all(row.get("completed", False) and row.get("selection_algorithm") == "DogiSelect" for row in rows)
    )
    return Gate(
        "external_dogi_physical_full_compact_suite_completed",
        passed,
        {
            "completed": dogi_physical_suite.get("completed"),
            "workloads": dogi_physical_suite.get("workloads"),
            "logical_size_gb": dogi_physical_suite.get("logical_size_gb"),
            "aggregate_waf": dogi_physical_suite.get("aggregate_waf"),
            "avg_waf": dogi_physical_suite.get("avg_waf"),
            "total_user_write_gib": dogi_physical_suite.get("total_user_write_gib"),
            "total_gc_write_gib": dogi_physical_suite.get("total_gc_write_gib"),
        },
    )


def gate_dogi_physical_pressure_suite(dogi_pressure_suite: dict) -> Gate:
    rows = dogi_pressure_suite.get("rows", [])
    placements = {row.get("placement") for row in rows}
    completed_rows = [row for row in rows if row.get("completed")]
    passed = (
        dogi_pressure_suite.get("completed_runs", 0) == dogi_pressure_suite.get("total_runs", -1)
        and dogi_pressure_suite.get("total_runs", 0) >= 3
        and {"DOGI", "Greedy", "CostBenefit"}.issubset(placements)
        and dogi_pressure_suite.get("dogi_waf", 0) > 1.0
        and dogi_pressure_suite.get("best_waf", 0) > 1.0
        and all(row.get("saw_zenfs_mount", False) and row.get("waf", 0) > 1.0 for row in completed_rows)
    )
    return Gate(
        "external_dogi_physical_dynamic_pressure_suite_completed",
        passed,
        {
            "completed_runs": dogi_pressure_suite.get("completed_runs"),
            "total_runs": dogi_pressure_suite.get("total_runs"),
            "device": dogi_pressure_suite.get("device"),
            "logical_size_gb": dogi_pressure_suite.get("logical_size_gb"),
            "scheduler": dogi_pressure_suite.get("scheduler"),
            "placements": sorted(placement for placement in placements if placement),
            "dogi_waf": dogi_pressure_suite.get("dogi_waf"),
            "best_placement": dogi_pressure_suite.get("best_placement"),
            "best_waf": dogi_pressure_suite.get("best_waf"),
        },
    )


def gate_midas_exact_repeat4(midas_repeat: dict) -> Gate:
    adapter = midas_repeat.get("adapter_summary", {})
    progress_reports = midas_repeat.get("progress_reports", [])
    total_waf = midas_repeat.get("total_waf", midas_repeat.get("recomputed_waf_from_dataw_gcdw", 0.0))
    counters = midas_repeat.get("counters", {})
    passed = (
        midas_repeat.get("completed", False)
        and midas_repeat.get("returncode", 1) == 0
        and adapter.get("compact_lba", False)
        and adapter.get("dogi_lines", 0) >= 1_000_000
        and adapter.get("dogi_tombstones", 0) > 0
        and adapter.get("user_write_bytes", 0) >= 3 * 1024 * 1024 * 1024
        and len(progress_reports) >= 6
        and total_waf >= 1.0
        and counters.get("dataw", 0) > 0
    )
    return Gate(
        "external_midas_exact_repeat4_compact_completed",
        passed,
        {
            "completed": midas_repeat.get("completed"),
            "returncode": midas_repeat.get("returncode"),
            "total_waf": total_waf,
            "recomputed_waf_from_dataw_gcdw": midas_repeat.get("recomputed_waf_from_dataw_gcdw"),
            "runtime_seconds": midas_repeat.get("runtime_seconds"),
            "dogi_lines": adapter.get("dogi_lines"),
            "dogi_tombstones": adapter.get("dogi_tombstones"),
            "compact_lba": adapter.get("compact_lba"),
            "compact_span_blocks": adapter.get("compact_span_blocks"),
            "user_write_gib": adapter.get("user_write_bytes", 0) / (1024**3),
            "dataw": counters.get("dataw"),
            "gcdw": counters.get("gcdw"),
            "progress_reports": len(progress_reports),
        },
    )


def gate_sepbit_exact_repeat4(sepbit_repeat: dict, nosep_repeat: dict) -> Gate:
    sepbit_summary = sepbit_repeat.get("summary", {})
    nosep_summary = nosep_repeat.get("summary", {})
    adapter = sepbit_repeat.get("adapter_summary", {})
    sepbit_wa = sepbit_summary.get("wa", 0.0)
    nosep_wa = nosep_summary.get("wa", 0.0)
    passed = (
        sepbit_repeat.get("completed", False)
        and nosep_repeat.get("completed", False)
        and sepbit_repeat.get("returncode", 1) == 0
        and nosep_repeat.get("returncode", 1) == 0
        and adapter.get("compact_lba", False)
        and sepbit_summary.get("requests", 0) >= 1_000_000
        and adapter.get("tombstones", 0) > 0
        and sepbit_summary.get("ngc", 0) > 0
        and nosep_summary.get("ngc", 0) > 0
        and sepbit_wa > 1.0
        and nosep_wa > sepbit_wa
    )
    return Gate(
        "external_sepbit_exact_repeat4_compact_completed",
        passed,
        {
            "sepbit_completed": sepbit_repeat.get("completed"),
            "nosep_completed": nosep_repeat.get("completed"),
            "sepbit_returncode": sepbit_repeat.get("returncode"),
            "nosep_returncode": nosep_repeat.get("returncode"),
            "sepbit_wa": sepbit_wa,
            "nosep_wa": nosep_wa,
            "sepbit_ngc": sepbit_summary.get("ngc"),
            "nosep_ngc": nosep_summary.get("ngc"),
            "requests": sepbit_summary.get("requests"),
            "tombstones": adapter.get("tombstones"),
            "compact_lba": adapter.get("compact_lba"),
            "compact_span_blocks": adapter.get("compact_span_blocks"),
            "sepbit_runtime_seconds": sepbit_summary.get("runtime_seconds"),
            "nosep_runtime_seconds": nosep_summary.get("runtime_seconds"),
        },
    )


def gate_nullblk_path(nullblk_plan: dict, nullblk_preflight: dict) -> Gate:
    commands = "\n".join(nullblk_plan.get("create_commands", []))
    passed = (
        "modprobe null_blk configfs=1" in commands
        and "/zoned" in commands
        and "/zone_size" in commands
        and "/power" in commands
        and bool(nullblk_preflight.get("configfs_parent_exists"))
        and "null_blk_module_available" in nullblk_preflight
    )
    return Gate(
        "nullblk_zoned_setup_path_recorded",
        passed,
        {
            "create_command_count": len(nullblk_plan.get("create_commands", [])),
            "configfs_parent_exists": nullblk_preflight.get("configfs_parent_exists"),
            "null_blk_module_available": nullblk_preflight.get("null_blk_module_available"),
            "can_create_without_sudo": nullblk_preflight.get("can_create_without_sudo"),
        },
    )


def gate_figures(figures_dir: Path) -> Gate:
    required = [
        "e1-waf.png",
        "e2-waf-vs-utilization.png",
        "e3-service-cost.png",
        "e4-exposure.png",
        "e4-exposure-timeline.png",
        "e5-bad-hints.png",
        "actual-zns/ycsb-pressure-waf-stale.png",
        "actual-zns/overhead-accounting.png",
        "actual-zns/workload-hardness.png",
    ]
    status = {}
    for name in required:
        path = figures_dir / name
        status[name] = {"exists": path.exists(), "bytes": path.stat().st_size if path.exists() else 0}
    passed = all(item["exists"] and item["bytes"] > 0 for item in status.values())
    return Gate("all_major_figures_exist", passed, status)


def gate_c_policy_overhead(c_policy_overhead: dict) -> Gate:
    aggregate = c_policy_overhead.get("aggregate", {})
    rows = c_policy_overhead.get("rows", [])
    dogi = aggregate.get("dogi-mlp", {})
    quasar = aggregate.get("quasar-hint", {})
    hybrid = aggregate.get("quasar-dogi-hybrid", {})
    passed = (
        bool(rows)
        and dogi.get("traces", 0) >= 1
        and quasar.get("traces", 0) >= 1
        and hybrid.get("traces", 0) >= 1
        and dogi.get("median_ns_per_write", 0) > 0
        and quasar.get("median_ns_per_write", 0) > 0
        and hybrid.get("median_ns_per_write", 0) > 0
        and quasar.get("median_ns_per_write", 999999999) < dogi.get("median_ns_per_write", 0)
    )
    return Gate(
        "c_policy_cpu_overhead_measured",
        passed,
        {
            "rows": len(rows),
            "dogi_mlp_median_ns_per_write": dogi.get("median_ns_per_write"),
            "quasar_hint_median_ns_per_write": quasar.get("median_ns_per_write"),
            "hybrid_median_ns_per_write": hybrid.get("median_ns_per_write"),
            "dogi_traces": dogi.get("traces"),
            "quasar_traces": quasar.get("traces"),
            "hybrid_traces": hybrid.get("traces"),
        },
    )


def gate_crash_recovery_cost(crash_model: dict) -> Gate:
    summary = crash_model.get("summary", {})
    cost = crash_model.get("metadata_cost", {})
    meta = cost.get("metadata_bytes", {})
    scan = cost.get("recovery_scan", {})
    passed = (
        summary.get("failed_cases") == 0
        and not summary.get("unsafe_reset_attempted", True)
        and meta.get("total", 0) > 0
        and cost.get("metadata_overhead_percent_of_user_bytes", 0) > 0
        and scan.get("estimated_scan_zones", 0) > 0
    )
    return Gate(
        "crash_recovery_cost_measured",
        passed,
        {
            "passed_cases": summary.get("passed_cases"),
            "cases": summary.get("cases"),
            "unsafe_reset_attempted": summary.get("unsafe_reset_attempted"),
            "metadata_bytes_total": meta.get("total"),
            "metadata_overhead_percent": cost.get("metadata_overhead_percent_of_user_bytes"),
            "estimated_recovery_scan_ms": scan.get("estimated_scan_ms"),
        },
    )


def gate_fdp_mapping(fdp_mapping: dict) -> Gate:
    runs = fdp_mapping.get("runs", [])
    best = max(runs, key=lambda row: row.get("handles", 0), default={})
    passed = (
        bool(runs)
        and best.get("handles", 0) >= 64
        and best.get("family_count", 0) > 0
        and best.get("occupied_handles", 0) > 0
        and best.get("family_purity", 0) >= 0.90
        and best.get("intent_purity", 0) >= 0.90
    )
    return Gate(
        "fdp_mapping_model_generated",
        passed,
        {
            "runs": len(runs),
            "best_handles": best.get("handles"),
            "family_count": best.get("family_count"),
            "occupied_handles": best.get("occupied_handles"),
            "family_purity": best.get("family_purity"),
            "intent_purity": best.get("intent_purity"),
        },
    )


def gate_fast_db_pressure(fast_db: dict) -> Gate:
    physical = fast_db.get("physical", {})
    rows = physical.get("by_policy_packing", {})
    dogi = rows.get("dogi-history::secret-group", {})
    hybrid = rows.get("quasar-dogi-hybrid::secret-group", {})
    comparison = physical.get("hybrid_vs_dogi_secret_group", {})
    passed = (
        physical.get("rows", 0) >= 24
        and physical.get("failed_rows", 1) == 0
        and physical.get("total_physical_gib", 0.0) >= 20.0
        and dogi.get("sim_stale_secret_blocks", 0) > 0
        and dogi.get("physical_reset_commands", 1) == 0
        and hybrid.get("sim_stale_secret_blocks", 1) == 0
        and hybrid.get("secret_blocks_waiting_for_physical_reset", 1) == 0
        and hybrid.get("physical_reset_commands", 0) > 0
        and hybrid.get("sim_gc_blocks", 999999999) < dogi.get("sim_gc_blocks", 0)
        and comparison.get("gc_reduction", 0.0) >= 0.90
    )
    return Gate(
        "fast_db_pressure_physical_replay_completed",
        passed,
        {
            "rows": physical.get("rows"),
            "failed_rows": physical.get("failed_rows"),
            "total_physical_gib": physical.get("total_physical_gib"),
            "dogi_waf": dogi.get("sim_waf"),
            "hybrid_waf": hybrid.get("sim_waf"),
            "dogi_gc_blocks": dogi.get("sim_gc_blocks"),
            "hybrid_gc_blocks": hybrid.get("sim_gc_blocks"),
            "gc_reduction": comparison.get("gc_reduction"),
            "dogi_stale_secret_blocks": dogi.get("sim_stale_secret_blocks"),
            "hybrid_stale_secret_blocks": hybrid.get("sim_stale_secret_blocks"),
            "hybrid_physical_resets": hybrid.get("physical_reset_commands"),
            "hybrid_secret_waiting_end": hybrid.get("secret_blocks_waiting_for_physical_reset"),
        },
    )


def gate_fast_ycsb_pressure(fast_ycsb: dict, ycsb_pressure_curve: dict, ycsb_f_straggler_baselines: dict) -> Gate:
    simulator = fast_ycsb.get("simulator", {})
    physical = fast_ycsb.get("physical", {})
    sim_workloads = {}
    for workload, item in simulator.items():
        policies = item.get("policies", {})
        dogi = policies.get("dogi-history", {})
        hybrid = policies.get("quasar-dogi-hybrid", {})
        sim_workloads[workload] = {
            "dogi_waf": dogi.get("waf"),
            "hybrid_waf": hybrid.get("waf"),
            "dogi_gc_blocks": dogi.get("gc_write_blocks"),
            "hybrid_gc_blocks": hybrid.get("gc_write_blocks"),
            "dogi_stale_secret_blocks": dogi.get("stale_secret_blocks_remaining"),
            "hybrid_stale_secret_blocks": hybrid.get("stale_secret_blocks_remaining"),
        }
    physical_status = {}
    physical_ok = True
    physical_waf_pressure_workloads = []
    for workload, item in physical.items():
        by_policy = item.get("by_policy", {})
        dogi = by_policy.get("dogi-history", {})
        hybrid = by_policy.get("quasar-dogi-hybrid", {})
        pressure_ok = (
            hybrid.get("sim_gc_blocks", 999999999) < dogi.get("sim_gc_blocks", 0)
            and (dogi.get("sim_waf") or 0.0) > (hybrid.get("sim_waf") or 0.0)
        )
        ok = (
            item.get("rows", 0) >= 6
            and item.get("failed_rows", 1) == 0
            and item.get("total_physical_gib", 0.0) > 0.0
            and dogi.get("sim_stale_secret_blocks", 0) > 0
            and dogi.get("physical_reset_commands", 1) == 0
            and hybrid.get("sim_stale_secret_blocks", 1) == 0
            and hybrid.get("secret_blocks_waiting_for_physical_reset", 1) == 0
            and hybrid.get("physical_reset_commands", 0) > 0
        )
        if pressure_ok:
            physical_waf_pressure_workloads.append(workload)
        physical_ok = physical_ok and ok
        physical_status[workload] = {
            "ok": ok,
            "pressure_ok": pressure_ok,
            "rows": item.get("rows"),
            "failed_rows": item.get("failed_rows"),
            "logical_zones": item.get("logical_zones"),
            "total_physical_gib": item.get("total_physical_gib"),
            "dogi_waf": dogi.get("sim_waf"),
            "hybrid_waf": hybrid.get("sim_waf"),
            "dogi_gc_blocks": dogi.get("sim_gc_blocks"),
            "hybrid_gc_blocks": hybrid.get("sim_gc_blocks"),
            "dogi_stale_secret_blocks": dogi.get("sim_stale_secret_blocks"),
            "hybrid_stale_secret_blocks": hybrid.get("sim_stale_secret_blocks"),
            "hybrid_physical_resets": hybrid.get("physical_reset_commands"),
        }
    waf_pressure_workloads = [
        workload
        for workload, row in sim_workloads.items()
        if (row.get("dogi_gc_blocks") or 0) > (row.get("hybrid_gc_blocks") or 0)
        and (row.get("dogi_waf") or 0.0) > (row.get("hybrid_waf") or 0.0)
    ]
    passed = (
        len(simulator) >= 4
        and len(physical) >= 4
        and len(waf_pressure_workloads) >= 3
        and len(physical_waf_pressure_workloads) >= 3
        and all((row.get("dogi_stale_secret_blocks") or 0) > 0 for row in sim_workloads.values())
        and all(row.get("hybrid_stale_secret_blocks") == 0 for row in sim_workloads.values())
        and physical_ok
    )
    straggler_rows = ycsb_f_straggler_baselines.get("summary", {}).get("by_policy_packing", {})
    straggler_status = {}
    straggler_ok = True
    for key in [
        "fifo::secret-group",
        "sepbit-style::secret-group",
        "midas-style::secret-group",
        "dogi-history::secret-group",
    ]:
        row = straggler_rows.get(key, {})
        ok = (
            row.get("failed_rows") == 0
            and row.get("physical_reset_commands") == 0
            and row.get("sim_stale_secret_blocks", 0) > 0
            and row.get("secret_blocks_waiting_for_physical_reset", 0) > 0
            and row.get("physical_waf", 0.0) >= 1.0
        )
        straggler_ok = straggler_ok and ok
        straggler_status[key] = {
            "ok": ok,
            "physical_waf": row.get("physical_waf"),
            "stale_secret_blocks": row.get("sim_stale_secret_blocks"),
            "secret_waiting_end": row.get("secret_blocks_waiting_for_physical_reset"),
            "physical_resets": row.get("physical_reset_commands"),
            "max_live_physical_zones": row.get("max_live_physical_zones"),
            "failed_rows": row.get("failed_rows"),
        }
    curve_rows = ycsb_pressure_curve.get("rows", [])
    curve_has_negative_control = any(
        row.get("pqc_level") == 2000
        and row.get("dogi_gc_blocks") == 0
        and row.get("semantic_gap")
        for row in curve_rows
    )
    curve_ok = (
        ycsb_pressure_curve.get("failed_rows") == 0
        and ycsb_pressure_curve.get("row_count", 0) >= 5
        and ycsb_pressure_curve.get("semantic_gap_rows", 0) >= 5
        and ycsb_pressure_curve.get("waf_pressure_rows", 0) >= 3
        and curve_has_negative_control
    )
    passed = (
        passed
        and ycsb_f_straggler_baselines.get("summary", {}).get("failed_rows") == 0
        and straggler_ok
        and curve_ok
    )
    return Gate(
        "fast_ycsb_pressure_physical_replay_completed",
        passed,
        {
            "sim_workloads": sim_workloads,
            "waf_pressure_workloads": waf_pressure_workloads,
            "physical_waf_pressure_workloads": physical_waf_pressure_workloads,
            "physical": physical_status,
            "actual_zns_pressure_curve": {
                "row_count": ycsb_pressure_curve.get("row_count"),
                "failed_rows": ycsb_pressure_curve.get("failed_rows"),
                "semantic_gap_rows": ycsb_pressure_curve.get("semantic_gap_rows"),
                "waf_pressure_rows": ycsb_pressure_curve.get("waf_pressure_rows"),
                "has_p2000_negative_control": curve_has_negative_control,
            },
            "ycsb_f_straggler_baselines": straggler_status,
        },
    )


def gate_actual_zns_overhead(overhead: dict) -> Gate:
    by_policy = overhead.get("by_policy", {})
    dogi = by_policy.get("dogi-history", {})
    hybrid = by_policy.get("quasar-dogi-hybrid", {})
    quasar = by_policy.get("quasar", {})
    comparison = overhead.get("hybrid_vs_dogi", {})
    passed = (
        overhead.get("failed_rows") == 0
        and overhead.get("row_count", 0) >= 80
        and dogi.get("semantic_physical_reset_commands") == 0
        and hybrid.get("semantic_physical_reset_commands", 0) > 0
        and quasar.get("semantic_physical_reset_commands", 0) > 0
        and dogi.get("append_avg_ns", 0) > 0
        and hybrid.get("append_avg_ns", 0) > 0
        and dogi.get("throughput_mib_s", 0) > 0
        and hybrid.get("throughput_mib_s", 0) > 0
        and comparison.get("cpu_median_ns_ratio", 99) < 1.0
    )
    return Gate(
        "actual_zns_overhead_and_policy_cpu_reported",
        passed,
        {
            "rows": overhead.get("row_count"),
            "failed_rows": overhead.get("failed_rows"),
            "dogi_append_avg_ns": dogi.get("append_avg_ns"),
            "hybrid_append_avg_ns": hybrid.get("append_avg_ns"),
            "dogi_throughput_mib_s": dogi.get("throughput_mib_s"),
            "hybrid_throughput_mib_s": hybrid.get("throughput_mib_s"),
            "dogi_semantic_resets": dogi.get("semantic_physical_reset_commands"),
            "hybrid_semantic_resets": hybrid.get("semantic_physical_reset_commands"),
            "cpu_median_ns_ratio": comparison.get("cpu_median_ns_ratio"),
        },
    )


def gate_security_capability(security: dict) -> Gate:
    ops = security.get("sanitize_operations_supported", {})
    claim_boundary = str(security.get("claim_boundary", ""))
    passed = (
        bool(security.get("device_model"))
        and security.get("sanitize_supported") is True
        and ops.get("crypto_erase") is True
        and ops.get("block_erase") is True
        and "reset eligibility" in claim_boundary
        and "physical erase" in claim_boundary
    )
    return Gate(
        "physical_security_capability_and_erase_claim_boundary_recorded",
        passed,
        {
            "device_model": security.get("device_model"),
            "sanicap_hex": security.get("sanicap_hex"),
            "sanitize_supported": security.get("sanitize_supported"),
            "crypto_erase": ops.get("crypto_erase"),
            "block_erase": ops.get("block_erase"),
            "overwrite": ops.get("overwrite"),
            "sanitize_log_status": security.get("sanitize_log_status"),
            "crypto_erase_executed": security.get("crypto_erase_executed"),
            "sanitize_execution_validated": security.get("sanitize_execution_validated"),
            "claim_boundary": claim_boundary,
        },
    )


def gate_claim_matrix(claim_matrix: dict) -> Gate:
    by_status = claim_matrix.get("by_status", {})
    claims = claim_matrix.get("claims", [])
    forbidden_text = "\n".join(claim.get("caveat", "") + "\n" + claim.get("paper_wording", "") for claim in claims)
    has_boundary_or_validated_sanitize = by_status.get("supported-boundary", 0) >= 1 or any(
        "crypto-erase" in claim.get("paper_wording", "") and "completed successfully" in claim.get("paper_wording", "")
        for claim in claims
    )
    passed = (
        claim_matrix.get("claim_count", 0) >= 8
        and by_status.get("supported", 0) >= 6
        and has_boundary_or_validated_sanitize
        and by_status.get("qualified", 0) >= 1
        and any("WAF" in claim.get("caveat", "") for claim in claims)
        and any("physical erase" in claim.get("caveat", "") for claim in claims)
        and "External DOGI/MiDAS/SepBIT" in forbidden_text
    )
    return Gate(
        "claim_matrix_maps_supported_qualified_and_boundary_claims",
        passed,
        {
            "claim_count": claim_matrix.get("claim_count"),
            "by_status": by_status,
        },
    )


def gate_workload_hardness_matrix(workload_hardness: dict) -> Gate:
    entries = workload_hardness.get("entries", [])
    by_tier = workload_hardness.get("by_tier", {})
    required_tiers = {"fairness", "negative-control", "pressure", "claim-gate", "hostile-robustness"}
    observed_tiers = {entry.get("tier") for entry in entries}
    failed_entries = [entry.get("name") for entry in entries if not entry.get("passed")]
    claim_gate = next((entry for entry in entries if entry.get("tier") == "claim-gate"), {})
    claim_evidence = claim_gate.get("evidence", {})
    claim_gate_passed = bool(
        claim_gate.get("passed")
        and claim_evidence.get("eligible_ycsb_pressure_rows", 0) >= 3
        and claim_evidence.get("ycsb_baseline_complete_rows", 0) >= 3
        and claim_evidence.get("db_pressure_eligible") is True
        and claim_evidence.get("eligible_dynamic_rows", 0) >= 2
        and claim_evidence.get("dynamic_baseline_complete_rows", 0) >= 2
    )
    passed = (
        workload_hardness.get("passed", False)
        and workload_hardness.get("passed_entries", 0) == workload_hardness.get("total_entries", -1)
        and workload_hardness.get("total_entries", 0) >= 9
        and required_tiers.issubset(observed_tiers)
        and by_tier.get("pressure", {}).get("passed", 0) >= 2
        and by_tier.get("claim-gate", {}).get("passed", 0) >= 1
        and by_tier.get("hostile-robustness", {}).get("passed", 0) >= 3
        and claim_gate_passed
    )
    return Gate(
        "workload_hardness_matrix_separates_negative_pressure_and_hostile_cases",
        passed,
        {
            "passed_entries": workload_hardness.get("passed_entries"),
            "total_entries": workload_hardness.get("total_entries"),
            "by_tier": by_tier,
            "failed_entries": failed_entries,
            "observed_tiers": sorted(tier for tier in observed_tiers if tier),
            "claim_gate_passed": claim_gate_passed,
            "claim_gate_evidence": claim_evidence,
        },
    )


def gate_deployment_policy_selector(selector: dict) -> Gate:
    modes = selector.get("modes", [])
    mode_names = {mode.get("mode") for mode in modes}
    required = {"default", "tenant-isolation", "strict-residual", "fallback-overflow"}
    failed_modes = [mode.get("mode") for mode in modes if not mode.get("passed")]
    passed = (
        selector.get("passed", False)
        and selector.get("passed_modes", 0) == selector.get("total_modes", -1)
        and selector.get("total_modes", 0) >= 4
        and selector.get("default_policy") == "quasar-dogi-hybrid"
        and required.issubset(mode_names)
        and selector.get("hardness_passed", False)
    )
    return Gate(
        "deployment_policy_selector_defines_default_tenant_residual_and_fallback_modes",
        passed,
        {
            "passed_modes": selector.get("passed_modes"),
            "total_modes": selector.get("total_modes"),
            "default_policy": selector.get("default_policy"),
            "hardness_passed": selector.get("hardness_passed"),
            "failed_modes": failed_modes,
            "mode_names": sorted(mode for mode in mode_names if mode),
        },
    )


def gate_reproducibility_manifest(manifest: dict) -> Gate:
    required_ids = {
        "same_path_actual_zns_fairness",
        "ycsb_actual_zns_pressure_curve",
        "ycsb_actual_zns_p2000_raw",
        "ycsb_actual_zns_a_p4000_raw",
        "ycsb_actual_zns_a_p6000_raw",
        "ycsb_actual_zns_a_p8000_raw",
        "ycsb_actual_zns_f_p4000_raw",
        "ycsb_actual_zns_f_p6000_raw",
        "ycsb_actual_zns_f_p8000_raw",
        "sysbench_actual_zns_pressure",
        "dynamic_exchange_actual_zns_pressure",
        "dynamic_exchange_actual_zns_raw",
        "dynamic_varmail_actual_zns_raw",
        "dynamic_alibaba_actual_zns_raw",
        "dogi_exact_alibaba_pressure",
        "dogi_exact_alibaba_suite",
        "actual_zns_overhead",
        "workload_hardness",
        "deployment_selector",
        "unified_comparison",
        "claim_matrix",
        "external_readiness",
        "acceptance",
    }
    artifact_ids = {item.get("id") for item in manifest.get("artifacts", [])}
    missing_required = sorted(required_ids - artifact_ids)
    missing_or_empty = manifest.get("missing_or_empty", [])
    commands = manifest.get("commands", [])
    passed = (
        manifest.get("passed", False)
        and manifest.get("artifact_count", 0) >= 14
        and not missing_or_empty
        and not missing_required
        and len(commands) >= 8
        and all(item.get("sha256") for item in manifest.get("artifacts", []))
    )
    return Gate(
        "reproducibility_manifest_covers_actual_zns_baselines_claims_and_commands",
        passed,
        {
            "artifact_count": manifest.get("artifact_count"),
            "missing_or_empty": missing_or_empty,
            "missing_required": missing_required,
            "command_count": len(commands),
        },
    )


def gate_reproducibility_validation(validation: dict) -> Gate:
    passed = (
        validation.get("passed", False)
        and validation.get("artifact_count", 0) >= 14
        and validation.get("mismatch_count", -1) == 0
        and not validation.get("mismatches", [])
    )
    return Gate(
        "reproducibility_manifest_hashes_match_current_artifacts",
        passed,
        {
            "artifact_count": validation.get("artifact_count"),
            "mismatch_count": validation.get("mismatch_count"),
            "mismatches": [
                {"id": row.get("id"), "path": row.get("path")}
                for row in validation.get("mismatches", [])
            ],
        },
    )


def gate_adaptive_policy_comparison(adaptive_comparison: dict) -> Gate:
    ycsb = adaptive_comparison.get("ycsb_pressure", {})
    sysbench = adaptive_comparison.get("sysbench_pressure", {})
    total_adaptive_wins = int(ycsb.get("adaptive_wins", 0)) + int(sysbench.get("adaptive_wins", 0))
    total_current_wins = int(ycsb.get("current_wins", 0)) + int(sysbench.get("current_wins", 0))
    passed = (
        adaptive_comparison.get("decision") == "keep-current-hybrid"
        and adaptive_comparison.get("default_policy") == "quasar-dogi-hybrid"
        and adaptive_comparison.get("candidate_policy") == "quasar-adaptive-hybrid"
        and total_current_wins >= 6
        and total_adaptive_wins == 0
        and len(ycsb.get("workloads", {})) >= 4
        and len(sysbench.get("workloads", {})) >= 2
    )
    return Gate(
        "adaptive_policy_comparison_keeps_current_hybrid",
        passed,
        {
            "decision": adaptive_comparison.get("decision"),
            "default_policy": adaptive_comparison.get("default_policy"),
            "candidate_policy": adaptive_comparison.get("candidate_policy"),
            "ycsb_current_wins": ycsb.get("current_wins"),
            "ycsb_adaptive_wins": ycsb.get("adaptive_wins"),
            "sysbench_current_wins": sysbench.get("current_wins"),
            "sysbench_adaptive_wins": sysbench.get("adaptive_wins"),
        },
    )


def gate_multitenant_pressure(multitenant: dict) -> Gate:
    simulator = multitenant.get("simulator", {})
    physical = multitenant.get("physical", {})
    physical_rows = physical.get("by_policy", {})
    current = physical_rows.get("quasar-dogi-hybrid", {})
    tenant_mode = physical_rows.get("quasar-adaptive-hybrid", {})
    dogi = physical_rows.get("dogi-history", {})
    comparison = physical.get("tenant_isolation_vs_current", {})
    sim_ok = True
    sim_status = {}
    for workload, item in simulator.items():
        current_sim = item.get("current", {})
        tenant_sim = item.get("tenant_isolation", {})
        ok = (
            current_sim.get("stale_secret_blocks_remaining", 1) == 0
            and tenant_sim.get("stale_secret_blocks_remaining", 1) == 0
            and current_sim.get("reset_secret_tenant_impurity", 0.0) > 0.5
            and tenant_sim.get("reset_secret_tenant_impurity", 1.0) == 0.0
        )
        sim_ok = sim_ok and ok
        sim_status[workload] = {
            "ok": ok,
            "current_waf": current_sim.get("waf"),
            "tenant_mode_waf": tenant_sim.get("waf"),
            "current_reset_secret_tenant_impurity": current_sim.get("reset_secret_tenant_impurity"),
            "tenant_mode_reset_secret_tenant_impurity": tenant_sim.get("reset_secret_tenant_impurity"),
            "current_families": current_sim.get("quasar_family_count"),
            "tenant_mode_families": tenant_sim.get("quasar_family_count"),
        }
    passed = (
        multitenant.get("decision") == "add-tenant-isolation-mode"
        and len(simulator) >= 2
        and sim_ok
        and physical.get("rows", 0) >= 7
        and physical.get("failed_rows", 1) == 0
        and dogi.get("sim_stale_secret_blocks", 0) > 0
        and current.get("sim_stale_secret_blocks", 1) == 0
        and tenant_mode.get("sim_stale_secret_blocks", 1) == 0
        and current.get("reset_secret_tenant_impurity", 0.0) > 0.5
        and tenant_mode.get("reset_secret_tenant_impurity", 1.0) == 0.0
        and tenant_mode.get("physical_reset_commands", 0) > current.get("physical_reset_commands", 0)
        and comparison.get("reset_secret_tenant_impurity_reduction", 0.0) >= 0.99
    )
    return Gate(
        "multitenant_tenant_isolation_mode_verified",
        passed,
        {
            "decision": multitenant.get("decision"),
            "simulator": sim_status,
            "physical_rows": physical.get("rows"),
            "physical_failed_rows": physical.get("failed_rows"),
            "dogi_stale_secret_blocks": dogi.get("sim_stale_secret_blocks"),
            "current_waf": current.get("sim_waf"),
            "tenant_mode_waf": tenant_mode.get("sim_waf"),
            "current_reset_secret_tenant_impurity": current.get("reset_secret_tenant_impurity"),
            "tenant_mode_reset_secret_tenant_impurity": tenant_mode.get("reset_secret_tenant_impurity"),
            "tenant_mode_physical_resets": tenant_mode.get("physical_reset_commands"),
            "current_physical_resets": current.get("physical_reset_commands"),
            "impurity_reduction": comparison.get("reset_secret_tenant_impurity_reduction"),
        },
    )


def gate_physical_robustness(robustness: dict) -> Gate:
    clean = robustness.get("clean", {})
    dogi_clean = clean.get("dogi", {})
    hybrid_clean = clean.get("hybrid", {})
    missing = robustness.get("missing_hint_5pct", {}).get("hybrid", {})
    wrong = robustness.get("wrong_epoch_5pct", {}).get("hybrid", {})
    straggler_exact = robustness.get("straggler_5pct_exact_secret_group", {})
    straggler_exact_hybrid = straggler_exact.get("hybrid", {})
    straggler_nobatch = robustness.get("straggler_5pct_exact_secret_group_nobatch", {})
    straggler_nobatch_hybrid = straggler_nobatch.get("hybrid", {})
    straggler_fallback = robustness.get("straggler_5pct_epoch_bin_4", {})
    straggler_fallback_hybrid = straggler_fallback.get("hybrid", {})
    straggler_residual = robustness.get("straggler_5pct_epoch_bin_5_residual_12288", {})
    straggler_residual_hybrid = straggler_residual.get("hybrid", {})
    limits = robustness.get("device_limits", {})
    mor = limits.get("mor")
    passed = (
        robustness.get("decision") == "add-open-zone-aware-residual-fallback"
        and clean.get("failed_rows") == 0
        and dogi_clean.get("sim_stale_secret_blocks", 0) > 0
        and hybrid_clean.get("sim_stale_secret_blocks", 1) == 0
        and hybrid_clean.get("physical_reset_commands", 0) > 0
        and robustness.get("missing_hint_5pct", {}).get("failed_rows") == 0
        and missing.get("sim_stale_secret_blocks", 0) > 0
        and robustness.get("wrong_epoch_5pct", {}).get("failed_rows") == 0
        and wrong.get("sim_stale_secret_blocks", 1) == 0
        and straggler_exact.get("failed_rows", 0) > 0
        and straggler_exact_hybrid.get("max_live_physical_zones", 0) > (mor or 0)
        and straggler_nobatch.get("failed_rows", 0) > 0
        and straggler_nobatch_hybrid.get("max_live_physical_zones", 0) > (mor or 0)
        and straggler_fallback.get("failed_rows") == 0
        and straggler_fallback_hybrid.get("max_live_physical_zones", 999999) <= (mor or 0)
        and straggler_fallback_hybrid.get("sim_stale_secret_blocks", 0) > 0
        and straggler_residual.get("failed_rows") == 0
        and straggler_residual_hybrid.get("max_live_physical_zones", 999999) <= (mor or 0)
        and straggler_residual_hybrid.get("secret_waiting_end", 1) == 0
        and straggler_residual_hybrid.get("physical_reset_commands", 0) > 0
        and straggler_residual_hybrid.get("residual_migrated_blocks", 0) > 0
    )
    return Gate(
        "physical_hint_robustness_and_open_zone_fallback_verified",
        passed,
        {
            "decision": robustness.get("decision"),
            "device_limits": limits,
            "clean_dogi_stale": dogi_clean.get("sim_stale_secret_blocks"),
            "clean_hybrid_stale": hybrid_clean.get("sim_stale_secret_blocks"),
            "missing_hybrid_stale": missing.get("sim_stale_secret_blocks"),
            "wrong_hybrid_stale": wrong.get("sim_stale_secret_blocks"),
            "straggler_secret_group_failed_rows": straggler_exact.get("failed_rows"),
            "straggler_secret_group_max_zones": straggler_exact_hybrid.get("max_live_physical_zones"),
            "straggler_nobatch_failed_rows": straggler_nobatch.get("failed_rows"),
            "straggler_nobatch_max_zones": straggler_nobatch_hybrid.get("max_live_physical_zones"),
            "straggler_epoch_bin_failed_rows": straggler_fallback.get("failed_rows"),
            "straggler_epoch_bin_max_zones": straggler_fallback_hybrid.get("max_live_physical_zones"),
            "straggler_epoch_bin_stale": straggler_fallback_hybrid.get("sim_stale_secret_blocks"),
            "straggler_residual_failed_rows": straggler_residual.get("failed_rows"),
            "straggler_residual_max_zones": straggler_residual_hybrid.get("max_live_physical_zones"),
            "straggler_residual_waiting_end": straggler_residual_hybrid.get("secret_waiting_end"),
            "straggler_residual_migrated_blocks": straggler_residual_hybrid.get("residual_migrated_blocks"),
        },
    )


def gate_residual_fallback_sweep(summary: dict) -> Gate:
    physical_rows = summary.get("physical_rows", [])
    physical_by_workload = {row.get("workload"): row for row in physical_rows}
    physical_by_profile = {
        (row.get("workload"), row.get("profile") or "representative"): row for row in physical_rows
    }
    candidates = summary.get("best_candidates", {})
    ycsb_f_zero = candidates.get("ycsb-f-pqc8000", {}).get("best_zero_wait", [])
    ycsb_f_best = ycsb_f_zero[0] if ycsb_f_zero else {}
    budget_rows = [
        row
        for row in summary.get("budget_rows", [])
        if row.get("workload") == "ycsb-f-pqc8000" and row.get("packing") == "epoch-bin-5"
    ]
    budget_physical_rows = [
        row
        for row in summary.get("budget_physical_rows", [])
        if row.get("workload") == "ycsb-f-pqc8000" and row.get("packing") == "epoch-bin-5"
    ]
    controller = {
        (row.get("workload"), row.get("profile")): row.get("selected") or {}
        for row in summary.get("controller_decisions", [])
    }
    required_physical = ["exchange-pqc2000", "sysbench-oltp-pqc4000", "ycsb-a-pqc4000"]
    mor = summary.get("device_limits", {}).get("mor")
    physical_ok = all(
        physical_by_workload.get(workload, {}).get("failed_rows") == 0
        and physical_by_workload.get(workload, {}).get("secret_waiting_end") == 0
        and physical_by_workload.get(workload, {}).get("max_live_physical_zones", 999999) <= (mor or 0)
        for workload in required_physical
    )
    ycsb_low_physical = physical_by_profile.get(("ycsb-f-pqc8000", "low_overhead"), {})
    ycsb_balanced_physical = physical_by_profile.get(("ycsb-f-pqc8000", "balanced"), {})
    ycsb_strict_physical = physical_by_profile.get(("ycsb-f-pqc8000", "strict_zero_wait"), {})
    ycsb_f_controller_physical_ok = (
        ycsb_low_physical.get("failed_rows") == 0
        and ycsb_low_physical.get("physical_waf", 99) <= 1.05
        and ycsb_low_physical.get("secret_waiting_end", 0) > 0
        and ycsb_balanced_physical.get("failed_rows") == 0
        and ycsb_balanced_physical.get("packing") == "epoch-bin-6"
        and ycsb_balanced_physical.get("physical_waf", 99) <= 1.50
        and ycsb_balanced_physical.get("secret_waiting_end", 10**18) <= 50_000
        and ycsb_balanced_physical.get("residual_migrated_blocks", 0) > 0
        and ycsb_balanced_physical.get("max_live_physical_zones", 999999) <= (mor or 0)
        and ycsb_strict_physical.get("failed_rows") == 0
        and ycsb_strict_physical.get("secret_waiting_end") == 0
        and ycsb_strict_physical.get("physical_waf", 0) >= 3.0
        and ycsb_strict_physical.get("residual_migrated_blocks", 0) > ycsb_balanced_physical.get(
            "residual_migrated_blocks", 0
        )
        and ycsb_strict_physical.get("max_live_physical_zones", 999999) <= (mor or 0)
    )
    budget_ok = (
        len(budget_rows) >= 4
        and any(row.get("physical_waf", 99) <= 1.15 and row.get("secret_waiting_end", 0) > 0 for row in budget_rows)
        and any(row.get("residual_migration_budget_skips", 0) > 0 for row in budget_rows)
        and all(row.get("max_live_physical_zones", 999999) <= (mor or 0) for row in budget_rows)
    )
    budget_physical_ok = (
        len(budget_physical_rows) >= 4
        and all(row.get("failed_rows") == 0 for row in budget_physical_rows)
        and all(row.get("max_live_physical_zones", 999999) <= (mor or 0) for row in budget_physical_rows)
        and any(
            row.get("physical_waf", 99) <= 1.15 and row.get("secret_waiting_end", 0) > 0
            for row in budget_physical_rows
        )
        and any(row.get("residual_migration_budget_skips", 0) > 0 for row in budget_physical_rows)
    )
    ycsb_low = controller.get(("ycsb-f-pqc8000", "low_overhead"), {})
    ycsb_balanced = controller.get(("ycsb-f-pqc8000", "balanced"), {})
    ycsb_strict = controller.get(("ycsb-f-pqc8000", "strict_zero_wait"), {})
    controller_ok = (
        len(summary.get("controller_decisions", [])) >= 9
        and ycsb_low.get("mode") == "no-residual-copy"
        and ycsb_low.get("physical_waf", 99) <= 1.05
        and ycsb_low.get("secret_waiting_end", 0) > 0
        and ycsb_balanced.get("physical_waf", 99) <= 1.50
        and ycsb_balanced.get("secret_waiting_end", 10**18) <= 50_000
        and ycsb_balanced.get("recommended_copy_budget", 0) > 0
        and ycsb_strict.get("mode") == "strict-zero-wait"
        and ycsb_strict.get("secret_waiting_end") == 0
        and ycsb_strict.get("physical_waf", 0) >= 3.0
    )
    passed = (
        summary.get("decision") == "use-residual-fallback-as-strict-exposure-mode"
        and len(summary.get("dryrun_rows", [])) >= 48
        and physical_ok
        and ycsb_f_controller_physical_ok
        and budget_ok
        and budget_physical_ok
        and controller_ok
        and physical_by_workload.get("exchange-pqc2000", {}).get("physical_waf", 99) <= 1.05
        and physical_by_workload.get("sysbench-oltp-pqc4000", {}).get("physical_waf", 99) <= 1.25
        and physical_by_workload.get("ycsb-a-pqc4000", {}).get("physical_waf", 99) <= 1.80
        and ycsb_f_best.get("secret_waiting_end") == 0
        and ycsb_f_best.get("physical_waf", 0) >= 3.0
    )
    return Gate(
        "residual_fallback_sweep_defines_strict_mode_frontier",
        passed,
        {
            "decision": summary.get("decision"),
            "dryrun_rows": len(summary.get("dryrun_rows", [])),
            "physical_workloads": {
                workload: {
                    "physical_waf": physical_by_workload.get(workload, {}).get("physical_waf"),
                    "secret_waiting_end": physical_by_workload.get(workload, {}).get("secret_waiting_end"),
                    "max_live_physical_zones": physical_by_workload.get(workload, {}).get("max_live_physical_zones"),
                    "failed_rows": physical_by_workload.get(workload, {}).get("failed_rows"),
                }
                for workload in required_physical
            },
            "ycsb_f_controller_physical": {
                "low_overhead": {
                    "physical_waf": ycsb_low_physical.get("physical_waf"),
                    "secret_waiting_end": ycsb_low_physical.get("secret_waiting_end"),
                    "residual_migrated_blocks": ycsb_low_physical.get("residual_migrated_blocks"),
                    "max_live_physical_zones": ycsb_low_physical.get("max_live_physical_zones"),
                    "failed_rows": ycsb_low_physical.get("failed_rows"),
                },
                "balanced": {
                    "physical_waf": ycsb_balanced_physical.get("physical_waf"),
                    "secret_waiting_end": ycsb_balanced_physical.get("secret_waiting_end"),
                    "residual_migrated_blocks": ycsb_balanced_physical.get("residual_migrated_blocks"),
                    "max_live_physical_zones": ycsb_balanced_physical.get("max_live_physical_zones"),
                    "failed_rows": ycsb_balanced_physical.get("failed_rows"),
                },
                "strict_zero_wait": {
                    "physical_waf": ycsb_strict_physical.get("physical_waf"),
                    "secret_waiting_end": ycsb_strict_physical.get("secret_waiting_end"),
                    "residual_migrated_blocks": ycsb_strict_physical.get("residual_migrated_blocks"),
                    "max_live_physical_zones": ycsb_strict_physical.get("max_live_physical_zones"),
                    "failed_rows": ycsb_strict_physical.get("failed_rows"),
                },
            },
            "budget_rows": [
                {
                    "copy_budget": row.get("copy_budget"),
                    "physical_waf": row.get("physical_waf"),
                    "secret_waiting_end": row.get("secret_waiting_end"),
                    "residual_migration_budget_skips": row.get("residual_migration_budget_skips"),
                }
                for row in budget_rows
            ],
            "budget_physical_rows": [
                {
                    "copy_budget": row.get("copy_budget"),
                    "physical_waf": row.get("physical_waf"),
                    "secret_waiting_end": row.get("secret_waiting_end"),
                    "residual_migrated_blocks": row.get("residual_migrated_blocks"),
                    "residual_migration_budget_skips": row.get("residual_migration_budget_skips"),
                    "max_live_physical_zones": row.get("max_live_physical_zones"),
                    "failed_rows": row.get("failed_rows"),
                }
                for row in budget_physical_rows
            ],
            "controller_ycsb_f": {
                "low_overhead": ycsb_low,
                "balanced": ycsb_balanced,
                "strict_zero_wait": ycsb_strict,
            },
            "ycsb_f_best_zero_wait": {
                "physical_waf": ycsb_f_best.get("physical_waf"),
                "residual_migrated_blocks": ycsb_f_best.get("residual_migrated_blocks"),
                "threshold": ycsb_f_best.get("threshold"),
                "packing": ycsb_f_best.get("packing"),
            },
        },
    )


def run_checks(args: argparse.Namespace) -> dict:
    mixed_rows = load_json(args.mixed)
    e1_rows = load_json(args.e1)
    e5_rows = load_json(args.e5)
    timeline_rows = load_json(args.timeline)
    dogi_adapter = load_json(args.dogi_adapter)
    dogi_preflight = load_json(args.dogi_preflight)
    liboqs_summary = load_json(args.liboqs_summary)
    liboqs_verification = load_json(args.liboqs_verification)
    file_zns_summary = load_json(args.file_zns_summary)
    nullblk_summary = load_json(args.nullblk_summary)
    nullblk_plan = load_json(args.nullblk_plan)
    nullblk_preflight = load_json(args.nullblk_preflight)
    physical_zonefs_replay = load_json(args.physical_zonefs_replay)
    physical_zonefs_suite = load_json(args.physical_zonefs_suite)
    physical_zonefs_write_pressure = load_json(args.physical_zonefs_write_pressure)
    physical_policy_zonefs_replay = load_json(args.physical_policy_zonefs_replay)
    physical_policy_dogi_zonefs_replay = load_json(args.physical_policy_dogi_zonefs_replay)
    packed_policy_replay_analysis = load_json(args.packed_policy_replay_analysis)
    packed_physical_zonefs_replay = load_json(args.packed_physical_zonefs_replay)
    dogi_nullblk_preflight = load_json(args.dogi_nullblk_preflight)
    dogi_run = load_json(args.dogi_run)
    dogi_physical_run = load_json(args.dogi_physical_run)
    dogi_physical_suite = load_json(args.dogi_physical_suite)
    dogi_physical_pressure_suite = load_json(args.dogi_physical_pressure_suite)
    midas_exact_repeat4 = load_json(args.midas_exact_repeat4)
    sepbit_exact_repeat4 = load_json(args.sepbit_exact_repeat4)
    sepbit_nosep_repeat4 = load_json(args.sepbit_nosep_repeat4)
    c_policy_overhead = load_json(args.c_policy_overhead)
    crash_model = load_json(args.crash_model)
    fdp_mapping = load_json(args.fdp_mapping)
    fast_db_pressure = load_json(args.fast_db_pressure)
    fast_ycsb_pressure = load_json(args.fast_ycsb_pressure)
    ycsb_pressure_curve = load_json(args.ycsb_pressure_curve)
    actual_zns_overhead = load_json(args.actual_zns_overhead)
    ycsb_f_straggler_baselines = load_json(args.ycsb_f_straggler_baselines)
    adaptive_policy_comparison = load_json(args.adaptive_policy_comparison)
    multitenant_pressure = load_json(args.multitenant_pressure)
    physical_robustness = load_json(args.physical_robustness)
    residual_fallback_sweep = load_json(args.residual_fallback_sweep)
    security_capability = load_json(args.security_capability)
    claim_matrix = load_json(args.claim_matrix)
    workload_hardness = load_json(args.workload_hardness)
    deployment_selector = load_json(args.deployment_selector)
    reproducibility_manifest = load_json(args.reproducibility_manifest)
    reproducibility_validation = load_json(args.reproducibility_validation)
    gates = [
        gate_quasar_beats_dogi(e1_rows, args.min_workloads),
        gate_waf_and_utilization(e1_rows),
        gate_bad_hints(e5_rows, args.bad_hint_waf_threshold),
        gate_exposure_window(timeline_rows),
        gate_dogi_baseline(dogi_adapter, dogi_preflight),
        gate_dogi_feature_coverage(mixed_rows),
        gate_liboqs_trace(liboqs_summary, liboqs_verification),
        gate_file_zns_replay(file_zns_summary),
        gate_real_nullblk_replay(nullblk_summary),
        gate_physical_zonefs_replay(physical_zonefs_replay),
        gate_physical_zonefs_dogi_suite(physical_zonefs_suite),
        gate_physical_zonefs_write_pressure(physical_zonefs_write_pressure),
        gate_physical_policy_zonefs_replay(physical_policy_zonefs_replay),
        gate_physical_policy_dogi_zonefs_replay(physical_policy_dogi_zonefs_replay),
        gate_packed_policy_replay_analysis(packed_policy_replay_analysis),
        gate_packed_physical_zonefs_replay(packed_physical_zonefs_replay),
        gate_dogi_nullblk_preflight(dogi_nullblk_preflight),
        gate_dogi_real_nullblk_run(dogi_run, dogi_adapter),
        gate_dogi_physical_compact_run(dogi_physical_run),
        gate_dogi_physical_full_suite(dogi_physical_suite),
        gate_dogi_physical_pressure_suite(dogi_physical_pressure_suite),
        gate_midas_exact_repeat4(midas_exact_repeat4),
        gate_sepbit_exact_repeat4(sepbit_exact_repeat4, sepbit_nosep_repeat4),
        gate_nullblk_path(nullblk_plan, nullblk_preflight),
        gate_figures(args.figures_dir),
        gate_c_policy_overhead(c_policy_overhead),
        gate_crash_recovery_cost(crash_model),
        gate_fdp_mapping(fdp_mapping),
        gate_fast_db_pressure(fast_db_pressure),
        gate_fast_ycsb_pressure(fast_ycsb_pressure, ycsb_pressure_curve, ycsb_f_straggler_baselines),
        gate_actual_zns_overhead(actual_zns_overhead),
        gate_adaptive_policy_comparison(adaptive_policy_comparison),
        gate_multitenant_pressure(multitenant_pressure),
        gate_physical_robustness(physical_robustness),
        gate_residual_fallback_sweep(residual_fallback_sweep),
        gate_security_capability(security_capability),
        gate_claim_matrix(claim_matrix),
        gate_workload_hardness_matrix(workload_hardness),
        gate_deployment_policy_selector(deployment_selector),
        gate_reproducibility_manifest(reproducibility_manifest),
        gate_reproducibility_validation(reproducibility_validation),
    ]
    return {
        "passed": all(gate.passed for gate in gates),
        "passed_gates": sum(1 for gate in gates if gate.passed),
        "total_gates": len(gates),
        "gates": [asdict(gate) for gate in gates],
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mixed", type=Path, default=Path("artifacts/results/pqc-mixed-verification.json"))
    parser.add_argument("--e1", type=Path, default=Path("artifacts/results/e1-workloads.json"))
    parser.add_argument("--e5", type=Path, default=Path("artifacts/results/schema-test-runner/e5-bad-hints.json"))
    parser.add_argument("--timeline", type=Path, default=Path("artifacts/results/e4-exposure-timeline.json"))
    parser.add_argument("--dogi-adapter", type=Path, default=Path("artifacts/results/pqc-mixed-dogi-adapter.json"))
    parser.add_argument("--dogi-preflight", type=Path, default=Path("artifacts/results/dogi-preflight.json"))
    parser.add_argument("--liboqs-summary", type=Path, default=Path("artifacts/results/liboqs-pqc-summary.json"))
    parser.add_argument("--liboqs-verification", type=Path, default=Path("artifacts/results/liboqs-pqc-verification.json"))
    parser.add_argument("--file-zns-summary", type=Path, default=Path("artifacts/results/pqc-mixed-file-zns-summary.json"))
    parser.add_argument("--nullblk-summary", type=Path, default=Path("artifacts/results/pqc-mixed-nullblk-summary.json"))
    parser.add_argument("--nullblk-plan", type=Path, default=Path("artifacts/results/nullblk-zoned-plan.json"))
    parser.add_argument("--nullblk-preflight", type=Path, default=Path("artifacts/results/nullblk-zoned-preflight.json"))
    parser.add_argument("--physical-zonefs-replay", type=Path, default=Path("artifacts/results/physical-zonefs-replay-kms.json"))
    parser.add_argument("--physical-zonefs-suite", type=Path, default=Path("artifacts/results/physical-zonefs-dogi-pqc2000-suite-summary.json"))
    parser.add_argument("--physical-zonefs-write-pressure", type=Path, default=Path("artifacts/results/physical-zonefs-write-pressure-pqc2000-rf0-scale40.json"))
    parser.add_argument("--physical-policy-zonefs-replay", type=Path, default=Path("artifacts/results/physical-policy-zonefs-replay-pqc-direct.json"))
    parser.add_argument("--physical-policy-dogi-zonefs-replay", type=Path, default=Path("artifacts/results/physical-policy-zonefs-replay-dogi-pqc2000-physical-capacity.json"))
    parser.add_argument("--packed-policy-replay-analysis", type=Path, default=Path("artifacts/results/packed-policy-replay-dogi-pqc2000-z512-pressure-physical-zones.json"))
    parser.add_argument(
        "--packed-physical-zonefs-replay",
        type=Path,
        default=Path(
            "artifacts/results/packed-physical-zonefs-replay-dogi-paper-pqc2000-z512-secret-group-helper.json"
        ),
    )
    parser.add_argument("--dogi-nullblk-preflight", type=Path, default=Path("artifacts/results/dogi-preflight-nullblk.json"))
    parser.add_argument("--dogi-run", type=Path, default=Path("artifacts/results/dogi-nullblk-full-run.json"))
    parser.add_argument("--dogi-physical-run", type=Path, default=Path("artifacts/results/dogi-physical-zns-compact-exchange-clean-run.json"))
    parser.add_argument("--dogi-physical-suite", type=Path, default=Path("artifacts/results/dogi-physical-zns-full-pqc2000-compact-lg2/summary.json"))
    parser.add_argument("--dogi-physical-pressure-suite", type=Path, default=Path("artifacts/results/dogi-exact/alibaba-pqc8000-suite.json"))
    parser.add_argument("--midas-exact-repeat4", type=Path, default=Path("artifacts/results/midas-exact/exchange-pqc2000-repeat4-compact.json"))
    parser.add_argument("--sepbit-exact-repeat4", type=Path, default=Path("artifacts/results/sepbit-exact/exchange-pqc2000-repeat4-compact-sepbit.json"))
    parser.add_argument("--sepbit-nosep-repeat4", type=Path, default=Path("artifacts/results/sepbit-exact/exchange-pqc2000-repeat4-compact-nosep.json"))
    parser.add_argument("--c-policy-overhead", type=Path, default=Path("artifacts/results/c-policy-overhead.json"))
    parser.add_argument("--crash-model", type=Path, default=Path("artifacts/results/pqc-mixed-crash-model.json"))
    parser.add_argument("--fdp-mapping", type=Path, default=Path("artifacts/results/pqc-mixed-fdp-mapping.json"))
    parser.add_argument("--fast-db-pressure", type=Path, default=Path("artifacts/results/fast-db-pressure/sysbench-pressure-summary.json"))
    parser.add_argument("--fast-ycsb-pressure", type=Path, default=Path("artifacts/results/fast-ycsb-pressure/ycsb-pressure-summary.json"))
    parser.add_argument(
        "--ycsb-pressure-curve",
        type=Path,
        default=Path("artifacts/results/fast-ycsb-pressure/ycsb-actual-zns-pressure-curve.json"),
    )
    parser.add_argument("--actual-zns-overhead", type=Path, default=Path("artifacts/results/actual-zns-overhead-summary.json"))
    parser.add_argument(
        "--ycsb-f-straggler-baselines",
        type=Path,
        default=Path(
            "artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc8000-straggler005-baselines-helper.json"
        ),
    )
    parser.add_argument("--adaptive-policy-comparison", type=Path, default=Path("artifacts/results/adaptive-policy-comparison.json"))
    parser.add_argument("--multitenant-pressure", type=Path, default=Path("artifacts/results/multitenant-pressure/multitenant-pressure-summary.json"))
    parser.add_argument("--physical-robustness", type=Path, default=Path("artifacts/results/physical-robustness-ycsb-a-pqc4000/summary.json"))
    parser.add_argument("--residual-fallback-sweep", type=Path, default=Path("artifacts/results/residual-fallback-sweep/summary.json"))
    parser.add_argument("--security-capability", type=Path, default=Path("artifacts/results/physical-zns-security-capability.json"))
    parser.add_argument("--claim-matrix", type=Path, default=Path("artifacts/results/quasar-claim-matrix.json"))
    parser.add_argument("--workload-hardness", type=Path, default=Path("artifacts/results/workload-hardness-matrix.json"))
    parser.add_argument("--deployment-selector", type=Path, default=Path("artifacts/results/quasar-deployment-policy-selector.json"))
    parser.add_argument("--reproducibility-manifest", type=Path, default=Path("artifacts/results/quasar-reproducibility-manifest.json"))
    parser.add_argument("--reproducibility-validation", type=Path, default=Path("artifacts/results/quasar-reproducibility-validation.json"))
    parser.add_argument("--figures-dir", type=Path, default=Path("artifacts/figures"))
    parser.add_argument("--min-workloads", type=int, default=3)
    parser.add_argument("--bad-hint-waf-threshold", type=float, default=1.05)
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/acceptance-report.json"))
    args = parser.parse_args()

    report = run_checks(args)
    write_json(args.out, report)
    print(f"wrote {args.out}")
    print(json.dumps({"passed": report["passed"], "passed_gates": report["passed_gates"], "total_gates": report["total_gates"]}, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
