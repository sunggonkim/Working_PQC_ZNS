import unittest

try:
    import run_liboqs_kms_stress as stress
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from sim import run_liboqs_kms_stress as stress


class LiboqsKmsStressTests(unittest.TestCase):
    def test_summarize_compares_dogi_and_hybrid(self) -> None:
        rows = [
            {
                "profile": "kms",
                "op_ratio": 0.5,
                "policy": "dogi-history",
                "waf": 1.2,
                "gc_write_blocks": 100,
                "stale_secret_blocks_remaining": 7,
                "write_latency_p99_ns": 30,
                "zones": 10,
                "initial_zones": 8,
                "retries": 1,
            },
            {
                "profile": "kms",
                "op_ratio": 0.5,
                "policy": "quasar-dogi-hybrid",
                "waf": 1.0,
                "gc_write_blocks": 0,
                "stale_secret_blocks_remaining": 0,
                "write_latency_p99_ns": 20,
                "zones": 8,
                "initial_zones": 8,
                "retries": 0,
            },
            {
                "profile": "kms",
                "op_ratio": 1.0,
                "policy": "dogi-history",
                "failed": True,
                "error": "out of zones",
            },
        ]

        summary = stress.summarize(rows)

        self.assertEqual(summary["row_count"], 3)
        self.assertEqual(summary["failed_runs"], 1)
        self.assertEqual(summary["comparison_count"], 1)
        self.assertAlmostEqual(summary["avg_waf_reduction_vs_dogi"], (1.2 - 1.0) / 1.2)
        self.assertEqual(summary["total_gc_blocks_saved"], 100)
        self.assertEqual(summary["total_stale_secret_blocks_avoided"], 7)


if __name__ == "__main__":
    unittest.main()
