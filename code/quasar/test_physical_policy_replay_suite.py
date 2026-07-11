import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import physical_policy_replay_suite as suite
except ModuleNotFoundError:  # pragma: no cover
    from quasar import physical_policy_replay_suite as suite


class PhysicalPolicyReplaySuiteTests(unittest.TestCase):
    def args(self, **overrides):
        values = {
            "lba_bucket_size": 4096,
            "zone_capacity": 4,
            "zones": 8,
            "min_free_zones": 1,
            "quasar_cert_epochs": 12,
            "quasar_min_epoch_fill": 0.0,
            "quasar_bin_width": 1,
            "quasar_open_zone_budget": 0,
            "quasar_residual_threshold": -1,
            "quasar_residual_fraction": 0.0,
            "quasar_disable_overflow": False,
            "quasar_disable_secret_priority": False,
            "quasar_adaptive_exact_min_blocks": 4,
            "quasar_adaptive_tenant_bin_width": 16,
            "quasar_adaptive_coarse_bin_width": 32_000_000,
            "quasar_adaptive_coarse_pressure": 0.75,
            "quasar_adaptive_family_pressure": 8.0,
            "quasar_adaptive_urgent_lifetime": 32,
            "hint_missing_rate": 0.0,
            "wrong_epoch_rate": 0.0,
            "straggler_rate": 0.0,
            "base_write_ns": 10_000,
            "gc_copy_ns": 15_000,
            "dogi_ml_ns_per_batch": 600_000,
            "dogi_batch_size": 128,
            "quasar_hint_ns": 200,
            "seed": 7,
            "coalesce": True,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_simulate_policy_emits_append_and_reset_operations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "trace.jsonl"
            rows = [
                {
                    "ts": 0,
                    "op": "write",
                    "object_id": 1,
                    "lba": 1,
                    "size_blocks": 2,
                    "intent": "KEM_ARTIFACT",
                    "epoch_id": 3,
                    "security_class": "SECRET",
                    "confidence": "exact",
                },
                {"ts": 1, "op": "expire", "object_id": 1},
            ]
            trace.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            stats, operations = suite.simulate_policy(trace, "quasar", self.args())

            self.assertEqual(stats["user_write_blocks"], 2)
            self.assertEqual([op["op"] for op in operations], ["append", "reset_zone"])
            self.assertEqual(operations[0]["blocks"], 2)

    def test_execute_operations_maps_logical_zones_to_zonefs_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seq = root / "seq"
            seq.mkdir()
            for index in range(10, 13):
                (seq / str(index)).write_bytes(b"")

            args = SimpleNamespace(
                mount=root,
                start_zone_index=10,
                max_zone_files=3,
                execute=True,
                fail_fast=True,
                max_physical_commands=0,
                max_blocks_per_dd=8,
                zone_capacity=4,
                batch_appends=False,
                reset_at_end=True,
                max_rows_in_output=16,
            )
            operations = [
                {"op": "append", "zone_id": 7, "blocks": 3, "is_gc": False, "ts": 0},
                {"op": "reset_zone", "zone_id": 7, "group": 1, "ts": 1},
            ]

            def fake_append(target: Path, blocks: int):
                before = target.stat().st_size
                target.write_bytes(target.read_bytes() + b"x" * blocks * 4096)
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

            def fake_reset(target: Path):
                before = target.stat().st_size
                target.write_bytes(b"")
                return {
                    "target": str(target),
                    "before_size": before,
                    "after_size": 0,
                    "latency_ns": 5,
                    "returncode": 0,
                    "stderr": "",
                    "stdout": "",
                    "succeeded": True,
                }

            with patch.object(suite.zonefs, "run_dd_append", side_effect=fake_append), patch.object(
                suite.zonefs, "run_truncate_reset", side_effect=fake_reset
            ):
                report = suite.execute_operations(operations, args)

            self.assertFalse(report["failed"])
            self.assertEqual(report["bytes_written"], 3 * 4096)
            self.assertEqual(report["reset_commands_executed"], 1)
            self.assertEqual(report["max_active_zone_files"], 1)
            self.assertEqual(report["max_open_zone_files"], 1)
            self.assertEqual(report["max_allocated_zone_files"], 1)

    def test_summarize_compares_dogi_and_hybrid_physical_blocks(self) -> None:
        rows = [
            {
                "policy": "dogi-history",
                "sim": {"user_write_blocks": 100, "gc_write_blocks": 20, "stale_secret_blocks_remaining": 9},
                "physical": {
                    "failed": False,
                    "bytes_written": 120 * 4096,
                    "user_blocks_written": 100,
                    "gc_blocks_written": 20,
                    "reset_commands_executed": 2,
                    "max_open_zone_files": 4,
                    "max_allocated_zone_files": 5,
                    "zone_files_used": 5,
                },
            },
            {
                "policy": "quasar-dogi-hybrid",
                "sim": {"user_write_blocks": 100, "gc_write_blocks": 5, "stale_secret_blocks_remaining": 0},
                "physical": {
                    "failed": False,
                    "bytes_written": 105 * 4096,
                    "user_blocks_written": 100,
                    "gc_blocks_written": 5,
                    "reset_commands_executed": 3,
                    "max_open_zone_files": 3,
                    "max_allocated_zone_files": 4,
                    "zone_files_used": 4,
                },
            },
        ]

        summary = suite.summarize(rows, wall_time_ns=1_000_000)

        self.assertAlmostEqual(summary["dogi_vs_hybrid"]["hybrid_block_reduction_vs_dogi"], 0.125)
        self.assertEqual(summary["dogi_vs_hybrid"]["stale_secret_blocks_avoided"], 9)


if __name__ == "__main__":
    unittest.main()
