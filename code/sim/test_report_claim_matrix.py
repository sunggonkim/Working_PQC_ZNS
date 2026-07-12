import unittest

try:
    import report_claim_matrix as claim_matrix
except ModuleNotFoundError:  # pragma: no cover
    from sim import report_claim_matrix as claim_matrix


class ClaimMatrixTests(unittest.TestCase):
    def test_build_claims_contains_boundaries(self) -> None:
        unified = {
            "same_path_physical_zns": {"rows": 1, "failed_rows": 0},
            "ycsb_pressure_curve": {"semantic_gap_rows": 5, "row_count": 5, "waf_pressure_rows": 3},
            "fast_db_pressure": {"hybrid_vs_dogi": {"stale_secret_reduction_blocks": 10, "gc_reduction": 0.9}},
            "residual_fallback_sweep": {"decision": "controller-frontier-ready", "budget_physical_rows": [1, 2]},
            "actual_zns_overhead": {
                "row_count": 10,
                "failed_rows": 0,
                "hybrid_vs_dogi": {
                    "cpu_median_ns_ratio": 0.5,
                    "semantic_reset_delta": 4,
                },
            },
            "real_app_block_trace": {
                "artifact": "real-app-sysbench-pqc-block-trace",
                "device": "/dev/sdc2",
                "sysbench_elapsed_s": 8.0,
                "blkparse_event_lines": 100_000,
                "blkparse_write_events": 70_000,
                "pqc_sessions_completed": 64,
                "pqc_records": 192,
                "all_kem_ok": True,
                "all_sig_ok": True,
            },
            "security_capability": {
                "sanicap_hex": "0x3",
                "sanitize_supported": True,
                "sanitize_log_status": "never sanitized",
                "claim_boundary": (
                    "reset eligibility and stale-secret exposure reduction; sanitize is a "
                    "device/namespace-scoped destructive operation, not per-zone cleanup on a shared namespace"
                ),
            },
            "workload_hardness": {
                "passed_entries": 9,
                "total_entries": 9,
                "by_tier": {"pressure": {"passed": 2, "total": 2}, "claim-gate": {"passed": 1, "total": 1}},
                "entries": [
                    {
                        "tier": "claim-gate",
                        "passed": True,
                        "evidence": {
                            "eligible_ycsb_pressure_rows": 5,
                            "ycsb_baseline_complete_rows": 7,
                            "eligible_dynamic_rows": 3,
                            "dynamic_baseline_complete_rows": 3,
                        },
                    }
                ],
            },
            "deployment_selector": {
                "passed_modes": 4,
                "total_modes": 4,
                "default_policy": "quasar-dogi-hybrid",
                "hardness_passed": True,
            },
            "reproducibility_manifest": {
                "passed": True,
                "artifact_count": 14,
                "command_count": 8,
            },
            "reproducibility_validation": {
                "passed": True,
                "mismatch_count": 0,
            },
            "exact_external_baselines": {
                "dogi_physical_compact": {"aggregate_waf": 2.0},
                "midas_memory_repeat4": {"total_waf": 1.0},
                "sepbit_repeat4": {"wa": 2.4},
            },
        }
        readiness = {"paper_ready_external": True}
        acceptance = {"passed_gates": 35, "total_gates": 35}
        fdp_mapping = {
            "runs": [
                {
                    "handles": 64,
                    "family_count": 86,
                    "family_purity": 0.96,
                    "intent_purity": 0.98,
                    "avg_families_per_occupied_handle": 1.7,
                }
            ]
        }

        claims = claim_matrix.build_claims(unified, readiness, acceptance, fdp_mapping)
        summary = claim_matrix.summarize(claims)
        text = claim_matrix.markdown(summary)

        self.assertEqual(summary["claim_count"], 13)
        self.assertIn("supported-boundary", summary["by_status"])
        self.assertIn("Forbidden Overclaims", text)
        self.assertIn("Zone reset alone", text)
        self.assertIn("YCSB baseline-complete rows=7", text)
        self.assertIn("FDP can carry", text)
        self.assertIn("real application block trace", text)


if __name__ == "__main__":
    unittest.main()
