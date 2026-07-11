import unittest

try:
    import report_component_ablation as ablation
except ModuleNotFoundError:  # pragma: no cover
    from sim import report_component_ablation as ablation


class ComponentAblationTests(unittest.TestCase):
    def test_summary_extracts_component_and_fallback_decisions(self) -> None:
        ycsb = {
            "physical": {
                "ycsb-a-pqc4000": {
                    "by_policy": {
                        "dogi-history": {
                            "sim_waf": 1.04,
                            "sim_gc_blocks": 100,
                            "sim_stale_secret_blocks": 50,
                            "secret_blocks_waiting_for_physical_reset": 10,
                            "physical_reset_commands": 0,
                            "avg_space_utilization": 0.2,
                            "max_live_physical_zones": 8,
                        },
                        "quasar": {
                            "sim_waf": 1.01,
                            "sim_gc_blocks": 10,
                            "sim_stale_secret_blocks": 0,
                            "secret_blocks_waiting_for_physical_reset": 0,
                            "physical_reset_commands": 2,
                            "avg_space_utilization": 0.6,
                            "max_live_physical_zones": 6,
                        },
                        "quasar-dogi-hybrid": {
                            "sim_waf": 1.0,
                            "sim_gc_blocks": 0,
                            "sim_stale_secret_blocks": 0,
                            "secret_blocks_waiting_for_physical_reset": 0,
                            "physical_reset_commands": 2,
                            "avg_space_utilization": 0.6,
                            "max_live_physical_zones": 6,
                        },
                    }
                }
            }
        }
        sysbench = {
            "physical": {
                "by_policy_packing": {
                    "dogi-history::secret-group": {
                        "sim_waf": 1.03,
                        "sim_gc_blocks": 40,
                        "sim_stale_secret_blocks": 20,
                    },
                    "quasar::secret-group": {
                        "sim_waf": 1.02,
                        "sim_gc_blocks": 8,
                        "sim_stale_secret_blocks": 0,
                    },
                    "quasar-dogi-hybrid::secret-group": {
                        "sim_waf": 1.0,
                        "sim_gc_blocks": 1,
                        "sim_stale_secret_blocks": 0,
                    },
                }
            }
        }
        dynamic = {
            "physical": [
                {
                    "path": "exchange-pqc8000",
                    "policies": {
                        "dogi-history": {
                            "sim_waf": 1.08,
                            "sim_gc_blocks": 80,
                            "sim_stale_secret_blocks": 30,
                        },
                        "quasar": {
                            "sim_waf": 1.01,
                            "sim_gc_blocks": 4,
                            "sim_stale_secret_blocks": 0,
                        },
                        "quasar-dogi-hybrid": {
                            "sim_waf": 1.0,
                            "sim_gc_blocks": 0,
                            "sim_stale_secret_blocks": 0,
                        },
                    },
                }
            ]
        }
        adaptive = {
            "decision": "keep-current-hybrid",
            "decision_reason": "current wins",
            "ycsb_pressure": {"current_wins": 1, "adaptive_wins": 0, "ties": 0},
            "sysbench_pressure": {"current_wins": 1, "adaptive_wins": 0, "ties": 0},
        }
        robustness = {
            "device_limits": {"mor": 13},
            "straggler_5pct_exact_secret_group": {
                "failed_rows": 1,
                "hybrid": {"secret_waiting_end": 40, "max_live_physical_zones": 30},
            },
            "straggler_5pct_epoch_bin_4": {
                "failed_rows": 0,
                "hybrid": {"secret_waiting_end": 40, "max_live_physical_zones": 13},
            },
            "straggler_5pct_epoch_bin_5_residual_12288": {
                "failed_rows": 0,
                "hybrid": {
                    "physical_waf": 1.7,
                    "secret_waiting_end": 0,
                    "residual_migrated_blocks": 200,
                    "max_live_physical_zones": 13,
                },
            },
        }
        residual = {
            "physical_rows": [
                {
                    "workload": "ycsb-f-pqc8000",
                    "profile": "strict_zero_wait",
                    "physical_waf": 3.5,
                    "secret_waiting_end": 0,
                    "residual_migrated_blocks": 1000,
                }
            ]
        }

        summary = ablation.summarize(ycsb, sysbench, dynamic, adaptive, robustness, residual)
        self.assertEqual(summary["adaptive_admission"]["current_wins"], 2)
        self.assertEqual(summary["adaptive_admission"]["adaptive_wins"], 0)
        self.assertEqual(summary["residual_fallback"]["epoch_bin_with_residual"]["secret_waiting_end"], 0)

        deltas = [row for row in summary["main_components"] if row["policy"] == "component delta"]
        self.assertEqual(len(deltas), 3)
        self.assertAlmostEqual(deltas[0]["dogi_to_quasar_gc_reduction"], 0.9)
        self.assertEqual(deltas[0]["dogi_to_hybrid_stale_reduction_blocks"], 50)
        self.assertIn("Lifecycle hints", ablation.markdown(summary))


if __name__ == "__main__":
    unittest.main()
