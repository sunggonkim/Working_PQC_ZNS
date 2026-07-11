import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

try:
    import acceptance_check as accept
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from sim import acceptance_check as accept


class AcceptanceCheckTests(unittest.TestCase):
    def test_workload_hardness_gate_requires_claim_gate(self) -> None:
        base = {
            "passed": True,
            "passed_entries": 9,
            "total_entries": 9,
            "by_tier": {
                "fairness": {"passed": 1, "total": 1},
                "negative-control": {"passed": 2, "total": 2},
                "pressure": {"passed": 2, "total": 2},
                "claim-gate": {"passed": 1, "total": 1},
                "hostile-robustness": {"passed": 3, "total": 3},
            },
            "entries": [
                {"tier": "fairness", "name": "fair", "passed": True},
                {"tier": "negative-control", "name": "negative", "passed": True},
                {"tier": "pressure", "name": "pressure", "passed": True},
                {
                    "tier": "claim-gate",
                    "name": "Main WAF/GC claim eligibility gate",
                    "passed": True,
                    "evidence": {
                        "eligible_ycsb_pressure_rows": 5,
                        "ycsb_baseline_complete_rows": 5,
                        "db_pressure_eligible": True,
                        "eligible_dynamic_rows": 3,
                        "dynamic_baseline_complete_rows": 3,
                    },
                },
                {"tier": "hostile-robustness", "name": "hostile", "passed": True},
            ],
        }

        self.assertTrue(accept.gate_workload_hardness_matrix(base).passed)

        weak = dict(base)
        weak["entries"] = [dict(entry) for entry in base["entries"]]
        weak["entries"][3] = {
            **weak["entries"][3],
            "evidence": {
                "eligible_ycsb_pressure_rows": 5,
                "ycsb_baseline_complete_rows": 5,
                "db_pressure_eligible": True,
                "eligible_dynamic_rows": 0,
                "dynamic_baseline_complete_rows": 0,
            },
        }

        self.assertFalse(accept.gate_workload_hardness_matrix(weak).passed)

    def test_acceptance_gates_pass_on_minimal_fixture(self) -> None:
        e1 = [
            {"workload": "w1", "policy": "dogi-history", "waf": 2.0},
            {"workload": "w1", "policy": "quasar", "waf": 1.1, "zone_utilization": 0.9},
            {"workload": "w2", "policy": "dogi-history", "waf": 2.0},
            {"workload": "w2", "policy": "quasar", "waf": 1.1, "zone_utilization": 0.9},
            {"workload": "w3", "policy": "dogi-history", "waf": 2.0},
            {"workload": "w3", "policy": "quasar", "waf": 1.1, "zone_utilization": 0.9},
        ]
        e5 = [
            {
                "policy": "quasar",
                "hint_missing_rate": 0.05,
                "wrong_epoch_rate": 0.0,
                "straggler_rate": 0.0,
                "waf": 1.02,
                "failed_gc_attempts": 0,
            }
        ]
        timeline = [
            {"policy": "fifo", "ts": 0, "stale_secret_blocks": 10},
            {"policy": "dogi-history", "ts": 0, "stale_secret_blocks": 8},
            {"policy": "quasar", "ts": 0, "stale_secret_blocks": 1},
            {"policy": "quasar", "ts": 1, "stale_secret_blocks": 0},
        ]
        dogi_adapter = {"dogi_lines": 10, "dogi_tombstones": 3}
        dogi_preflight = {
            "repo": {"parser_matches_adapter": True},
            "trace": {"all_lines_usable": True},
            "can_run_full_prototype": False,
        }
        mixed = [
            {
                "policy": "dogi-history",
                "dogi_feature_count": 6,
                "dogi_uses_lba": 1,
                "dogi_uses_freq_bit": 1,
                "dogi_uses_freq_bit2": 1,
                "dogi_uses_interval_bit": 1,
                "dogi_uses_seg_accessed": 1,
                "dogi_uses_prev_lba": 1,
                "dogi_feature_samples": 10,
                "prediction_samples": 10,
                "dogi_runtime_feature_keys": 4,
            }
        ]
        liboqs_summary = {
            "sessions": 1,
            "all_kem_ok": True,
            "all_sig_ok": True,
            "kem": "ML-KEM-512",
            "sig": "ML-DSA-44",
        }
        liboqs_verification = [
            {"policy": "dogi-history", "waf": 1.5},
            {"policy": "quasar", "waf": 1.1, "stale_secret_blocks_remaining": 0},
        ]
        file_zns_summary = {
            "backend": "file-zns",
            "dry_run_only": False,
            "append_commands": 10,
            "emulator_append_commands": 10,
            "reset_family_commands": 2,
            "emulator_reset_commands": 2,
            "emulator_reset_zones": 3,
            "emulator_final_used_zones": 5,
            "emulator_zone_count": 8,
        }
        nullblk_summary = {
            "backend": "blkzone-zns",
            "real_backend": "blkzone-zns",
            "real_device": "/dev/nullb_quasar",
            "dry_run_only": False,
            "append_blocks": 10,
            "append_commands": 10,
            "real_append_commands": 10,
            "reset_family_commands": 2,
            "real_reset_commands": 2,
            "real_reset_zones": 2,
            "real_bytes_written": 40960,
            "real_final_used_zones": 3,
            "real_zone_count": 8,
        }
        physical_zonefs_replay = {
            "execute": True,
            "reset_issued": False,
            "append_commands": 12,
            "bytes_written": 49152,
            "zone_files_used": 3,
            "unique_families": 3,
            "latency": {"p99_ns": 1000},
        }
        physical_zonefs_write_pressure = {
            "execute": True,
            "failed": False,
            "scale": 10,
            "summary": {
                "all_passed": True,
                "row_count": 30,
                "total_bytes_written": 128 * 1024 * 1024 * 1024,
                "dogi_vs_hybrid": {
                    "hybrid_block_reduction_vs_dogi": 0.04,
                    "stale_secret_blocks_avoided": 100,
                },
            },
        }
        physical_policy_zonefs_replay = {
            "execute": True,
            "summary": {
                "row_count": 20,
                "failed_rows": 0,
                "by_policy": {
                    "dogi-history": {
                        "sim_stale_secret_blocks": 10,
                        "physical_resets": 0,
                        "max_active_zone_files": 7,
                    },
                    "quasar": {
                        "sim_stale_secret_blocks": 0,
                        "physical_resets": 8,
                        "max_active_zone_files": 12,
                    },
                    "quasar-dogi-hybrid": {
                        "sim_stale_secret_blocks": 0,
                        "physical_resets": 8,
                        "max_active_zone_files": 12,
                    },
                },
                "dogi_vs_hybrid": {
                    "hybrid_block_reduction_vs_dogi": 0.0,
                    "stale_secret_blocks_avoided": 10,
                },
            },
        }
        physical_policy_dogi_zonefs_replay = {
            "execute": True,
            "zone_capacity": 275_712,
            "summary": {
                "row_count": 30,
                "failed_rows": 0,
                "by_policy": {
                    "dogi-history": {
                        "sim_stale_secret_blocks": 100,
                        "physical_resets": 0,
                        "max_open_zone_files": 6,
                        "max_allocated_zone_files": 6,
                    },
                    "quasar": {
                        "sim_stale_secret_blocks": 0,
                        "physical_resets": 10,
                        "max_open_zone_files": 7,
                        "max_allocated_zone_files": 7,
                    },
                    "quasar-dogi-hybrid": {
                        "sim_stale_secret_blocks": 0,
                        "physical_resets": 10,
                        "max_open_zone_files": 12,
                        "max_allocated_zone_files": 12,
                    },
                },
                "dogi_vs_hybrid": {
                    "hybrid_block_reduction_vs_dogi": 0.0,
                    "stale_secret_blocks_avoided": 100,
                },
            },
        }
        packed_policy_replay_analysis = {
            "physical_zones": 905,
            "physical_zone_capacity": 275_712,
            "logical_zone_capacity": 512,
            "summary": {
                "row_count": 120,
                "failed_rows": 0,
                "by_policy_packing": {
                    "quasar-dogi-hybrid::any": {
                        "secret_blocks_waiting_for_physical_reset": 100,
                        "delayed_reset_ratio": 1.0,
                    },
                    "quasar-dogi-hybrid::group": {
                        "secret_blocks_waiting_for_physical_reset": 0,
                        "max_live_physical_zones": 12,
                        "max_secret_blocks_waiting_for_physical_reset": 20,
                    },
                    "quasar-dogi-hybrid::logical-zone": {
                        "secret_blocks_waiting_for_physical_reset": 0,
                        "delayed_reset_ratio": 0.0,
                        "max_live_physical_zones": 390,
                    },
                },
            },
        }
        nullblk_plan = {
            "create_commands": [
                "sudo modprobe null_blk configfs=1",
                "echo 1 | sudo tee /sys/kernel/config/nullb/nullb_quasar/zoned >/dev/null",
                "echo 64 | sudo tee /sys/kernel/config/nullb/nullb_quasar/zone_size >/dev/null",
                "echo 1 | sudo tee /sys/kernel/config/nullb/nullb_quasar/power >/dev/null",
            ]
        }
        nullblk_preflight = {
            "configfs_parent_exists": True,
            "null_blk_module_available": True,
            "can_create_without_sudo": False,
        }
        dogi_nullblk_preflight = {
            "device": "/dev/nullb_quasar",
            "can_configure_build": True,
            "can_run_full_prototype": True,
            "trace": {"all_lines_usable": True},
        }
        dogi_physical_run = {
            "completed": True,
            "trace_path": "/tmp/compact.dogi",
            "placement_name": "DOGI",
            "selection_algorithm": "DogiSelect",
            "saw_zenfs_mount": True,
            "saw_dogi_select": True,
            "waf": 2.0,
            "user_write_gib": 1.0,
            "gc_write_gib": 1.0,
        }
        dogi_physical_suite = {
            "completed": True,
            "workloads": 6,
            "logical_size_gb": 2,
            "aggregate_waf": 2.0,
            "avg_waf": 2.0,
            "total_user_write_gib": 6.0,
            "total_gc_write_gib": 6.0,
            "rows": [
                {"completed": True, "selection_algorithm": "DogiSelect"}
                for _ in range(6)
            ],
        }
        dogi_physical_pressure_suite = {
            "completed_runs": 3,
            "total_runs": 3,
            "device": "/dev/nvme0n1",
            "logical_size_gb": 2,
            "scheduler": "mq-deadline",
            "dogi_waf": 2.9,
            "best_placement": "CostBenefit",
            "best_waf": 2.7,
            "rows": [
                {"placement": "DOGI", "completed": True, "waf": 2.9, "saw_zenfs_mount": True},
                {"placement": "Greedy", "completed": True, "waf": 2.8, "saw_zenfs_mount": True},
                {"placement": "CostBenefit", "completed": True, "waf": 2.7, "saw_zenfs_mount": True},
            ],
        }
        midas_exact_repeat4 = {
            "completed": True,
            "returncode": 0,
            "total_waf": 1.01,
            "recomputed_waf_from_dataw_gcdw": 1.012,
            "runtime_seconds": 6.0,
            "progress_reports": [{"total_waf": 1.0} for _ in range(6)],
            "counters": {"dataw": 100, "gcdw": 1},
            "adapter_summary": {
                "compact_lba": True,
                "dogi_lines": 1_500_000,
                "dogi_tombstones": 600_000,
                "compact_span_blocks": 80_000,
                "user_write_bytes": 4 * 1024 * 1024 * 1024,
            },
        }
        sepbit_exact_repeat4 = {
            "completed": True,
            "returncode": 0,
            "adapter_summary": {
                "compact_lba": True,
                "compact_span_blocks": 80_000,
                "tombstones": 600_000,
            },
            "summary": {
                "requests": 1_500_000,
                "ngc": 100,
                "wa": 2.4,
                "runtime_seconds": 14.0,
            },
        }
        sepbit_nosep_repeat4 = {
            "completed": True,
            "returncode": 0,
            "summary": {
                "requests": 1_500_000,
                "ngc": 100,
                "wa": 3.7,
                "runtime_seconds": 13.0,
            },
        }
        c_policy_overhead = {
            "rows": [
                {"policy": "dogi-mlp", "ns_per_write_median": 200.0},
                {"policy": "quasar-hint", "ns_per_write_median": 20.0},
                {"policy": "quasar-dogi-hybrid", "ns_per_write_median": 100.0},
            ],
            "aggregate": {
                "dogi-mlp": {"traces": 1, "median_ns_per_write": 200.0},
                "quasar-hint": {"traces": 1, "median_ns_per_write": 20.0},
                "quasar-dogi-hybrid": {"traces": 1, "median_ns_per_write": 100.0},
            },
        }
        crash_model = {
            "summary": {
                "failed_cases": 0,
                "passed_cases": 5,
                "cases": 5,
                "unsafe_reset_attempted": False,
            },
            "metadata_cost": {
                "metadata_bytes": {"total": 1024},
                "metadata_overhead_percent_of_user_bytes": 0.1,
                "recovery_scan": {"estimated_scan_zones": 4, "estimated_scan_ms": 0.01},
            },
        }
        fdp_mapping = {
            "runs": [
                {
                    "handles": 64,
                    "family_count": 10,
                    "occupied_handles": 8,
                    "family_purity": 0.95,
                    "intent_purity": 0.97,
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmp:
            figures = Path(tmp)
            for name in [
                "e1-waf.png",
                "e2-waf-vs-utilization.png",
                "e3-service-cost.png",
                "e4-exposure.png",
                "e4-exposure-timeline.png",
                "e5-bad-hints.png",
                "actual-zns/ycsb-pressure-waf-stale.png",
                "actual-zns/overhead-accounting.png",
                "actual-zns/workload-hardness.png",
            ]:
                (figures / name).parent.mkdir(parents=True, exist_ok=True)
                (figures / name).write_bytes(b"png")

            gates = [
                accept.gate_quasar_beats_dogi(e1, 3),
                accept.gate_waf_and_utilization(e1),
                accept.gate_bad_hints(e5, 1.05),
                accept.gate_exposure_window(timeline),
                accept.gate_dogi_baseline(dogi_adapter, dogi_preflight),
                accept.gate_dogi_feature_coverage(mixed),
                accept.gate_liboqs_trace(liboqs_summary, liboqs_verification),
                accept.gate_file_zns_replay(file_zns_summary),
                accept.gate_real_nullblk_replay(nullblk_summary),
                accept.gate_physical_zonefs_replay(physical_zonefs_replay),
                accept.gate_physical_zonefs_write_pressure(physical_zonefs_write_pressure),
                accept.gate_physical_policy_zonefs_replay(physical_policy_zonefs_replay),
                accept.gate_physical_policy_dogi_zonefs_replay(physical_policy_dogi_zonefs_replay),
                accept.gate_packed_policy_replay_analysis(packed_policy_replay_analysis),
                accept.gate_dogi_nullblk_preflight(dogi_nullblk_preflight),
                accept.gate_dogi_physical_compact_run(dogi_physical_run),
                accept.gate_dogi_physical_full_suite(dogi_physical_suite),
                accept.gate_dogi_physical_pressure_suite(dogi_physical_pressure_suite),
                accept.gate_midas_exact_repeat4(midas_exact_repeat4),
                accept.gate_sepbit_exact_repeat4(sepbit_exact_repeat4, sepbit_nosep_repeat4),
                accept.gate_nullblk_path(nullblk_plan, nullblk_preflight),
                accept.gate_figures(figures),
                accept.gate_c_policy_overhead(c_policy_overhead),
                accept.gate_crash_recovery_cost(crash_model),
                accept.gate_fdp_mapping(fdp_mapping),
            ]

        self.assertTrue(all(gate.passed for gate in gates))


if __name__ == "__main__":
    unittest.main()
