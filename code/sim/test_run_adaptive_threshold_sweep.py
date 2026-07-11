import unittest

try:
    import run_adaptive_threshold_sweep
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from sim import run_adaptive_threshold_sweep


class AdaptiveThresholdSweepTests(unittest.TestCase):
    def test_summarize_groups_adaptive_configs(self) -> None:
        rows = [
            {
                "experiment": "adaptive",
                "adaptive_exact_min_blocks": 2,
                "adaptive_family_pressure": 4.0,
                "adaptive_tenant_bin_width": 8,
                "failed": False,
                "waf": 1.1,
                "gc_write_blocks": 10,
                "lifetime_zone_utilization": 0.2,
                "closed_zone_fill_avg": 0.25,
                "stale_secret_blocks_remaining": 0,
                "stale_secret_block_seconds": 100.0,
                "max_secret_exposure_time": 5.0,
            },
            {
                "experiment": "adaptive",
                "adaptive_exact_min_blocks": 2,
                "adaptive_family_pressure": 4.0,
                "adaptive_tenant_bin_width": 8,
                "failed": False,
                "waf": 1.2,
                "gc_write_blocks": 20,
                "lifetime_zone_utilization": 0.3,
                "closed_zone_fill_avg": 0.35,
                "stale_secret_blocks_remaining": 1,
                "stale_secret_block_seconds": 200.0,
                "max_secret_exposure_time": 6.0,
            },
            {
                "experiment": "dogi_baseline",
                "failed": False,
                "waf": 1.3,
                "gc_write_blocks": 30,
                "lifetime_zone_utilization": 0.8,
                "closed_zone_fill_avg": 0.9,
                "stale_secret_blocks_remaining": 5,
                "stale_secret_block_seconds": 500.0,
                "max_secret_exposure_time": 10.0,
            },
        ]

        summary = run_adaptive_threshold_sweep.summarize(rows)

        self.assertEqual(summary["row_count"], 3)
        self.assertEqual(summary["failed_runs"], 0)
        configs = {item["config"]: item for item in summary["configs"]}
        self.assertIn("exact=2;family=4.0;tenant=8", configs)
        self.assertAlmostEqual(configs["exact=2;family=4.0;tenant=8"]["waf"]["mean"], 1.15)
        self.assertEqual(len(summary["best_adaptive_by_score"]), 1)


if __name__ == "__main__":
    unittest.main()
