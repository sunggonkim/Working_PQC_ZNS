import unittest

try:
    import report_goal_completion_audit as audit
except ModuleNotFoundError:  # pragma: no cover
    from sim import report_goal_completion_audit as audit


def real_app_fixture() -> dict:
    return {
        "artifact": "real-app-sysbench-pqc-block-trace",
        "claim": "real sysbench fileio block trace captured while PQC lifecycle side writes were persisted",
        "device": "/dev/sdc2",
        "sysbench": {"elapsed_s": 8.0},
        "blktrace": {"event_lines": 100_000, "write_events": 80_000},
        "pqc_side_writer": {
            "sessions_completed": 64,
            "records": 192,
            "all_kem_ok": True,
            "all_sig_ok": True,
        },
    }


def per_cohort_key_erase_fixture() -> dict:
    return {
        "artifact": "per-cohort-key-isolated-crypto-erase",
        "records": 256,
        "cohorts": 8,
        "destroyed_cohort": "epoch-4",
        "target_records": 32,
        "target_records_inaccessible_after_destroy": True,
        "unrelated_records": 224,
        "unrelated_cohorts_preserved": True,
        "wrong_key_rejection": {"attempted": 32, "rejected": 32, "all_rejected": True},
        "sanitize_called": False,
        "zone_reset_physical_erase_claimed": False,
        "claim_boundary": (
            "This is a cohort-scoped crypto-erase deployment path, not proof that zone reset "
            "physically erases NAND. It closes the erase blast-radius issue by moving the "
            "destructive primitive from device-wide sanitize to per-cohort encryption-key destruction."
        ),
    }


def fixture() -> tuple[dict, dict, dict, dict, dict, dict, dict]:
    unified = {
        "same_path_physical_zns": {
            "rows": 72,
            "failed_rows": 0,
            "by_policy": {
                "fifo": {"sim_stale_secret_blocks": 10, "physical_reset_commands": 0},
                "sepbit-style": {"sim_stale_secret_blocks": 10, "physical_reset_commands": 0},
                "midas-style": {"sim_stale_secret_blocks": 10, "physical_reset_commands": 0},
                "dogi-history": {"sim_stale_secret_blocks": 10, "physical_reset_commands": 0},
                "quasar": {"sim_stale_secret_blocks": 0, "physical_reset_commands": 2},
                "quasar-dogi-hybrid": {"sim_stale_secret_blocks": 0, "physical_reset_commands": 2},
            },
        },
        "ycsb_pressure_curve": {"waf_pressure_rows": 3, "semantic_gap_rows": 5, "row_count": 5},
        "fast_db_pressure": {
            "hybrid_vs_dogi": {"gc_reduction": 0.8, "stale_secret_reduction_blocks": 100}
        },
        "exact_external_baselines": {
            "dogi_physical_compact": {"completed": True, "aggregate_waf": 2.4},
            "dogi_physical_original_lba_pressure": {"completed": True, "waf": 3.2},
            "midas_memory_repeat4": {"completed": True, "total_waf": 1.01},
            "sepbit_repeat4": {"completed": True, "wa": 2.39},
        },
        "workload_hardness": {
            "passed": True,
            "passed_entries": 9,
            "total_entries": 9,
            "by_tier": {
                "negative-control": {"passed": 2, "total": 2},
                "claim-gate": {"passed": 1, "total": 1},
            },
            "entries": [
                {
                    "tier": "claim-gate",
                    "passed": True,
                    "evidence": {
                        "eligible_ycsb_pressure_rows": 5,
                        "ycsb_baseline_complete_rows": 5,
                        "db_pressure_eligible": True,
                        "eligible_dynamic_rows": 3,
                        "dynamic_baseline_complete_rows": 3,
                    },
                }
            ],
        },
        "deployment_selector": {
            "passed": True,
            "passed_modes": 4,
            "total_modes": 4,
            "default_policy": "quasar-dogi-hybrid",
            "hardness_passed": True,
        },
        "actual_zns_overhead": {
            "failed_rows": 0,
            "row_count": 84,
            "hybrid_vs_dogi": {"cpu_median_ns_ratio": 0.5, "semantic_reset_delta": 10},
        },
        "xnvme_zns_latency": {
            "completed": True,
            "append_count": 4096,
            "append_p99_ns": 26000,
            "mounted_after": True,
            "nonempty_after_lines": 0,
        },
        "security_capability": {
            "device_model": "zns",
            "sanicap_hex": "0x1",
            "sanitize_supported": True,
            "sanitize_log_status": "never",
        },
    }
    readiness = {"paper_ready_external": True, "blockers": [], "pending": []}
    acceptance = {"passed": True, "passed_gates": 40, "total_gates": 40}
    validation = {"passed": True, "mismatch_count": 0}
    pipeline_manifest = {"passed": True, "non_destructive": True, "steps": [{"name": "done"}]}
    return (
        unified,
        readiness,
        acceptance,
        validation,
        pipeline_manifest,
        real_app_fixture(),
        per_cohort_key_erase_fixture(),
    )


class GoalCompletionAuditTests(unittest.TestCase):
    def test_build_audit_marks_scoped_claim_ready(self) -> None:
        summary = audit.build_audit(*fixture())

        self.assertTrue(summary["scoped_claim_ready"])
        self.assertFalse(summary["full_goal_complete"])
        self.assertEqual(summary["blocking_count"], 0)
        self.assertEqual(summary["fast_r2_production_blocker_count"], 4)
        self.assertGreater(summary["full_goal_remaining_count"], 0)
        self.assertIn("not production-grade fast evidence", summary["main_takeaway"].lower())
        self.assertIn("broader user goal remains active", summary["completion_boundary"])
        self.assertIn("Reviewer-2 production blockers", summary["completion_boundary"])
        blockers = {row["name"] for row in summary["fast_r2_production_blockers"]}
        self.assertIn("spdk_or_zenfs_tail_latency", blockers)
        self.assertNotIn("per_cohort_physical_erase_scope", blockers)
        self.assertNotIn("real_application_block_traces", blockers)
        self.assertNotIn("Full original-LBA", " ".join(summary["optional_strengthening"]))

    def test_missing_real_app_trace_remains_production_blocker(self) -> None:
        unified, readiness, acceptance, validation, pipeline_manifest, _real_app, key_erase = fixture()

        summary = audit.build_audit(unified, readiness, acceptance, validation, pipeline_manifest, {}, key_erase)

        self.assertFalse(summary["scoped_claim_ready"])
        blockers = {row["name"] for row in summary["fast_r2_production_blockers"]}
        self.assertIn("real_application_block_traces", blockers)

    def test_missing_per_cohort_key_erase_remains_production_blocker(self) -> None:
        unified, readiness, acceptance, validation, pipeline_manifest, real_app, _key_erase = fixture()

        summary = audit.build_audit(unified, readiness, acceptance, validation, pipeline_manifest, real_app, {})

        self.assertFalse(summary["scoped_claim_ready"])
        blockers = {row["name"] for row in summary["fast_r2_production_blockers"]}
        self.assertIn("per_cohort_physical_erase_scope", blockers)

    def test_missing_same_path_policy_blocks_claim(self) -> None:
        unified, readiness, acceptance, validation, pipeline_manifest, real_app, key_erase = fixture()
        unified["same_path_physical_zns"]["by_policy"].pop("midas-style")

        summary = audit.build_audit(unified, readiness, acceptance, validation, pipeline_manifest, real_app, key_erase)

        self.assertFalse(summary["scoped_claim_ready"])
        self.assertGreater(summary["blocking_count"], 0)


if __name__ == "__main__":
    unittest.main()
