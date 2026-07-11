import json
import tempfile
import unittest
from pathlib import Path

try:
    import report_actual_zns_overhead as overhead
except ModuleNotFoundError:  # pragma: no cover
    from sim import report_actual_zns_overhead as overhead


def row(policy: str, append_avg: int, reset_count: int, semantic_resets: int) -> dict:
    return {
        "workload": "w1",
        "trace": "w1.jsonl",
        "policy": policy,
        "packing": "secret-group",
        "physical": {
            "failed": False,
            "physical_bytes_written": 4096 * 10,
            "physical_append_commands": 2,
            "physical_reset_commands": semantic_resets,
            "initial_reset_zones": 1,
            "cleanup_reset_zones": 1,
            "wall_time_s": 0.5,
            "throughput_mib_s": 1.0,
            "max_live_physical_zones": 3,
            "append_latency": {
                "count": 2,
                "avg_ns": append_avg,
                "p95_ns": append_avg + 10,
                "p99_ns": append_avg + 20,
                "max_ns": append_avg + 30,
            },
            "reset_latency": {
                "count": reset_count,
                "avg_ns": 100,
                "p95_ns": 200,
                "p99_ns": 300,
                "max_ns": 400,
            },
        },
    }


class ActualZnsOverheadReportTests(unittest.TestCase):
    def test_summarizes_physical_and_cpu_overhead(self) -> None:
        report = {
            "rows": [
                row("dogi-history", 200, 2, 0),
                row("quasar-dogi-hybrid", 100, 3, 4),
            ]
        }
        cpu = {
            "aggregate": {
                "dogi-mlp": {"median_ns_per_write": 2000.0},
                "quasar-dogi-hybrid": {"median_ns_per_write": 1000.0},
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            physical = root / "physical.json"
            physical.write_text(json.dumps(report), encoding="utf-8")
            summary = overhead.summarize_artifacts([physical], cpu)

        self.assertEqual(summary["row_count"], 2)
        self.assertEqual(summary["failed_rows"], 0)
        self.assertEqual(summary["by_policy"]["dogi-history"]["append_avg_ns"], 200)
        self.assertEqual(summary["by_policy"]["quasar-dogi-hybrid"]["semantic_physical_reset_commands"], 4)
        self.assertEqual(summary["hybrid_vs_dogi"]["cpu_median_ns_ratio"], 0.5)
        self.assertIn("Actual-ZNS", overhead.markdown(summary))


if __name__ == "__main__":
    unittest.main()
