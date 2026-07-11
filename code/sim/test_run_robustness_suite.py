import unittest

try:
    import run_robustness_suite
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from sim import run_robustness_suite


class RobustnessSuiteTests(unittest.TestCase):
    def test_summarize_reports_clean_and_perturbed_bounds(self) -> None:
        rows = [
            {
                "workload": "kms",
                "experiment": "dogi_baseline",
                "waf": 1.25,
                "stale_secret_blocks_remaining": 10,
                "failed": False,
            },
            {
                "workload": "kms",
                "experiment": "clean",
                "waf": 1.0,
                "stale_secret_blocks_remaining": 0,
                "failed": False,
            },
            {
                "workload": "kms",
                "experiment": "missing-0.10",
                "waf": 1.05,
                "stale_secret_blocks_remaining": 7,
                "failed": False,
            },
        ]

        summary = run_robustness_suite.summarize(rows)

        self.assertAlmostEqual(summary["kms"]["clean_waf_vs_dogi_pct"], 20.0)
        self.assertEqual(summary["kms"]["max_perturbed_waf"], 1.05)
        self.assertEqual(summary["kms"]["max_perturbed_stale_secret_blocks"], 7)


if __name__ == "__main__":
    unittest.main()
