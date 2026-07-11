#!/usr/bin/env python3
"""Summarize external-system readiness for QUASAR experiments.

This report is intentionally conservative. Simulator artifacts can pass while
production-like OpenSSL service capture, physical ZNS/FDP replay, or exact
baseline runs are still blocked by local environment state.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_INPUTS = {
    "openssl": Path("artifacts/results/openssl-pqc-capability.json"),
    "openssl_oqsprovider_run": Path("artifacts/results/openssl-oqsprovider/summary.json"),
    "openssl_oqsprovider_service_run": Path("artifacts/results/openssl-oqsprovider-kem-service/summary.json"),
    "openssl_oqsprovider_tls_socket_run": Path("artifacts/results/openssl-oqsprovider-tls-socket/summary.json"),
    "zns": Path("artifacts/results/zns-preflight.json"),
    "physical_zns": Path("artifacts/results/physical-zns-readiness.json"),
    "physical_zonefs_append": Path("artifacts/results/physical-zonefs-append.json"),
    "physical_zonefs_replay": Path("artifacts/results/physical-zonefs-replay-kms.json"),
    "physical_zonefs_suite": Path("artifacts/results/physical-zonefs-dogi-pqc2000-suite-summary.json"),
    "physical_zonefs_write_pressure": Path("artifacts/results/physical-zonefs-write-pressure-pqc2000-rf0-scale40.json"),
    "physical_policy_zonefs_replay": Path("artifacts/results/physical-policy-zonefs-replay-pqc-direct.json"),
    "physical_policy_dogi_zonefs_replay": Path("artifacts/results/physical-policy-zonefs-replay-dogi-pqc2000-physical-capacity.json"),
    "packed_policy_replay_analysis": Path("artifacts/results/packed-policy-replay-dogi-pqc2000-z512-pressure-physical-zones.json"),
    "packed_physical_zonefs_replay": Path(
        "artifacts/results/packed-physical-zonefs-replay-dogi-paper-pqc2000-z512-secret-group-helper.json"
    ),
    "dogi_preflight": Path("artifacts/results/dogi-preflight.json"),
    "dogi_run": Path("artifacts/results/dogi-nullblk-full-run.json"),
    "dogi_physical_run": Path("artifacts/results/dogi-physical-zns-compact-exchange-clean-run.json"),
    "dogi_physical_suite": Path("artifacts/results/dogi-physical-zns-full-pqc2000-compact-lg2/summary.json"),
    "dogi_physical_pressure_run": Path("artifacts/results/dogi-exact/alibaba-pqc8000-dogi.json"),
    "dogi_physical_pressure_suite": Path("artifacts/results/dogi-exact/alibaba-pqc8000-suite.json"),
    "dogi_physical_original_lba_run": Path("artifacts/results/dogi-exact/alibaba-pqc8000-original-lba-dogi-cwd-app.json"),
    "midas": Path("artifacts/results/midas-preflight.json"),
    "midas_run": Path("artifacts/results/midas-exact/pqc-pressure-1g.json"),
    "midas_repeat_run": Path("artifacts/results/midas-exact/exchange-pqc2000-repeat4-compact.json"),
    "sepbit_run": Path("artifacts/results/sepbit-exact/pqc-pressure-1g-sepbit.json"),
    "sepbit_repeat_run": Path("artifacts/results/sepbit-exact/exchange-pqc2000-repeat4-compact-sepbit.json"),
    "sepbit_nosep_repeat_run": Path("artifacts/results/sepbit-exact/exchange-pqc2000-repeat4-compact-nosep.json"),
    "fast_db_pressure": Path("artifacts/results/fast-db-pressure/sysbench-pressure-summary.json"),
    "fast_ycsb_pressure": Path("artifacts/results/fast-ycsb-pressure/ycsb-pressure-summary.json"),
    "ycsb_pressure_curve": Path("artifacts/results/fast-ycsb-pressure/ycsb-actual-zns-pressure-curve.json"),
    "actual_zns_overhead": Path("artifacts/results/actual-zns-overhead-summary.json"),
    "ycsb_f_straggler_baselines": Path(
        "artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc8000-straggler005-baselines-helper.json"
    ),
    "adaptive_policy_comparison": Path("artifacts/results/adaptive-policy-comparison.json"),
    "multitenant_pressure": Path("artifacts/results/multitenant-pressure/multitenant-pressure-summary.json"),
    "physical_robustness": Path("artifacts/results/physical-robustness-ycsb-a-pqc4000/summary.json"),
    "residual_fallback_sweep": Path("artifacts/results/residual-fallback-sweep/summary.json"),
    "security_capability": Path("artifacts/results/physical-zns-security-capability.json"),
    "claim_matrix": Path("artifacts/results/quasar-claim-matrix.json"),
    "workload_hardness": Path("artifacts/results/workload-hardness-matrix.json"),
    "deployment_selector": Path("artifacts/results/quasar-deployment-policy-selector.json"),
    "reproducibility_manifest": Path("artifacts/results/quasar-reproducibility-manifest.json"),
    "reproducibility_validation": Path("artifacts/results/quasar-reproducibility-validation.json"),
    "acceptance": Path("artifacts/results/acceptance-report.json"),
}


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def first_line(text: str | None) -> str:
    if not text:
        return ""
    return text.splitlines()[0] if text.splitlines() else text


def openssl_status(
    data: dict[str, Any] | None,
    provider_run: dict[str, Any] | None = None,
    service_run: dict[str, Any] | None = None,
    tls_socket_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if tls_socket_run is not None:
        if tls_socket_run.get("all_tls_ok"):
            return {
                "status": "done-local-tls-socket",
                "summary": (
                    "OpenSSL s_server/s_client with oqsprovider completed "
                    f"{tls_socket_run.get('sessions')} TLS 1.3 handshakes using group {tls_socket_run.get('group')}."
                ),
                "evidence": {
                    "openssl_bin": tls_socket_run.get("openssl_bin"),
                    "provider_module_path": tls_socket_run.get("provider_module_path"),
                    "sessions": tls_socket_run.get("sessions"),
                    "group": tls_socket_run.get("group"),
                    "avg_client_handshake_ns": tls_socket_run.get("avg_client_handshake_ns"),
                },
                "next": "Use this as the local TLS socket trace; add real service logs only if deployment realism is required.",
            }
    if service_run is not None:
        if (
            service_run.get("all_kem_ok")
            and service_run.get("all_sig_ok")
            and service_run.get("kem_encap_c_api_supported")
        ):
            return {
                "status": "done-local-kem-service",
                "summary": (
                    "OpenSSL 3 + oqsprovider C API generated provider-backed "
                    f"{service_run.get('kem')}/{service_run.get('sig')} KEM encap/decap traces."
                ),
                "evidence": {
                    "provider_module_path": service_run.get("provider_module_path"),
                    "probe_bin": service_run.get("probe_bin"),
                    "sessions": service_run.get("sessions"),
                    "ciphertext_bytes": service_run.get("ciphertext_bytes"),
                    "shared_secret_bytes": service_run.get("shared_secret_bytes"),
                    "signature_bytes": service_run.get("signature_bytes"),
                },
                "next": "Use this as the provider-backed KEM service trace; add TLS socket or production-like service logs if available.",
            }
    if provider_run is not None:
        probe = provider_run.get("probe", {})
        if (
            probe.get("kem_provider_detected")
            and probe.get("sig_provider_detected")
            and provider_run.get("all_sig_ok")
        ):
            return {
                "status": "done-local-build",
                "summary": (
                    "OpenSSL 3 + oqsprovider local build generated provider-backed "
                    f"{provider_run.get('kem')}/{provider_run.get('sig')} traces."
                ),
                "evidence": {
                    "openssl_bin": provider_run.get("openssl_bin"),
                    "provider_module_path": provider_run.get("provider_module_path"),
                    "sessions": provider_run.get("sessions"),
                    "kem_encap_cli_supported": provider_run.get("kem_encap_cli_supported"),
                },
                "next": "Use this as the provider-backed sanity trace; add KEM C-API, TLS socket, or production-like service logs if available.",
            }
    if data is None:
        return {
            "status": "missing",
            "summary": "OpenSSL/PQC provider probe has not been run.",
            "next": "Run code/tracegen/oqs_tls_trace.py with --probe-out.",
        }
    if data.get("pqc_provider_detected"):
        return {
            "status": "ready",
            "summary": "PQC provider detected by the local OpenSSL probe.",
            "next": "Capture OpenSSL/oqsprovider event logs and replay them through the simulator.",
        }
    version = first_line(data.get("version", {}).get("stdout"))
    providers = data.get("providers", {})
    kem = data.get("kem_algorithms", {})
    return {
        "status": "blocked",
        "summary": "PQC provider was not detected locally.",
        "evidence": {
            "openssl_version": version,
            "providers_returncode": providers.get("returncode"),
            "kem_returncode": kem.get("returncode"),
        },
        "next": "Use OpenSSL 3.x with oqsprovider, or collect event logs from a PQC-enabled host.",
    }


def zns_status(
    data: dict[str, Any] | None,
    physical: dict[str, Any] | None = None,
    append_probe: dict[str, Any] | None = None,
    physical_replay: dict[str, Any] | None = None,
    physical_suite: dict[str, Any] | None = None,
    physical_write_pressure: dict[str, Any] | None = None,
    physical_policy_replay: dict[str, Any] | None = None,
    physical_policy_dogi_replay: dict[str, Any] | None = None,
    packed_policy_analysis: dict[str, Any] | None = None,
    packed_physical_replay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if physical and physical.get("status") == "physical-zns-detected":
        policy_replay_ok = bool(
            physical_policy_replay
            and physical_policy_replay.get("execute")
            and physical_policy_replay.get("summary", {}).get("failed_rows", 1) == 0
            and physical_policy_replay.get("summary", {}).get("row_count", 0) >= 20
            and physical_policy_replay.get("summary", {})
            .get("by_policy", {})
            .get("quasar-dogi-hybrid", {})
            .get("physical_resets", 0)
            > 0
        )
        pressure_ok = bool(
            physical_write_pressure
            and physical_write_pressure.get("execute")
            and not physical_write_pressure.get("failed", True)
            and physical_write_pressure.get("summary", {}).get("total_bytes_written", 0) >= 100 * 1024 * 1024 * 1024
            and physical_write_pressure.get("summary", {})
            .get("dogi_vs_hybrid", {})
            .get("hybrid_block_reduction_vs_dogi", 0.0)
            > 0.0
        )
        dogi_policy_replay_ok = bool(
            physical_policy_dogi_replay
            and physical_policy_dogi_replay.get("execute")
            and physical_policy_dogi_replay.get("summary", {}).get("failed_rows", 1) == 0
            and physical_policy_dogi_replay.get("summary", {}).get("row_count", 0) >= 30
            and physical_policy_dogi_replay.get("summary", {})
            .get("by_policy", {})
            .get("quasar-dogi-hybrid", {})
            .get("physical_resets", 0)
            > 0
        )
        if pressure_ok:
            summary = physical_write_pressure.get("summary", {})
            comparison = summary.get("dogi_vs_hybrid", {})
            total_gib = summary.get("total_bytes_written", 0) / (1024**3)
            policy_summary = physical_policy_replay.get("summary", {}) if policy_replay_ok else {}
            policy_by_policy = policy_summary.get("by_policy", {})
            hybrid_policy = policy_by_policy.get("quasar-dogi-hybrid", {})
            dogi_policy = policy_by_policy.get("dogi-history", {})
            dogi_policy_summary = physical_policy_dogi_replay.get("summary", {}) if dogi_policy_replay_ok else {}
            dogi_policy_by_policy = dogi_policy_summary.get("by_policy", {})
            dogi_capacity_hybrid = dogi_policy_by_policy.get("quasar-dogi-hybrid", {})
            dogi_capacity_dogi = dogi_policy_by_policy.get("dogi-history", {})
            packed_summary = (packed_policy_analysis or {}).get("summary", {})
            packed_rows = packed_summary.get("by_policy_packing", {})
            packed_any = packed_rows.get("quasar-dogi-hybrid::any", {})
            packed_group = packed_rows.get("quasar-dogi-hybrid::group", {})
            packed_logical = packed_rows.get("quasar-dogi-hybrid::logical-zone", {})
            packed_physical_summary = (packed_physical_replay or {}).get("summary", {})
            packed_physical_rows = packed_physical_summary.get("by_policy_packing", {})
            packed_physical_group = packed_physical_rows.get("quasar-dogi-hybrid::group", {})
            packed_physical_secret_group = packed_physical_rows.get("quasar-dogi-hybrid::secret-group", {})
            return {
                "status": (
                    "done-physical-zonefs-write-pressure-plus-policy-and-packed-replay"
                    if policy_replay_ok and dogi_policy_replay_ok and packed_physical_replay
                    else "done-physical-zonefs-write-pressure-plus-policy-replay"
                    if policy_replay_ok and dogi_policy_replay_ok
                    else "done-physical-zonefs-write-pressure"
                ),
                "summary": (
                    "Physical ZNS SSD detected; DOGI-shaped PQC2000 policy write-pressure suite "
                    f"completed with {total_gib:.2f} GiB of zonefs append traffic"
                    + (
                        ", direct policy-operation zonefs replay completed for PQC/liboqs traces, "
                        "physical-capacity DOGI-shaped policy-operation replay completed, "
                        "and packed logical-to-physical zonefs replay completed."
                        if policy_replay_ok and dogi_policy_replay_ok and packed_physical_replay
                        else ", direct policy-operation zonefs replay completed for PQC/liboqs traces, "
                        "and physical-capacity DOGI-shaped policy-operation replay completed."
                        if policy_replay_ok and dogi_policy_replay_ok
                        else "."
                    )
                ),
                "evidence": {
                    "device": physical.get("device"),
                    "mount": physical.get("mount"),
                    "model": physical.get("detected", {}).get("model"),
                    "scale": physical_write_pressure.get("scale"),
                    "rows": summary.get("row_count"),
                    "total_gib_written": summary.get("total_bytes_written", 0) / (1024**3),
                    "hybrid_block_reduction_vs_dogi": comparison.get("hybrid_block_reduction_vs_dogi"),
                    "stale_secret_blocks_avoided": comparison.get("stale_secret_blocks_avoided"),
                    "policy_replay_rows": policy_summary.get("row_count"),
                    "policy_replay_hybrid_resets": hybrid_policy.get("physical_resets"),
                    "policy_replay_dogi_stale_secrets": dogi_policy.get("sim_stale_secret_blocks"),
                    "policy_replay_hybrid_stale_secrets": hybrid_policy.get("sim_stale_secret_blocks"),
                    "dogi_policy_replay_rows": dogi_policy_summary.get("row_count"),
                    "dogi_policy_replay_hybrid_resets": dogi_capacity_hybrid.get("physical_resets"),
                    "dogi_policy_replay_hybrid_max_open_zones": dogi_capacity_hybrid.get("max_open_zone_files"),
                    "dogi_policy_replay_dogi_stale_secrets": dogi_capacity_dogi.get("sim_stale_secret_blocks"),
                    "dogi_policy_replay_hybrid_stale_secrets": dogi_capacity_hybrid.get("sim_stale_secret_blocks"),
                    "packed_analysis_rows": packed_summary.get("row_count"),
                    "packed_any_secret_waiting_end": packed_any.get("secret_blocks_waiting_for_physical_reset"),
                    "packed_group_secret_waiting_end": packed_group.get("secret_blocks_waiting_for_physical_reset"),
                    "packed_group_max_live_physical_zones": packed_group.get("max_live_physical_zones"),
                    "packed_logical_zone_max_live_physical_zones": packed_logical.get("max_live_physical_zones"),
                    "packed_physical_rows": packed_physical_summary.get("row_count"),
                    "packed_physical_wall_time_s": packed_physical_summary.get("wall_time_s"),
                    "packed_physical_append_engine": (packed_physical_replay or {}).get("append_engine"),
                    "packed_physical_helper_chunk_blocks": (packed_physical_replay or {}).get("helper_chunk_blocks"),
                    "packed_physical_group_secret_waiting_end": packed_physical_group.get("secret_blocks_waiting_for_physical_reset"),
                    "packed_physical_group_resets": packed_physical_group.get("physical_reset_commands"),
                    "packed_physical_group_max_live_physical_zones": packed_physical_group.get("max_live_physical_zones"),
                    "packed_physical_group_avg_utilization": packed_physical_group.get("avg_space_utilization"),
                    "packed_physical_secret_group_secret_waiting_end": packed_physical_secret_group.get("secret_blocks_waiting_for_physical_reset"),
                    "packed_physical_secret_group_resets": packed_physical_secret_group.get("physical_reset_commands"),
                    "packed_physical_secret_group_max_live_physical_zones": packed_physical_secret_group.get("max_live_physical_zones"),
                    "packed_physical_secret_group_avg_utilization": packed_physical_secret_group.get("avg_space_utilization"),
                },
                "next": "Use this as physical write-pressure and packed placement evidence; add xNVMe/SPDK only if lower-overhead replay is needed.",
            }
        suite_ok = bool(
            physical_suite
            and physical_suite.get("all_passed")
            and physical_suite.get("workloads", 0) >= 6
            and physical_suite.get("total_bytes_written", 0) > 0
            and physical_suite.get("total_reset_family_commands", 0) > 0
        )
        if suite_ok:
            return {
                "status": "done-physical-zonefs-dogi-suite",
                "summary": (
                    "Physical ZNS SSD detected; DOGI-shaped six-workload PQC2000 zonefs replay suite "
                    "completed with zonefs append and reset-family commands."
                ),
                "evidence": {
                    "device": physical.get("device"),
                    "mount": physical.get("mount"),
                    "model": physical.get("detected", {}).get("model"),
                    "zones": physical.get("zns_report", {}).get("nr_zones"),
                    "workloads": physical_suite.get("workloads"),
                    "total_gib_written": physical_suite.get("total_gib_written"),
                    "total_append_commands": physical_suite.get("total_append_commands"),
                    "total_reset_family_commands": physical_suite.get("total_reset_family_commands"),
                    "max_active_zone_files": physical_suite.get("max_active_zone_files"),
                    "median_p99_append_latency_ns": physical_suite.get("median_p99_append_latency_ns"),
                },
                "next": "Use this as the paper-scale physical append/reset feasibility result; add xNVMe/SPDK only if lower-overhead replay is needed.",
            }
        replay_ok = bool(
            physical_replay
            and physical_replay.get("execute")
            and physical_replay.get("bytes_written", 0) > 0
            and physical_replay.get("reset_issued") is False
        )
        if replay_ok:
            return {
                "status": "done-physical-zonefs-replay",
                "summary": (
                    "Physical ZNS SSD detected; tiny append smoke and guarded non-resetting zonefs trace replay succeeded."
                ),
                "evidence": {
                    "device": physical.get("device"),
                    "mount": physical.get("mount"),
                    "model": physical.get("detected", {}).get("model"),
                    "zones": physical.get("zns_report", {}).get("nr_zones"),
                    "append_commands": physical_replay.get("append_commands"),
                    "bytes_written": physical_replay.get("bytes_written"),
                    "zone_files_used": physical_replay.get("zone_files_used"),
                    "p99_append_latency_ns": physical_replay.get("latency", {}).get("p99_ns"),
                    "reset_issued": physical_replay.get("reset_issued"),
                },
                "next": "Run paper-scale replay only after defining a physical zone reset/sanitize policy.",
            }
        append_ok = bool(append_probe and append_probe.get("write_succeeded"))
        if append_ok:
            return {
                "status": "done-physical-zonefs-smoke",
                "summary": (
                    "Physical ZNS SSD detected and a tiny non-resetting zonefs append smoke test succeeded."
                ),
                "evidence": {
                    "device": physical.get("device"),
                    "mount": physical.get("mount"),
                    "model": physical.get("detected", {}).get("model"),
                    "zones": physical.get("zns_report", {}).get("nr_zones"),
                    "bytes_written": append_probe.get("bytes_written"),
                    "target": append_probe.get("target"),
                    "reset_issued": append_probe.get("reset_issued"),
                },
                "next": "Run guarded paper-scale replay only after deciding whether physical zone reset is allowed.",
            }
        return {
            "status": "partial-physical-readonly",
            "summary": "Physical ZNS SSD is detected, but a zonefs append smoke result is not yet successful.",
            "evidence": {
                "device": physical.get("device"),
                "mount": physical.get("mount"),
                "model": physical.get("detected", {}).get("model"),
                "zones": physical.get("zns_report", {}).get("nr_zones"),
                "append_status": append_probe.get("status") if append_probe else None,
            },
            "next": "Run code/quasar/zonefs_append_probe.py --execute for a tiny non-resetting append smoke test.",
        }
    if data is None:
        return {
            "status": "missing",
            "summary": "ZNS/FDP preflight has not been run.",
            "next": "Run code/quasar/zns_preflight.py.",
        }
    zoned_devices = data.get("zoned_devices", [])
    null_blk = data.get("null_blk", {})
    zone_report_errors = {
        path: first_line(report.get("stderr"))
        for path, report in data.get("zoned_device_reports", {}).items()
        if report.get("returncode") not in {0, None}
    }
    if data.get("can_run_real_zns_replay"):
        return {
            "status": "ready",
            "summary": f"{len(zoned_devices)} zoned target(s) are available for real replay.",
            "next": "Run guarded blkzone/xNVMe/SPDK replay and collect latency/reset counters.",
        }
    if null_blk.get("module_available"):
        return {
            "status": "partial",
            "summary": "No physical zoned device is ready, but null_blk support exists for guarded emulation.",
            "evidence": {
                "zoned_devices": len(zoned_devices),
                "can_run_real_zns_replay": data.get("can_run_real_zns_replay"),
                "zone_report_errors": zone_report_errors,
                "xnvme": data.get("tools", {}).get("xnvme"),
                "spdk_nvme_perf": data.get("tools", {}).get("spdk_nvme_perf"),
            },
            "next": "Use null_blk with appropriate block-device permission for reproducibility; obtain physical ZNS/FDP or xNVMe/SPDK target for paper-grade replay.",
        }
    return {
        "status": "blocked",
        "summary": "No usable ZNS/FDP replay target was detected.",
        "evidence": {"zoned_devices": len(zoned_devices)},
        "next": "Attach a physical/emulated ZNS target or enable null_blk zoned support.",
    }


def dogi_status(
    preflight: dict[str, Any] | None,
    run: dict[str, Any] | None,
    physical_run: dict[str, Any] | None = None,
    physical_suite: dict[str, Any] | None = None,
    physical_pressure_run: dict[str, Any] | None = None,
    physical_pressure_suite: dict[str, Any] | None = None,
    physical_original_lba_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if run and run.get("completed"):
        if physical_suite and physical_suite.get("completed"):
            pressure_done = bool(physical_pressure_run and physical_pressure_run.get("completed"))
            pressure_suite_done = bool(
                physical_pressure_suite
                and physical_pressure_suite.get("completed_runs") == physical_pressure_suite.get("total_runs")
            )
            original_lba_done = bool(physical_original_lba_run and physical_original_lba_run.get("completed"))
            return {
                "status": (
                    "done-nullblk-plus-physical-full-compact-plus-dynamic-pressure-plus-original-lba"
                    if pressure_done and original_lba_done
                    else "done-nullblk-plus-physical-full-compact-plus-dynamic-pressure"
                    if pressure_done
                    else "done-nullblk-plus-physical-full-compact"
                ),
                "summary": (
                    "External DOGI prototype completed on null_blk/ZenFS and on a six-workload "
                    "compact-LBA physical ZNS PQC2000 suite."
                    + (
                        " It also completed DOGI/Greedy/CostBenefit on an Alibaba-like p8000 compact physical ZNS pressure trace."
                        if pressure_suite_done
                        else " It also completed on an Alibaba-like p8000 compact physical ZNS pressure trace."
                        if pressure_done
                        else ""
                    )
                    + (
                        " The Alibaba-like p8000 original-LBA span also completed on the public DOGI stack."
                        if original_lba_done
                        else ""
                    )
                ),
                "evidence": {
                    "nullblk_waf": run.get("waf"),
                    "physical_suite_workloads": physical_suite.get("workloads"),
                    "physical_suite_logical_size_gb": physical_suite.get("logical_size_gb"),
                    "physical_suite_aggregate_waf": physical_suite.get("aggregate_waf"),
                    "physical_suite_avg_waf": physical_suite.get("avg_waf"),
                    "physical_suite_user_write_gib": physical_suite.get("total_user_write_gib"),
                    "physical_suite_gc_write_gib": physical_suite.get("total_gc_write_gib"),
                    "physical_pressure_waf": (physical_pressure_run or {}).get("waf"),
                    "physical_pressure_user_write_gib": (physical_pressure_run or {}).get("user_write_gib"),
                    "physical_pressure_gc_write_gib": (physical_pressure_run or {}).get("gc_write_gib"),
                    "physical_pressure_trace": (physical_pressure_run or {}).get("trace_path"),
                    "physical_pressure_suite_completed_runs": (physical_pressure_suite or {}).get("completed_runs"),
                    "physical_pressure_suite_total_runs": (physical_pressure_suite or {}).get("total_runs"),
                    "physical_pressure_suite_best_placement": (physical_pressure_suite or {}).get("best_placement"),
                    "physical_pressure_suite_best_waf": (physical_pressure_suite or {}).get("best_waf"),
                    "physical_original_lba_waf": (physical_original_lba_run or {}).get("waf"),
                    "physical_original_lba_user_write_gib": (physical_original_lba_run or {}).get("user_write_gib"),
                    "physical_original_lba_gc_write_gib": (physical_original_lba_run or {}).get("gc_write_gib"),
                    "physical_original_lba_trace": (physical_original_lba_run or {}).get("trace_path"),
                },
                "next": (
                    "Use this as exact DOGI physical pressure evidence; compact and original-LBA units remain separate from packed QUASAR replay."
                    if original_lba_done
                    else "Use this as exact DOGI physical pressure evidence; full original LBA-span runs still need more host memory or a larger logical device configuration."
                ),
            }
        if physical_run and physical_run.get("completed"):
            return {
                "status": "done-nullblk-plus-physical-compact",
                "summary": (
                    "External DOGI prototype completed on null_blk/ZenFS and also reached final "
                    "UserWrite/GCWrite stats with clean exit on a compact-LBA physical ZNS run."
                ),
                "evidence": {
                    "nullblk_waf": run.get("waf"),
                    "physical_compact_waf": physical_run.get("waf"),
                    "physical_user_write_gib": physical_run.get("user_write_gib"),
                    "physical_gc_write_gib": physical_run.get("gc_write_gib"),
                    "physical_saw_zenfs_mount": physical_run.get("saw_zenfs_mount"),
                    "physical_saw_dogi_select": physical_run.get("saw_dogi_select"),
                },
                "next": "Keep null_blk as the reproducible exact baseline; use the compact physical run as hardware feasibility evidence, not as a full paper-scale trace replacement.",
            }
        return {
            "status": "done-nullblk",
            "summary": "External DOGI prototype completed on memory-backed null_blk/ZenFS.",
            "evidence": {
                "waf": run.get("waf"),
                "user_write_gib": run.get("user_write_gib"),
                "gc_write_gib": run.get("gc_write_gib"),
            },
            "next": "Repeat on physical ZNS/NVMeVirt if available; keep null_blk result as reproducible baseline.",
        }
    if preflight and preflight.get("can_configure_build"):
        return {
            "status": "partial",
            "summary": "DOGI repo and trace parser are compatible, but full run is not complete.",
            "evidence": {"can_run_full_prototype": preflight.get("can_run_full_prototype")},
            "next": "Configure RocksDB/ZenFS and a zoned target, then run DOGI.",
        }
    return {
        "status": "missing",
        "summary": "DOGI readiness has not been established.",
        "next": "Run fetch_dogi.py, dogi_trace_adapter.py, and dogi_preflight.py.",
    }


def midas_status(
    data: dict[str, Any] | None,
    run: dict[str, Any] | None = None,
    repeat_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if repeat_run and repeat_run.get("completed"):
        adapter = repeat_run.get("adapter_summary", {})
        return {
            "status": "done-local-memory-repeat4",
            "summary": (
                "External MiDAS memory-backed prototype completed on a 1.53M-request "
                "PQC repeat4 compact trace and remained strong "
                f"with WAF {repeat_run.get('total_waf')}."
            ),
            "evidence": {
                "trace": repeat_run.get("trace"),
                "storage_capacity_gib": repeat_run.get("storage_capacity_gib"),
                "dogi_lines": adapter.get("dogi_lines"),
                "dogi_tombstones": adapter.get("dogi_tombstones"),
                "compact_lba": adapter.get("compact_lba"),
                "compact_span_blocks": adapter.get("compact_span_blocks"),
                "runtime_seconds": repeat_run.get("runtime_seconds"),
                "dataw": repeat_run.get("counters", {}).get("dataw"),
                "gcdw": repeat_run.get("counters", {}).get("gcdw"),
                "total_waf": repeat_run.get("total_waf"),
                "recomputed_waf": repeat_run.get("recomputed_waf_from_dataw_gcdw"),
            },
            "next": "Do not claim MiDAS collapses on every PQC trace; position QUASAR on death-cohort reset/security semantics and DOGI-style failure modes.",
        }
    if run and run.get("completed"):
        return {
            "status": "done-local-memory",
            "summary": (
                "External MiDAS memory-backed prototype completed on a PQC pressure trace "
                f"with WAF {run.get('total_waf')}."
            ),
            "evidence": {
                "trace": run.get("trace"),
                "storage_capacity_gib": run.get("storage_capacity_gib"),
                "build": run.get("build"),
                "runtime_seconds": run.get("runtime_seconds"),
                "dataw": run.get("counters", {}).get("dataw"),
                "gcdw": run.get("counters", {}).get("gcdw"),
                "recomputed_waf": run.get("recomputed_waf_from_dataw_gcdw"),
            },
            "next": "Use this as exact MiDAS smoke/pressure evidence; repeat with paper-scale traces if enough memory and time are available.",
        }
    if data is None:
        return {
            "status": "missing",
            "summary": "MiDAS preflight has not been run.",
            "next": "Run code/baselines/midas_preflight.py against artifacts/external/MiDAS.",
        }
    if data.get("can_attempt_local_memory_run"):
        return {
            "status": "ready-for-run",
            "summary": "MiDAS artifact structure, tools, and sampled trace format are ready for a local-memory attempt.",
            "evidence": {
                "required_files_ok": all(data.get("required_files", {}).values()),
                "trace_usable": data.get("trace", {}).get("all_sampled_lines_usable"),
            },
            "next": "Run an exact MiDAS artifact experiment or document why only MiDAS-style simulator results are used.",
        }
    return {
        "status": "partial",
        "summary": "MiDAS artifact is present but not ready for a local-memory run.",
        "evidence": {
            "exists": data.get("exists"),
            "required_files_ok": all(data.get("required_files", {}).values()),
            "trace_usable": data.get("trace", {}).get("all_sampled_lines_usable"),
        },
        "next": "Fix missing files/tools/trace compatibility before exact MiDAS execution.",
    }


def acceptance_status(data: dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {
            "status": "missing",
            "summary": "Acceptance report has not been generated.",
            "next": "Run code/sim/acceptance_check.py.",
        }
    passed = data.get("passed_gates")
    total = data.get("total_gates")
    return {
        "status": "passed" if data.get("passed") else "failed",
        "summary": f"{passed}/{total} local simulator/reproducibility gates passed.",
        "next": "Keep this green after adding external replay and exact baseline artifacts.",
    }


def sepbit_status(
    data: dict[str, Any] | None,
    repeat_run: dict[str, Any] | None = None,
    nosep_repeat_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if repeat_run and repeat_run.get("completed"):
        summary = repeat_run.get("summary", {})
        nosep_summary = (nosep_repeat_run or {}).get("summary", {})
        return {
            "status": "done-local-simulator-repeat4",
            "summary": (
                "External SepBIT trace_replay completed on the 1.53M-request PQC repeat4 "
                f"compact trace with WA {summary.get('wa')}; NoSep WA was {nosep_summary.get('wa')}."
            ),
            "evidence": {
                "method": repeat_run.get("method"),
                "selection": repeat_run.get("selection"),
                "requests": summary.get("requests"),
                "ngc": summary.get("ngc"),
                "bytes_to_system": summary.get("bytes_to_system"),
                "bytes_to_storage": summary.get("bytes_to_storage"),
                "runtime_seconds": summary.get("runtime_seconds"),
                "nosep_wa": nosep_summary.get("wa"),
                "nosep_ngc": nosep_summary.get("ngc"),
                "compact_lba": repeat_run.get("adapter_summary", {}).get("compact_lba"),
                "tombstones": repeat_run.get("adapter_summary", {}).get("tombstones"),
            },
            "next": "Use this as exact SepBIT large-trace evidence; keep units separate from native ZNS physical replay.",
        }
    if data and data.get("completed"):
        summary = data.get("summary", {})
        return {
            "status": "done-local-simulator",
            "summary": (
                "External SepBIT trace_replay simulator completed on a PQC pressure trace "
                f"with WA {summary.get('wa')}."
            ),
            "evidence": {
                "method": data.get("method"),
                "selection": data.get("selection"),
                "requests": summary.get("requests"),
                "ngc": summary.get("ngc"),
                "bytes_to_system": summary.get("bytes_to_system"),
                "bytes_to_storage": summary.get("bytes_to_storage"),
                "runtime_seconds": summary.get("runtime_seconds"),
            },
            "next": "Use this as exact SepBIT simulator evidence; repeat on larger traces if needed.",
        }
    return {
        "status": "style-only",
        "summary": "SepBIT-style simulator baseline exists; no separate exact SepBIT artifact run is integrated.",
        "next": "Run the external SepBIT trace_replay simulator or keep SepBIT-style as a heuristic baseline.",
    }


def fast_db_pressure_status(data: dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {
            "status": "missing",
            "summary": "FAST-style Sysbench-OLTP pressure artifact is missing.",
            "next": "Run code/sim/report_fast_db_pressure.py after simulator and physical packed replay.",
        }
    physical = data.get("physical", {})
    comparison = physical.get("hybrid_vs_dogi_secret_group", {})
    rows = physical.get("by_policy_packing", {})
    dogi = rows.get("dogi-history::secret-group", {})
    hybrid = rows.get("quasar-dogi-hybrid::secret-group", {})
    if (
        physical.get("rows", 0) >= 24
        and physical.get("failed_rows", 1) == 0
        and comparison.get("gc_reduction", 0.0) >= 0.90
        and dogi.get("sim_stale_secret_blocks", 0) > 0
        and hybrid.get("sim_stale_secret_blocks", 1) == 0
    ):
        return {
            "status": "done-physical-sysbench-pressure",
            "summary": (
                "FAST-style Sysbench-OLTP pressure replay completed on physical ZNS; "
                "QUASAR-DOGI hybrid keeps stale secrets at zero and sharply reduces GC blocks."
            ),
            "evidence": {
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
            },
            "next": "Use as a stress figure; keep DOGI-paper six-workload suite as the fairness matrix.",
        }
    return {
        "status": "partial-fast-db-pressure",
        "summary": "FAST-style DB pressure artifact exists but does not satisfy the physical replay evidence threshold.",
        "next": "Inspect artifacts/results/fast-db-pressure/sysbench-pressure-summary.md and rerun if needed.",
    }


def fast_ycsb_pressure_status(
    data: dict[str, Any] | None,
    pressure_curve: dict[str, Any] | None = None,
    straggler_baselines: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if data is None:
        return {
            "status": "missing",
            "summary": "FAST/YCSB pressure artifact is missing.",
            "next": "Run code/sim/report_fast_ycsb_pressure.py after simulator and physical packed replay.",
        }
    simulator = data.get("simulator", {})
    physical = data.get("physical", {})
    pressure_workloads = []
    for workload, item in simulator.items():
        policies = item.get("policies", {})
        dogi = policies.get("dogi-history", {})
        hybrid = policies.get("quasar-dogi-hybrid", {})
        if (
            dogi.get("waf", 0.0) > hybrid.get("waf", 0.0)
            and dogi.get("gc_write_blocks", 0) > hybrid.get("gc_write_blocks", 0)
            and dogi.get("stale_secret_blocks_remaining", 0) > 0
            and hybrid.get("stale_secret_blocks_remaining", 1) == 0
        ):
            pressure_workloads.append(workload)
    physical_ok = True
    physical_evidence = {}
    for workload, item in physical.items():
        by_policy = item.get("by_policy", {})
        dogi = by_policy.get("dogi-history", {})
        hybrid = by_policy.get("quasar-dogi-hybrid", {})
        ok = (
            item.get("rows", 0) >= 6
            and item.get("failed_rows", 1) == 0
            and dogi.get("sim_stale_secret_blocks", 0) > 0
            and hybrid.get("sim_stale_secret_blocks", 1) == 0
            and hybrid.get("physical_reset_commands", 0) > 0
        )
        physical_ok = physical_ok and ok
        physical_evidence[workload] = {
            "ok": ok,
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
    straggler_rows = (straggler_baselines or {}).get("summary", {}).get("by_policy_packing", {})
    straggler_evidence = {}
    straggler_ok = bool(straggler_baselines and (straggler_baselines or {}).get("summary", {}).get("failed_rows") == 0)
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
        )
        straggler_ok = straggler_ok and ok
        straggler_evidence[key] = {
            "ok": ok,
            "physical_waf": row.get("physical_waf"),
            "stale_secret_blocks": row.get("sim_stale_secret_blocks"),
            "secret_waiting_end": row.get("secret_blocks_waiting_for_physical_reset"),
            "physical_resets": row.get("physical_reset_commands"),
            "max_live_physical_zones": row.get("max_live_physical_zones"),
        }
    curve_ok = bool(
        pressure_curve
        and pressure_curve.get("failed_rows") == 0
        and pressure_curve.get("row_count", 0) >= 5
        and pressure_curve.get("semantic_gap_rows", 0) >= 5
        and pressure_curve.get("waf_pressure_rows", 0) >= 3
    )
    if (
        len(simulator) >= 4
        and len(pressure_workloads) >= 3
        and len(physical) >= 2
        and physical_ok
        and straggler_ok
        and curve_ok
    ):
        return {
            "status": "done-physical-ycsb-pressure",
            "summary": (
                "FAST/YCSB-A/F pressure sweep completed; representative physical ZNS replays confirm "
                "that high-PQC YCSB can expose DOGI-style WAF/GC and stale-secret failures, and "
                "same-straggler actual-ZNS baseline replay confirms FIFO/SepBIT/MiDAS/DOGI issue no semantic resets. "
                "The actual-ZNS pressure curve includes p2000 as a negative WAF control plus p4000/p8000 pressure points."
            ),
            "evidence": {
                "simulator_workloads": len(simulator),
                "waf_pressure_workloads": pressure_workloads,
                "physical": physical_evidence,
                "pressure_curve": {
                    "row_count": pressure_curve.get("row_count"),
                    "failed_rows": pressure_curve.get("failed_rows"),
                    "semantic_gap_rows": pressure_curve.get("semantic_gap_rows"),
                    "waf_pressure_rows": pressure_curve.get("waf_pressure_rows"),
                },
                "ycsb_f_straggler_baselines": straggler_evidence,
            },
            "next": "Use as DOGI-axis pressure evidence; keep p2000 six-workload suite as fairness evidence.",
        }
    return {
        "status": "partial-fast-ycsb-pressure",
        "summary": "FAST/YCSB pressure artifact exists but does not satisfy the physical replay evidence threshold.",
        "next": "Inspect artifacts/results/fast-ycsb-pressure/ycsb-pressure-summary.md and rerun if needed.",
    }


def actual_zns_overhead_status(data: dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {
            "status": "missing",
            "summary": "Actual-ZNS overhead summary artifact is missing.",
            "next": "Run code/sim/report_actual_zns_overhead.py.",
        }
    by_policy = data.get("by_policy", {})
    dogi = by_policy.get("dogi-history", {})
    hybrid = by_policy.get("quasar-dogi-hybrid", {})
    comparison = data.get("hybrid_vs_dogi", {})
    if (
        data.get("failed_rows") == 0
        and data.get("row_count", 0) >= 80
        and dogi.get("semantic_physical_reset_commands") == 0
        and hybrid.get("semantic_physical_reset_commands", 0) > 0
        and comparison.get("cpu_median_ns_ratio", 99) < 1.0
    ):
        return {
            "status": "done-actual-zns-overhead",
            "summary": (
                "Actual-ZNS helper replay overhead and C-level policy-decision overhead are summarized; "
                "hybrid pays semantic reset work while remaining below DOGI-style MLP decision cost."
            ),
            "evidence": {
                "rows": data.get("row_count"),
                "failed_rows": data.get("failed_rows"),
                "dogi_append_avg_ns": dogi.get("append_avg_ns"),
                "hybrid_append_avg_ns": hybrid.get("append_avg_ns"),
                "dogi_throughput_mib_s": dogi.get("throughput_mib_s"),
                "hybrid_throughput_mib_s": hybrid.get("throughput_mib_s"),
                "hybrid_semantic_reset_delta": comparison.get("semantic_reset_delta"),
                "cpu_median_ns_ratio": comparison.get("cpu_median_ns_ratio"),
            },
            "next": "Use as overhead accounting; xNVMe/SPDK remains optional for lower-overhead latency measurement.",
        }
    return {
        "status": "partial-actual-zns-overhead",
        "summary": "Actual-ZNS overhead artifact exists but does not satisfy the evidence threshold.",
        "next": "Inspect artifacts/results/actual-zns-overhead-summary.md and rerun if needed.",
    }


def security_capability_status(data: dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {
            "status": "missing",
            "summary": "Physical ZNS security/sanitize capability summary is missing.",
            "next": "Run code/quasar/report_zns_security_capability.py.",
        }
    ops = data.get("sanitize_operations_supported", {})
    if data.get("sanitize_execution_validated") or data.get("crypto_erase_executed"):
        return {
            "status": "done-sanitize-validated",
            "summary": (
                "Physical ZNS security capability is recorded and the NVMe crypto-erase sanitize "
                "command path completed successfully. Zone reset alone remains a reclaim/exposure "
                "primitive unless paired with explicit sanitize or equivalent hardware crypto-erase."
            ),
            "evidence": {
                "device_model": data.get("device_model"),
                "sanicap_hex": data.get("sanicap_hex"),
                "crypto_erase": ops.get("crypto_erase"),
                "block_erase": ops.get("block_erase"),
                "overwrite": ops.get("overwrite"),
                "sanitize_log_status": data.get("sanitize_log_status"),
                "sanitize_cdw10_info": data.get("sanitize_cdw10_info"),
                "crypto_erase_executed": data.get("crypto_erase_executed"),
                "sanitize_execution_validated": data.get("sanitize_execution_validated"),
            },
            "next": "Use this as device command-path evidence; do not claim zone reset alone physically erases NAND.",
        }
    if data.get("sanitize_supported") and data.get("claim_boundary"):
        return {
            "status": "done-claim-boundary",
            "summary": (
                "Physical ZNS security capability is recorded; sanitize capability is advertised, "
                "but the paper claim is bounded to reset eligibility unless sanitize/crypto-erase is executed and validated."
            ),
            "evidence": {
                "device_model": data.get("device_model"),
                "sanicap_hex": data.get("sanicap_hex"),
                "crypto_erase": ops.get("crypto_erase"),
                "block_erase": ops.get("block_erase"),
                "overwrite": ops.get("overwrite"),
                "sanitize_log_status": data.get("sanitize_log_status"),
            },
            "next": "Use this wording boundary in the paper; do not claim NAND physical erasure from zone reset alone.",
        }
    return {
        "status": "partial-claim-boundary",
        "summary": "Security capability artifact exists but does not clearly record sanitize support and claim boundary.",
        "next": "Inspect artifacts/results/physical-zns-security-capability.md.",
    }


def claim_matrix_status(data: dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {
            "status": "missing",
            "summary": "QUASAR claim matrix is missing.",
            "next": "Run code/sim/report_claim_matrix.py.",
        }
    by_status = data.get("by_status", {})
    has_boundary_or_validated_sanitize = by_status.get("supported-boundary", 0) >= 1 or any(
        "crypto-erase" in claim.get("paper_wording", "") and "completed successfully" in claim.get("paper_wording", "")
        for claim in data.get("claims", [])
    )
    if (
        data.get("claim_count", 0) >= 8
        and by_status.get("supported", 0) >= 6
        and has_boundary_or_validated_sanitize
        and by_status.get("qualified", 0) >= 1
    ):
        return {
            "status": "done-claim-matrix",
            "summary": "Claim matrix maps paper claims to evidence and forbidden overclaims.",
            "evidence": {
                "claim_count": data.get("claim_count"),
                "by_status": by_status,
            },
            "next": "Use this as the paper writing guardrail.",
        }
    return {
        "status": "partial-claim-matrix",
        "summary": "Claim matrix exists but does not cover supported, qualified, and boundary claims.",
        "next": "Inspect artifacts/results/quasar-claim-matrix.md.",
    }


def workload_hardness_status(data: dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {
            "status": "missing",
            "summary": "Workload hardness matrix is missing.",
            "next": "Run code/sim/report_workload_hardness_matrix.py.",
        }
    claim_gate = next((entry for entry in data.get("entries", []) if entry.get("tier") == "claim-gate"), {})
    claim_evidence = claim_gate.get("evidence", {})
    claim_gate_passed = bool(
        claim_gate.get("passed")
        and claim_evidence.get("eligible_ycsb_pressure_rows", 0) >= 3
        and claim_evidence.get("ycsb_baseline_complete_rows", 0) >= 3
        and claim_evidence.get("db_pressure_eligible") is True
        and claim_evidence.get("eligible_dynamic_rows", 0) >= 2
        and claim_evidence.get("dynamic_baseline_complete_rows", 0) >= 2
    )
    if (
        data.get("passed")
        and data.get("passed_entries") == data.get("total_entries")
        and data.get("total_entries", 0) >= 9
        and data.get("by_tier", {}).get("claim-gate", {}).get("passed", 0) >= 1
        and claim_gate_passed
    ):
        return {
            "status": "done-workload-hardness-matrix",
            "summary": (
                "Workload suite separates DOGI-axis fairness, negative WAF controls, "
                "pressure rows, headline-claim eligibility, and QUASAR-hostile robustness cases."
            ),
            "evidence": {
                "passed_entries": data.get("passed_entries"),
                "total_entries": data.get("total_entries"),
                "by_tier": data.get("by_tier"),
                "claim_gate": claim_evidence,
            },
            "next": "Use this as the benchmark guardrail against relying on an overly easy PQC trace.",
        }
    return {
        "status": "partial-workload-hardness-matrix",
        "summary": "Workload hardness matrix exists but not every required benchmark tier passes.",
        "next": "Inspect artifacts/results/workload-hardness-matrix.md.",
    }


def deployment_selector_status(data: dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {
            "status": "missing",
            "summary": "QUASAR deployment policy selector is missing.",
            "next": "Run code/sim/report_deployment_policy_selector.py.",
        }
    if (
        data.get("passed")
        and data.get("passed_modes") == data.get("total_modes")
        and data.get("default_policy") == "quasar-dogi-hybrid"
    ):
        return {
            "status": "done-deployment-selector",
            "summary": (
                "Deployment selector defines default hybrid, tenant-isolation, strict-residual, "
                "and fallback-overflow modes from measured artifacts."
            ),
            "evidence": {
                "passed_modes": data.get("passed_modes"),
                "total_modes": data.get("total_modes"),
                "default_policy": data.get("default_policy"),
                "hardness_passed": data.get("hardness_passed"),
            },
            "next": "Use this as the implementation policy matrix.",
        }
    return {
        "status": "partial-deployment-selector",
        "summary": "Deployment selector exists but not all modes pass.",
        "next": "Inspect artifacts/results/quasar-deployment-policy-selector.md.",
    }


def reproducibility_manifest_status(data: dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {
            "status": "missing",
            "summary": "QUASAR reproducibility manifest is missing.",
            "next": "Run code/sim/report_reproducibility_manifest.py.",
        }
    if data.get("passed") and data.get("artifact_count", 0) >= 14 and not data.get("missing_or_empty"):
        return {
            "status": "done-reproducibility-manifest",
            "summary": "Reproducibility manifest records actual-ZNS artifacts, hashes, claims, and regeneration commands.",
            "evidence": {
                "artifact_count": data.get("artifact_count"),
                "missing_or_empty": data.get("missing_or_empty"),
                "command_count": len(data.get("commands", [])),
            },
            "next": "Use this as the artifact index when writing or rerunning the paper experiments.",
        }
    return {
        "status": "partial-reproducibility-manifest",
        "summary": "Reproducibility manifest exists but has missing artifacts or insufficient coverage.",
        "next": "Inspect artifacts/results/quasar-reproducibility-manifest.md.",
    }


def reproducibility_validation_status(data: dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {
            "status": "missing",
            "summary": "QUASAR reproducibility validation is missing.",
            "next": "Run code/sim/validate_reproducibility_manifest.py.",
        }
    if data.get("passed") and data.get("mismatch_count") == 0 and data.get("artifact_count", 0) >= 14:
        return {
            "status": "done-reproducibility-validation",
            "summary": "Current artifact files match the reproducibility manifest byte sizes and SHA256 hashes.",
            "evidence": {
                "artifact_count": data.get("artifact_count"),
                "mismatch_count": data.get("mismatch_count"),
            },
            "next": "Regenerate the manifest whenever any indexed artifact is intentionally updated.",
        }
    return {
        "status": "partial-reproducibility-validation",
        "summary": "Current artifacts do not fully match the reproducibility manifest.",
        "next": "Inspect artifacts/results/quasar-reproducibility-validation.md.",
    }


def adaptive_policy_status(data: dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {
            "status": "missing",
            "summary": "Adaptive QUASAR comparison artifact is missing.",
            "next": "Run code/sim/report_adaptive_policy_comparison.py.",
        }
    ycsb = data.get("ycsb_pressure", {})
    sysbench = data.get("sysbench_pressure", {})
    if data.get("decision") == "keep-current-hybrid" and ycsb.get("adaptive_wins", 1) == 0 and sysbench.get("adaptive_wins", 1) == 0:
        return {
            "status": "done-current-hybrid-retained",
            "summary": (
                "Adaptive QUASAR was tested on YCSB/Sysbench pressure workloads and did not beat "
                "the current QUASAR-DOGI hybrid; the default policy remains unchanged."
            ),
            "evidence": {
                "default_policy": data.get("default_policy"),
                "candidate_policy": data.get("candidate_policy"),
                "decision": data.get("decision"),
                "ycsb_current_wins": ycsb.get("current_wins"),
                "ycsb_adaptive_wins": ycsb.get("adaptive_wins"),
                "sysbench_current_wins": sysbench.get("current_wins"),
                "sysbench_adaptive_wins": sysbench.get("adaptive_wins"),
            },
            "next": "Keep adaptive binning as a future multi-tenant/open-zone-budget experiment, not as the default.",
        }
    return {
        "status": "partial-adaptive-comparison",
        "summary": "Adaptive policy comparison exists but does not clearly justify keeping the current default.",
        "next": "Inspect artifacts/results/adaptive-policy-comparison.md before changing policy defaults.",
    }


def multitenant_pressure_status(data: dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {
            "status": "missing",
            "summary": "Multi-tenant pressure artifact is missing.",
            "next": "Run code/sim/report_multitenant_pressure.py after simulator and physical replay.",
        }
    physical = data.get("physical", {})
    rows = physical.get("by_policy", {})
    current = rows.get("quasar-dogi-hybrid", {})
    tenant_mode = rows.get("quasar-adaptive-hybrid", {})
    comparison = physical.get("tenant_isolation_vs_current", {})
    if (
        data.get("decision") == "add-tenant-isolation-mode"
        and physical.get("failed_rows", 1) == 0
        and current.get("sim_stale_secret_blocks", 1) == 0
        and tenant_mode.get("sim_stale_secret_blocks", 1) == 0
        and current.get("reset_secret_tenant_impurity", 0.0) > 0.5
        and tenant_mode.get("reset_secret_tenant_impurity", 1.0) == 0.0
        and comparison.get("reset_secret_tenant_impurity_reduction", 0.0) >= 0.99
    ):
        return {
            "status": "done-physical-multitenant-isolation",
            "summary": (
                "Multi-tenant pressure replay completed; tuned adaptive hybrid eliminates reset-time "
                "secret tenant mixing at measurable reset/open-zone cost."
            ),
            "evidence": {
                "decision": data.get("decision"),
                "rows": physical.get("rows"),
                "failed_rows": physical.get("failed_rows"),
                "current_waf": current.get("sim_waf"),
                "tenant_mode_waf": tenant_mode.get("sim_waf"),
                "current_reset_secret_tenant_impurity": current.get("reset_secret_tenant_impurity"),
                "tenant_mode_reset_secret_tenant_impurity": tenant_mode.get("reset_secret_tenant_impurity"),
                "tenant_mode_physical_resets": tenant_mode.get("physical_reset_commands"),
                "current_physical_resets": current.get("physical_reset_commands"),
                "tenant_mode_max_live_physical_zones": tenant_mode.get("max_live_physical_zones"),
                "current_max_live_physical_zones": current.get("max_live_physical_zones"),
            },
            "next": "Expose this as an optional tenant-isolation mode, not as the default low-overhead policy.",
        }
    return {
        "status": "partial-multitenant-pressure",
        "summary": "Multi-tenant pressure artifact exists but does not satisfy tenant-isolation evidence thresholds.",
        "next": "Inspect artifacts/results/multitenant-pressure/multitenant-pressure-summary.md and rerun if needed.",
    }


def physical_robustness_status(data: dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {
            "status": "missing",
            "summary": "Physical ZNS hint-robustness artifact is missing.",
            "next": "Run code/sim/report_physical_robustness.py after the robustness physical replays.",
        }
    clean = data.get("clean", {})
    dogi = clean.get("dogi", {})
    hybrid = clean.get("hybrid", {})
    missing = data.get("missing_hint_5pct", {}).get("hybrid", {})
    wrong = data.get("wrong_epoch_5pct", {}).get("hybrid", {})
    straggler_exact = data.get("straggler_5pct_exact_secret_group", {})
    straggler_exact_hybrid = straggler_exact.get("hybrid", {})
    straggler_fallback = data.get("straggler_5pct_epoch_bin_4", {})
    straggler_fallback_hybrid = straggler_fallback.get("hybrid", {})
    straggler_residual = data.get("straggler_5pct_epoch_bin_5_residual_12288", {})
    straggler_residual_hybrid = straggler_residual.get("hybrid", {})
    mor = data.get("device_limits", {}).get("mor")
    if (
        data.get("decision") == "add-open-zone-aware-residual-fallback"
        and clean.get("failed_rows") == 0
        and dogi.get("sim_stale_secret_blocks", 0) > 0
        and hybrid.get("sim_stale_secret_blocks", 1) == 0
        and missing.get("sim_stale_secret_blocks", 0) > 0
        and wrong.get("sim_stale_secret_blocks", 1) == 0
        and straggler_exact.get("failed_rows", 0) > 0
        and straggler_exact_hybrid.get("max_live_physical_zones", 0) > (mor or 0)
        and straggler_fallback.get("failed_rows") == 0
        and straggler_fallback_hybrid.get("max_live_physical_zones", 999999) <= (mor or 0)
        and straggler_residual.get("failed_rows") == 0
        and straggler_residual_hybrid.get("max_live_physical_zones", 999999) <= (mor or 0)
        and straggler_residual_hybrid.get("secret_waiting_end", 1) == 0
        and straggler_residual_hybrid.get("residual_migrated_blocks", 0) > 0
    ):
        return {
            "status": "done-physical-hint-robustness",
            "summary": (
                "Physical ZNS robustness replay completed: clean/missing/wrong hints run, "
                "stragglers expose an open-zone-limit failure, and residual epoch-bin fallback completes with zero final secret waiting."
            ),
            "evidence": {
                "device_limits": data.get("device_limits"),
                "clean_dogi_stale": dogi.get("sim_stale_secret_blocks"),
                "clean_hybrid_stale": hybrid.get("sim_stale_secret_blocks"),
                "missing_hybrid_stale": missing.get("sim_stale_secret_blocks"),
                "wrong_hybrid_stale": wrong.get("sim_stale_secret_blocks"),
                "straggler_secret_group_failed_rows": straggler_exact.get("failed_rows"),
                "straggler_secret_group_max_zones": straggler_exact_hybrid.get("max_live_physical_zones"),
                "straggler_epoch_bin_failed_rows": straggler_fallback.get("failed_rows"),
                "straggler_epoch_bin_max_zones": straggler_fallback_hybrid.get("max_live_physical_zones"),
                "straggler_residual_failed_rows": straggler_residual.get("failed_rows"),
                "straggler_residual_max_zones": straggler_residual_hybrid.get("max_live_physical_zones"),
                "straggler_residual_waiting_end": straggler_residual_hybrid.get("secret_waiting_end"),
                "straggler_residual_migrated_blocks": straggler_residual_hybrid.get("residual_migrated_blocks"),
            },
            "next": "Use residual epoch-bin fallback as the open-zone-aware straggler mode; sweep thresholds on more workloads before making it the default.",
        }
    return {
        "status": "partial-physical-hint-robustness",
        "summary": "Physical robustness artifact exists but does not satisfy the fallback evidence thresholds.",
        "next": "Inspect artifacts/results/physical-robustness-ycsb-a-pqc4000/summary.md and rerun if needed.",
    }


def residual_fallback_status(data: dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {
            "status": "missing",
            "summary": "Residual fallback sweep artifact is missing.",
            "next": "Run code/sim/report_residual_fallback_sweep.py after residual fallback dry-runs.",
        }
    physical_by_workload = {row.get("workload"): row for row in data.get("physical_rows", [])}
    physical_by_profile = {
        (row.get("workload"), row.get("profile") or "representative"): row for row in data.get("physical_rows", [])
    }
    candidates = data.get("best_candidates", {})
    ycsb_f_best = (candidates.get("ycsb-f-pqc8000", {}).get("best_zero_wait") or [{}])[0]
    budget_rows = [
        row
        for row in data.get("budget_rows", [])
        if row.get("workload") == "ycsb-f-pqc8000" and row.get("packing") == "epoch-bin-5"
    ]
    budget_physical_rows = [
        row
        for row in data.get("budget_physical_rows", [])
        if row.get("workload") == "ycsb-f-pqc8000" and row.get("packing") == "epoch-bin-5"
    ]
    controller = {
        (row.get("workload"), row.get("profile")): row.get("selected") or {}
        for row in data.get("controller_decisions", [])
    }
    mor = data.get("device_limits", {}).get("mor")
    required = ["exchange-pqc2000", "sysbench-oltp-pqc4000", "ycsb-a-pqc4000"]
    physical_ok = all(
        physical_by_workload.get(workload, {}).get("failed_rows") == 0
        and physical_by_workload.get(workload, {}).get("secret_waiting_end") == 0
        and physical_by_workload.get(workload, {}).get("max_live_physical_zones", 999999) <= (mor or 0)
        for workload in required
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
        len(data.get("controller_decisions", [])) >= 9
        and ycsb_low.get("mode") == "no-residual-copy"
        and ycsb_balanced.get("recommended_copy_budget", 0) > 0
        and ycsb_balanced.get("secret_waiting_end", 10**18) <= 50_000
        and ycsb_strict.get("mode") == "strict-zero-wait"
        and ycsb_strict.get("secret_waiting_end") == 0
    )
    if (
        data.get("decision") == "use-residual-fallback-as-strict-exposure-mode"
        and len(data.get("dryrun_rows", [])) >= 48
        and physical_ok
        and ycsb_f_controller_physical_ok
        and budget_ok
        and budget_physical_ok
        and controller_ok
        and ycsb_f_best.get("physical_waf", 0) >= 3.0
    ):
        return {
            "status": "done-residual-controller-frontier",
            "summary": (
                "Residual fallback sweep completed: strict actual ZNS representatives reach zero final secret waiting, "
                "actual YCSB-F low-overhead, balanced, and strict controller modes were verified on the ZNS device, "
                "YCSB-F shows strict zero-wait mode can be too expensive, "
                "actual copy-budget rows define a bounded-overhead mode, "
                "and the residual controller exposes the WAF/exposure trade-off instead of hiding it."
            ),
            "evidence": {
                "dryrun_rows": len(data.get("dryrun_rows", [])),
                "budget_rows": len(budget_rows),
                "budget_physical_rows": len(budget_physical_rows),
                "controller_decisions": len(data.get("controller_decisions", [])),
                "physical_representatives": {
                    workload: {
                        "physical_waf": physical_by_workload.get(workload, {}).get("physical_waf"),
                        "residual_migrated_blocks": physical_by_workload.get(workload, {}).get(
                            "residual_migrated_blocks"
                        ),
                        "max_live_physical_zones": physical_by_workload.get(workload, {}).get(
                            "max_live_physical_zones"
                        ),
                    }
                    for workload in required
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
                "ycsb_f_strict_physical_waf": ycsb_f_best.get("physical_waf"),
                "ycsb_f_budget_min_waf": min((row.get("physical_waf", 99) for row in budget_rows), default=None),
                "ycsb_f_budget_physical_min_waf": min(
                    (row.get("physical_waf", 99) for row in budget_physical_rows),
                    default=None,
                ),
                "ycsb_f_budget_physical_rows": [
                    {
                        "copy_budget": row.get("copy_budget"),
                        "physical_waf": row.get("physical_waf"),
                        "secret_waiting_end": row.get("secret_waiting_end"),
                        "residual_migrated_blocks": row.get("residual_migrated_blocks"),
                        "residual_migration_budget_skips": row.get("residual_migration_budget_skips"),
                        "max_live_physical_zones": row.get("max_live_physical_zones"),
                    }
                    for row in budget_physical_rows
                ],
                "ycsb_f_controller": {
                    "low_overhead": ycsb_low,
                    "balanced": ycsb_balanced,
                    "strict_zero_wait": ycsb_strict,
                },
            },
            "next": "Use the controller as the deployable policy hook; broaden actual ZNS budget points only if finer-grained WAF/exposure tuning is needed.",
        }
    return {
        "status": "partial-residual-strict-mode-frontier",
        "summary": "Residual fallback sweep exists but does not satisfy the strict-mode frontier thresholds.",
        "next": "Inspect artifacts/results/residual-fallback-sweep/summary.md and rerun missing representatives.",
    }


def build_report(inputs: dict[str, Path]) -> dict[str, Any]:
    loaded = {name: load_json(path) for name, path in inputs.items()}
    components = {
        "acceptance": acceptance_status(loaded["acceptance"]),
        "openssl_oqsprovider": openssl_status(
            loaded["openssl"],
            loaded["openssl_oqsprovider_run"],
            loaded["openssl_oqsprovider_service_run"],
            loaded["openssl_oqsprovider_tls_socket_run"],
        ),
        "zns_fdp_replay": zns_status(
            loaded["zns"],
            loaded["physical_zns"],
            loaded["physical_zonefs_append"],
            loaded["physical_zonefs_replay"],
            loaded["physical_zonefs_suite"],
            loaded["physical_zonefs_write_pressure"],
            loaded["physical_policy_zonefs_replay"],
            loaded["physical_policy_dogi_zonefs_replay"],
            loaded["packed_policy_replay_analysis"],
            loaded["packed_physical_zonefs_replay"],
        ),
        "dogi_exact": dogi_status(
            loaded["dogi_preflight"],
            loaded["dogi_run"],
            loaded["dogi_physical_run"],
            loaded["dogi_physical_suite"],
            loaded["dogi_physical_pressure_run"],
            loaded["dogi_physical_pressure_suite"],
            loaded["dogi_physical_original_lba_run"],
        ),
        "midas_exact": midas_status(loaded["midas"], loaded["midas_run"], loaded["midas_repeat_run"]),
        "sepbit_exact": sepbit_status(
            loaded["sepbit_run"],
            loaded["sepbit_repeat_run"],
            loaded["sepbit_nosep_repeat_run"],
        ),
        "fast_db_pressure": fast_db_pressure_status(loaded["fast_db_pressure"]),
        "fast_ycsb_pressure": fast_ycsb_pressure_status(
            loaded["fast_ycsb_pressure"],
            loaded["ycsb_pressure_curve"],
            loaded["ycsb_f_straggler_baselines"],
        ),
        "actual_zns_overhead": actual_zns_overhead_status(loaded["actual_zns_overhead"]),
        "adaptive_policy": adaptive_policy_status(loaded["adaptive_policy_comparison"]),
        "multitenant_pressure": multitenant_pressure_status(loaded["multitenant_pressure"]),
        "physical_robustness": physical_robustness_status(loaded["physical_robustness"]),
        "residual_fallback": residual_fallback_status(loaded["residual_fallback_sweep"]),
        "security_capability": security_capability_status(loaded["security_capability"]),
        "claim_matrix": claim_matrix_status(loaded["claim_matrix"]),
        "workload_hardness": workload_hardness_status(loaded["workload_hardness"]),
        "deployment_selector": deployment_selector_status(loaded["deployment_selector"]),
        "reproducibility_manifest": reproducibility_manifest_status(loaded["reproducibility_manifest"]),
        "reproducibility_validation": reproducibility_validation_status(loaded["reproducibility_validation"]),
    }
    blockers = [
        name
        for name, item in components.items()
        if item["status"] in {"blocked", "missing", "failed"} or str(item["status"]).startswith("blocked")
    ]
    pending = [
        name
        for name, item in components.items()
        if item["status"] in {"partial", "ready-for-run", "style-only"} or str(item["status"]).startswith("partial")
    ]
    return {
        "inputs": {name: str(path) for name, path in inputs.items()},
        "components": components,
        "paper_ready_external": not blockers and not pending,
        "blockers": blockers,
        "pending": pending,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# External Readiness Report",
        "",
        f"- Paper-ready external status: `{report['paper_ready_external']}`",
        f"- Blocking components: {', '.join(report['blockers']) if report['blockers'] else 'none'}",
        f"- Pending/partial components: {', '.join(report['pending']) if report['pending'] else 'none'}",
        "",
        "| Component | Status | Summary | Next Step |",
        "| --- | --- | --- | --- |",
    ]
    for name, item in report["components"].items():
        lines.append(
            "| {name} | `{status}` | {summary} | {next_step} |".format(
                name=name,
                status=item["status"],
                summary=str(item["summary"]).replace("|", "\\|"),
                next_step=str(item["next"]).replace("|", "\\|"),
            )
        )
    lines.append("")
    lines.append("This report is conservative: simulator acceptance can pass while external paper-grade evidence remains pending.")
    return "\n".join(lines) + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/external-readiness.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/external-readiness.md"))
    args = parser.parse_args()

    report = build_report(DEFAULT_INPUTS)
    write_json(args.out, report)
    write_text(args.markdown_out, markdown(report))
    print(json.dumps({"paper_ready_external": report["paper_ready_external"], "blockers": report["blockers"], "pending": report["pending"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
