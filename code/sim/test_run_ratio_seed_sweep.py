import unittest

try:
    import run_ratio_seed_sweep
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from sim import run_ratio_seed_sweep


class RatioSeedSweepTests(unittest.TestCase):
    def test_summarize_computes_break_even_and_ci_inputs(self) -> None:
        pairs = [
            {
                "seed": 1,
                "base": "kms",
                "ratio": 0.0,
                "waf_reduction_vs_dogi": 0.0,
                "gc_reduction_vs_dogi": 0.0,
                "stale_avoided": 0,
            },
            {
                "seed": 2,
                "base": "kms",
                "ratio": 0.0,
                "waf_reduction_vs_dogi": 0.0,
                "gc_reduction_vs_dogi": 0.0,
                "stale_avoided": 0,
            },
            {
                "seed": 1,
                "base": "kms",
                "ratio": 0.2,
                "waf_reduction_vs_dogi": 0.10,
                "gc_reduction_vs_dogi": 0.40,
                "stale_avoided": 100,
            },
            {
                "seed": 2,
                "base": "kms",
                "ratio": 0.2,
                "waf_reduction_vs_dogi": 0.20,
                "gc_reduction_vs_dogi": 0.60,
                "stale_avoided": 200,
            },
        ]

        summary = run_ratio_seed_sweep.summarize(pairs)

        self.assertEqual(summary["break_even_ratio"], 0.2)
        self.assertEqual(summary["seed_count"], 2)
        ratio_20 = [row for row in summary["ratio_summary"] if row["ratio"] == 0.2][0]
        self.assertAlmostEqual(ratio_20["waf_reduction_vs_dogi"]["mean"], 0.15)
        self.assertAlmostEqual(ratio_20["stale_avoided_per_seed"]["mean"], 150.0)


if __name__ == "__main__":
    unittest.main()
