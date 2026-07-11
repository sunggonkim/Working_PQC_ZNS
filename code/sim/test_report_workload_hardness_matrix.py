import unittest

try:
    import report_workload_hardness_matrix as hardness
except ModuleNotFoundError:  # pragma: no cover
    from sim import report_workload_hardness_matrix as hardness


class WorkloadHardnessMatrixTests(unittest.TestCase):
    def test_summarize_requires_negative_pressure_and_hostile_rows(self) -> None:
        fair = {
            "execute": True,
            "summary": {
                "row_count": 72,
                "failed_rows": 0,
                "by_policy_packing": {
                    "dogi-history::secret-group": {
                        "sim_waf": 1.0,
                        "sim_stale_secret_blocks": 100,
                        "physical_reset_commands": 0,
                    },
                    "quasar-dogi-hybrid::secret-group": {
                        "sim_waf": 1.0,
                        "sim_stale_secret_blocks": 0,
                        "physical_reset_commands": 10,
                    },
                },
            },
        }
        dogi_eval_rows = []
        for workload in [
            "fio-zipf-pqc0000",
            "ycsb-a-pqc0000",
            "ycsb-f-pqc0000",
            "varmail-pqc0000",
            "alibaba-pqc0000",
        ]:
            dogi_eval_rows.extend(
                [
                    {
                        "workload": workload,
                        "policy": "fifo",
                        "waf": 1.2,
                        "stale_secret_blocks_remaining": 0,
                    },
                    {
                        "workload": workload,
                        "policy": "quasar",
                        "waf": 1.2,
                        "stale_secret_blocks_remaining": 0,
                    },
                    {
                        "workload": workload,
                        "policy": "dogi-history",
                        "waf": 1.05,
                        "stale_secret_blocks_remaining": 0,
                    },
                    {
                        "workload": workload,
                        "policy": "quasar-dogi-hybrid",
                        "waf": 1.05,
                        "stale_secret_blocks_remaining": 0,
                    },
                ]
            )
        ycsb_curve = {
            "row_count": 4,
            "failed_rows": 0,
            "waf_pressure_rows": 3,
            "semantic_gap_rows": 4,
            "rows": [
                {
                    "pqc_level": 2000,
                    "workloads": ["ycsb-a-pqc2000", "ycsb-f-pqc2000"],
                    "waf_pressure": False,
                    "semantic_gap": True,
                    "dogi_waf": 1.0,
                    "hybrid_waf": 1.0,
                    "dogi_gc_blocks": 0,
                    "hybrid_gc_blocks": 0,
                    "dogi_stale_secret_blocks": 10,
                    "hybrid_stale_secret_blocks": 0,
                    "hybrid_semantic_resets": 2,
                },
                {
                    "pqc_level": 4000,
                    "workloads": ["ycsb-a-pqc4000"],
                    "waf_pressure": True,
                    "semantic_gap": True,
                    "dogi_gc_blocks": 10,
                    "dogi_stale_secret_blocks": 20,
                    "hybrid_stale_secret_blocks": 0,
                },
                {
                    "pqc_level": 8000,
                    "workloads": ["ycsb-a-pqc8000"],
                    "waf_pressure": True,
                    "semantic_gap": True,
                    "dogi_gc_blocks": 11,
                    "dogi_stale_secret_blocks": 30,
                    "hybrid_stale_secret_blocks": 0,
                },
                {
                    "pqc_level": 8000,
                    "workloads": ["ycsb-f-pqc8000"],
                    "waf_pressure": True,
                    "semantic_gap": True,
                    "dogi_gc_blocks": 12,
                    "dogi_stale_secret_blocks": 40,
                    "hybrid_stale_secret_blocks": 0,
                },
            ],
        }
        for row in ycsb_curve["rows"]:
            row["baseline_semantic_failures"] = {
                "fifo": {"stale_secret_blocks": 1, "semantic_resets": 0},
                "sepbit-style": {"stale_secret_blocks": 1, "semantic_resets": 0},
                "midas-style": {"stale_secret_blocks": 1, "semantic_resets": 0},
                "dogi-history": {"stale_secret_blocks": 1, "semantic_resets": 0},
            }
        fast_db = {
            "physical": {
                "failed_rows": 0,
                "rows": 24,
                "hybrid_vs_dogi_secret_group": {
                    "gc_reduction": 0.8,
                    "waf_reduction": 0.1,
                    "stale_secret_reduction_blocks": 50,
                },
            }
        }
        dynamic_pressure = {
            "physical": [
                {
                    "failed_rows": 0,
                    "path": "exchange-pqc8000",
                    "hybrid_vs_dogi": {
                        "gc_reduction": 0.99,
                        "stale_secret_reduction_blocks": 100,
                    },
                    "policies": {
                        "fifo": {},
                        "sepbit-style": {},
                        "midas-style": {},
                        "quasar": {},
                        "dogi-history": {
                            "sim_waf": 1.08,
                            "sim_gc_blocks": 100,
                            "sim_stale_secret_blocks": 100,
                        },
                        "quasar-dogi-hybrid": {
                            "sim_waf": 1.00,
                            "sim_gc_blocks": 1,
                            "sim_stale_secret_blocks": 0,
                        },
                    },
                },
                {
                    "failed_rows": 0,
                    "path": "varmail-pqc8000",
                    "hybrid_vs_dogi": {
                        "gc_reduction": 0.80,
                        "stale_secret_reduction_blocks": 80,
                    },
                    "policies": {
                        "fifo": {},
                        "sepbit-style": {},
                        "midas-style": {},
                        "quasar": {},
                        "dogi-history": {
                            "sim_waf": 1.07,
                            "sim_gc_blocks": 80,
                            "sim_stale_secret_blocks": 80,
                        },
                        "quasar-dogi-hybrid": {
                            "sim_waf": 1.00,
                            "sim_gc_blocks": 2,
                            "sim_stale_secret_blocks": 0,
                        },
                    },
                },
            ]
        }
        multitenant = {
            "decision": "add-tenant-isolation-mode",
            "physical": {
                "failed_rows": 0,
                "tenant_isolation_vs_current": {
                    "reset_secret_tenant_impurity_reduction": 1.0,
                    "waf_increase": 0.01,
                },
            },
        }
        robustness = {
            "decision": "add-open-zone-aware-residual-fallback",
            "missing_hint_5pct": {"failed_rows": 0, "hybrid": {"secret_waiting_end": 1}},
            "wrong_epoch_5pct": {"failed_rows": 0, "hybrid": {"secret_waiting_end": 0}},
            "straggler_5pct_exact_secret_group": {"failed_rows": 1, "hybrid": {"secret_waiting_end": 20}},
            "straggler_5pct_epoch_bin_5_residual_12288": {
                "failed_rows": 0,
                "hybrid": {"secret_waiting_end": 0, "physical_waf": 1.7},
            },
        }
        residual = {
            "decision": "use-profiled-residual-controller",
            "physical_rows": [
                {"workload": "exchange-pqc2000"},
                {"workload": "sysbench-oltp-pqc4000"},
                {"workload": "ycsb-a-pqc4000"},
                {
                    "workload": "ycsb-f-pqc8000",
                    "profile": "strict_zero_wait",
                    "secret_waiting_end": 0,
                    "physical_waf": 3.5,
                    "residual_migrated_blocks": 100,
                },
            ],
        }

        summary = hardness.summarize(
            fair,
            dogi_eval_rows,
            ycsb_curve,
            fast_db,
            dynamic_pressure,
            multitenant,
            robustness,
            residual,
        )
        text = hardness.markdown(summary)

        self.assertTrue(summary["passed"])
        self.assertEqual(summary["passed_entries"], summary["total_entries"])
        self.assertIn("DOGI-favorable", text)
        self.assertIn("Main WAF/GC claim eligibility", text)
        self.assertIn("negative WAF control", text)
        self.assertIn("universal WAF dominance", text)

    def test_main_claim_gate_rejects_easy_rows_without_dynamic_pressure(self) -> None:
        ycsb_curve = {
            "rows": [
                {
                    "pqc_level": 2000,
                    "waf_pressure": False,
                    "semantic_gap": True,
                    "dogi_gc_blocks": 0,
                    "dogi_stale_secret_blocks": 10,
                    "hybrid_stale_secret_blocks": 0,
                    "baseline_semantic_failures": {
                        "fifo": {},
                        "sepbit-style": {},
                        "midas-style": {},
                        "dogi-history": {},
                    },
                }
            ]
        }
        fast_db = {
            "physical": {
                "failed_rows": 0,
                "hybrid_vs_dogi_secret_group": {
                    "gc_reduction": 0.9,
                    "stale_secret_reduction_blocks": 10,
                },
            }
        }

        entry = hardness.main_claim_eligibility(ycsb_curve, fast_db, {"physical": []})

        self.assertFalse(entry["passed"])
        self.assertEqual(entry["evidence"]["eligible_ycsb_pressure_rows"], 0)
        self.assertEqual(entry["evidence"]["eligible_dynamic_rows"], 0)

    def test_main_claim_gate_rejects_rows_missing_baseline_coverage(self) -> None:
        ycsb_curve = {
            "rows": [
                {
                    "pqc_level": 4000,
                    "workloads": ["ycsb-a-pqc4000"],
                    "waf_pressure": True,
                    "semantic_gap": True,
                    "dogi_gc_blocks": 10,
                    "dogi_stale_secret_blocks": 20,
                    "hybrid_stale_secret_blocks": 0,
                    "baseline_semantic_failures": {
                        "dogi-history": {},
                    },
                }
                for _ in range(3)
            ]
        }
        fast_db = {
            "physical": {
                "failed_rows": 0,
                "hybrid_vs_dogi_secret_group": {
                    "gc_reduction": 0.9,
                    "stale_secret_reduction_blocks": 10,
                },
            }
        }
        dynamic_pressure = {
            "physical": [
                {
                    "failed_rows": 0,
                    "hybrid_vs_dogi": {
                        "gc_reduction": 0.9,
                        "stale_secret_reduction_blocks": 10,
                    },
                    "policies": {
                        "dogi-history": {"sim_gc_blocks": 10, "sim_stale_secret_blocks": 10},
                        "quasar-dogi-hybrid": {"sim_stale_secret_blocks": 0},
                    },
                }
                for _ in range(2)
            ]
        }

        entry = hardness.main_claim_eligibility(ycsb_curve, fast_db, dynamic_pressure)

        self.assertFalse(entry["passed"])
        self.assertEqual(entry["evidence"]["ycsb_baseline_complete_rows"], 0)
        self.assertEqual(entry["evidence"]["dynamic_baseline_complete_rows"], 0)


if __name__ == "__main__":
    unittest.main()
