import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import physical_write_pressure_suite as suite
except ModuleNotFoundError:  # pragma: no cover
    from quasar import physical_write_pressure_suite as suite


class PhysicalWritePressureSuiteTests(unittest.TestCase):
    def test_select_rows_filters_ratio_policy_and_workload(self) -> None:
        rows = [
            {"workload": "exchange-pqc2000", "policy": "dogi-history"},
            {"workload": "exchange-pqc0500", "policy": "dogi-history"},
            {"workload": "varmail-pqc2000", "policy": "fifo"},
            {"workload": "varmail-pqc2000", "policy": "quasar-dogi-hybrid"},
        ]

        selected = suite.select_rows(
            rows,
            ratio_tag="pqc2000",
            policies=["dogi-history", "quasar-dogi-hybrid"],
            workloads=["exchange", "varmail"],
        )

        self.assertEqual(
            [(row["workload"], row["policy"]) for row in selected],
            [("exchange-pqc2000", "dogi-history"), ("varmail-pqc2000", "quasar-dogi-hybrid")],
        )

    def test_pressure_blocks_scales_user_plus_gc(self) -> None:
        row = {"user_write_blocks": 10, "gc_write_blocks": 3}

        self.assertEqual(suite.pressure_blocks(row, scale=4), 52)

    def test_append_blocks_across_zones_splits_by_zone_capacity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            zone_files = []
            for index in range(3):
                path = Path(tmp) / str(index)
                path.write_bytes(b"")
                zone_files.append(path)
            calls = []

            def fake_append(target: Path, blocks: int):
                calls.append((target.name, blocks))
                before = target.stat().st_size
                target.write_bytes(target.read_bytes() + (b"x" * blocks * 4096))
                return {
                    "target": str(target),
                    "blocks": blocks,
                    "bytes_requested": blocks * 4096,
                    "before_size": before,
                    "after_size": target.stat().st_size,
                    "latency_ns": 10,
                    "returncode": 0,
                    "stderr": "",
                    "stdout": "",
                    "succeeded": True,
                }

            with patch.object(suite.zonefs, "run_dd_append", side_effect=fake_append):
                result = suite.append_blocks_across_zones(
                    zone_files,
                    blocks=25,
                    zone_capacity_blocks=10,
                    max_blocks_per_dd=8,
                    execute=True,
                    fail_fast=True,
                )

            self.assertFalse(result["failed"])
            self.assertEqual(result["executed_blocks"], 25)
            self.assertEqual(calls, [("0", 8), ("0", 2), ("1", 8), ("1", 2), ("2", 5)])

    def test_summarize_computes_dogi_hybrid_reduction(self) -> None:
        rows = [
            {
                "workload_base": "exchange",
                "policy": "dogi-history",
                "source_user_write_blocks": 100,
                "source_gc_write_blocks": 20,
                "planned_physical_blocks": 120,
                "bytes_written": 120 * 4096,
                "wall_time_s": 1.0,
                "dd_ops": 1,
                "append_latency": {"count": 1, "p99_ns": 100},
                "source_stale_secret_blocks_remaining": 7,
            },
            {
                "workload_base": "exchange",
                "policy": "quasar-dogi-hybrid",
                "source_user_write_blocks": 100,
                "source_gc_write_blocks": 5,
                "planned_physical_blocks": 105,
                "bytes_written": 105 * 4096,
                "wall_time_s": 1.0,
                "dd_ops": 1,
                "append_latency": {"count": 1, "p99_ns": 80},
                "source_stale_secret_blocks_remaining": 0,
            },
        ]

        summary = suite.summarize(rows, wall_time_ns=2_000_000_000, reset_latencies=[])

        self.assertAlmostEqual(summary["dogi_vs_hybrid"]["hybrid_block_reduction_vs_dogi"], 0.125)
        self.assertEqual(summary["dogi_vs_hybrid"]["stale_secret_blocks_avoided"], 7)


if __name__ == "__main__":
    unittest.main()
