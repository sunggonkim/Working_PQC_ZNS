import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

try:
    import report_residual_fallback_sweep as report
except ModuleNotFoundError:  # pragma: no cover
    from sim import report_residual_fallback_sweep as report


class ResidualFallbackControllerTests(unittest.TestCase):
    def test_collect_budget_physical_parses_actual_zns_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            artifact = base / "ycsb-f-pqc8000-th32768-budget50000-epoch-bin-5-physical.json"
            artifact.write_text(
                """
{
  "execute": true,
  "summary": {
    "by_policy_packing": {
      "quasar-dogi-hybrid::epoch-bin-5": {
        "failed_rows": 0,
        "max_live_physical_zones": 12,
        "physical_reset_commands": 3,
        "physical_waf": 1.1096,
        "residual_migrated_blocks": 44105,
        "residual_migration_budget_skips": 68,
        "secret_blocks_waiting_for_physical_reset": 70656,
        "sim_waf": 1.0137
      }
    }
  }
}
""",
                encoding="utf-8",
            )

            rows = report.collect_budget_physical(base)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["workload"], "ycsb-f-pqc8000")
        self.assertEqual(rows[0]["threshold"], 32768)
        self.assertEqual(rows[0]["copy_budget"], 50_000)
        self.assertEqual(rows[0]["packing"], "epoch-bin-5")
        self.assertEqual(rows[0]["evidence"], "actual-zns")
        self.assertEqual(rows[0]["residual_migration_budget_skips"], 68)

    def test_controller_selects_low_balanced_and_strict_modes(self) -> None:
        rows = [
            {
                "workload": "ycsb-f-pqc8000",
                "packing": "epoch-bin-5",
                "threshold": 4096,
                "physical_waf": 1.01,
                "secret_waiting_end": 70_000,
                "residual_migrated_blocks": 0,
                "max_live_physical_zones": 12,
                "failed_rows": 0,
            },
            {
                "workload": "ycsb-f-pqc8000",
                "packing": "epoch-bin-5",
                "threshold": 32768,
                "copy_budget": 200_000,
                "physical_waf": 1.44,
                "secret_waiting_end": 43_000,
                "residual_migrated_blocks": 198_000,
                "residual_migration_budget_skips": 50,
                "max_live_physical_zones": 12,
                "failed_rows": 0,
            },
            {
                "workload": "ycsb-f-pqc8000",
                "packing": "epoch-bin-5",
                "threshold": 32768,
                "physical_waf": 3.55,
                "secret_waiting_end": 0,
                "residual_migrated_blocks": 1_168_000,
                "max_live_physical_zones": 13,
                "failed_rows": 0,
            },
        ]

        decisions = {
            item["profile"]: item["selected"]
            for item in report.controller_decisions(rows, [], mor=13)
            if item["workload"] == "ycsb-f-pqc8000"
        }

        self.assertEqual(decisions["low_overhead"]["mode"], "no-residual-copy")
        self.assertEqual(decisions["low_overhead"]["recommended_copy_budget"], 0)
        self.assertEqual(decisions["balanced"]["mode"], "bounded-copy-budget")
        self.assertEqual(decisions["balanced"]["recommended_copy_budget"], 200_000)
        self.assertEqual(decisions["strict_zero_wait"]["mode"], "strict-zero-wait")
        self.assertIsNone(decisions["strict_zero_wait"]["recommended_copy_budget"])
        self.assertEqual(decisions["strict_zero_wait"]["secret_waiting_end"], 0)

    def test_zero_waiting_is_not_treated_as_missing(self) -> None:
        rows = [
            {
                "workload": "exchange-pqc2000",
                "packing": "epoch-bin-5",
                "threshold": 4096,
                "physical_waf": 1.02,
                "secret_waiting_end": 0,
                "residual_migrated_blocks": 3515,
                "max_live_physical_zones": 10,
                "failed_rows": 0,
            }
        ]

        strict_profile = next(profile for profile in report.CONTROLLER_PROFILES if profile["profile"] == "strict_zero_wait")
        choice = report.choose_controller_candidate(rows, strict_profile, mor=13)

        self.assertEqual(choice["selected"]["mode"], "strict-zero-wait")
        self.assertEqual(choice["selected"]["secret_waiting_end"], 0)
        self.assertEqual(choice["relaxed_constraints"], [])


if __name__ == "__main__":
    unittest.main()
