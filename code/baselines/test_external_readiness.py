import tempfile
import unittest
from pathlib import Path

try:
    import external_readiness
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from baselines import external_readiness


class ExternalReadinessTests(unittest.TestCase):
    def test_workload_hardness_status_requires_claim_gate(self) -> None:
        strong = {
            "passed": True,
            "passed_entries": 9,
            "total_entries": 9,
            "by_tier": {
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
        }
        weak = {
            **strong,
            "entries": [
                {
                    "tier": "claim-gate",
                    "passed": True,
                    "evidence": {
                        "eligible_ycsb_pressure_rows": 5,
                        "ycsb_baseline_complete_rows": 5,
                        "db_pressure_eligible": True,
                        "eligible_dynamic_rows": 0,
                        "dynamic_baseline_complete_rows": 0,
                    },
                }
            ],
        }

        self.assertEqual(
            external_readiness.workload_hardness_status(strong)["status"],
            "done-workload-hardness-matrix",
        )
        self.assertEqual(
            external_readiness.workload_hardness_status(weak)["status"],
            "partial-workload-hardness-matrix",
        )

    def test_report_marks_environment_blockers_and_completed_dogi(self) -> None:
        inputs = {name: Path("/does/not/exist") for name in external_readiness.DEFAULT_INPUTS}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            openssl = root / "openssl.json"
            zns = root / "zns.json"
            dogi_run = root / "dogi-run.json"
            midas = root / "midas.json"
            midas_run = root / "midas-run.json"
            sepbit_run = root / "sepbit-run.json"
            acceptance = root / "acceptance.json"

            openssl.write_text('{"pqc_provider_detected": false, "version": {"stdout": "OpenSSL 1.1.1\\n"}}', encoding="utf-8")
            zns.write_text('{"can_run_real_zns_replay": false, "zoned_devices": [], "null_blk": {"module_available": true}, "tools": {}}', encoding="utf-8")
            dogi_run.write_text('{"completed": true, "waf": 1.68, "user_write_gib": 2.5, "gc_write_gib": 1.7}', encoding="utf-8")
            midas.write_text('{"can_attempt_local_memory_run": true, "required_files": {"README.md": true}, "trace": {"all_sampled_lines_usable": true}}', encoding="utf-8")
            midas_run.write_text('{"completed": true, "total_waf": 1.25, "storage_capacity_gib": 1, "build": {"gigaunit": "1L"}, "counters": {"dataw": 10, "gcdw": 2}}', encoding="utf-8")
            sepbit_run.write_text('{"completed": true, "method": "SepBIT", "selection": "Greedy", "summary": {"wa": 2.43, "requests": 100, "ngc": 7}}', encoding="utf-8")
            acceptance.write_text('{"passed": true, "passed_gates": 13, "total_gates": 13}', encoding="utf-8")

            inputs.update(
                {
                    "openssl": openssl,
                    "zns": zns,
                    "dogi_run": dogi_run,
                    "midas": midas,
                    "midas_run": midas_run,
                    "sepbit_run": sepbit_run,
                    "acceptance": acceptance,
                }
            )

            report = external_readiness.build_report(inputs)

            self.assertIn("openssl_oqsprovider", report["blockers"])
            self.assertIn("zns_fdp_replay", report["pending"])
            self.assertEqual(report["components"]["dogi_exact"]["status"], "done-nullblk")
            self.assertEqual(report["components"]["midas_exact"]["status"], "done-local-memory")
            self.assertEqual(report["components"]["sepbit_exact"]["status"], "done-local-simulator")


if __name__ == "__main__":
    unittest.main()
