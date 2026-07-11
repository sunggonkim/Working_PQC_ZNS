import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import packed_physical_replay_suite as suite
except ModuleNotFoundError:  # pragma: no cover
    from quasar import packed_physical_replay_suite as suite


class PackedPhysicalReplaySuiteTests(unittest.TestCase):
    def args(self, root: Path, **overrides):
        values = {
            "mount": root,
            "start_zone_index": 0,
            "max_zone_files": 4,
            "physical_zone_capacity": 16,
            "execute": True,
            "reset_selected_zones_at_start": True,
            "reset_at_end": True,
            "batch_appends": True,
            "max_blocks_per_dd": 8,
            "max_rows_in_output": 16,
            "max_logical_operations": 0,
            "fail_fast": True,
            "append_engine": "dd",
            "append_helper": Path("/tmp/zonefs_direct_append"),
            "helper_chunk_blocks": 1024,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def make_zonefs(self, root: Path, count: int = 4) -> None:
        seq = root / "seq"
        seq.mkdir()
        for index in range(count):
            (seq / str(index)).write_bytes(b"")

    def fake_append(self, target: Path, blocks: int):
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

    def fake_reset(self, target: Path):
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

    def test_any_packing_physically_delays_secret_reset(self) -> None:
        operations = [
            {
                "op": "append",
                "zone_id": 1,
                "group": 100,
                "blocks": 4,
                "intent": "KEM_ARTIFACT",
                "is_gc": False,
                "account_user": True,
            },
            {
                "op": "append",
                "zone_id": 2,
                "group": 200,
                "blocks": 4,
                "intent": "PAYLOAD",
                "is_gc": False,
                "account_user": True,
            },
            {"op": "reset_zone", "zone_id": 1, "group": 100},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_zonefs(root)
            args = self.args(root)
            with patch.object(suite.zonefs, "run_dd_append", side_effect=self.fake_append), patch.object(
                suite.zonefs, "run_truncate_reset", side_effect=self.fake_reset
            ):
                report = suite.execute_packed_operations(operations, args, packing="any")

        self.assertFalse(report["failed"])
        self.assertEqual(report["physical_reset_commands"], 0)
        self.assertEqual(report["delayed_logical_resets"], 1)
        self.assertEqual(report["secret_blocks_waiting_for_physical_reset"], 4)
        self.assertEqual(report["cleanup_reset_zones"], 1)

    def test_group_packing_turns_cohort_reset_into_physical_reset(self) -> None:
        operations = [
            {
                "op": "append",
                "zone_id": 1,
                "group": 100,
                "blocks": 4,
                "intent": "KEM_ARTIFACT",
                "is_gc": False,
                "account_user": True,
            },
            {
                "op": "append",
                "zone_id": 2,
                "group": 200,
                "blocks": 4,
                "intent": "PAYLOAD",
                "is_gc": False,
                "account_user": True,
            },
            {"op": "reset_zone", "zone_id": 1, "group": 100},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_zonefs(root)
            args = self.args(root)
            with patch.object(suite.zonefs, "run_dd_append", side_effect=self.fake_append), patch.object(
                suite.zonefs, "run_truncate_reset", side_effect=self.fake_reset
            ):
                report = suite.execute_packed_operations(operations, args, packing="group")

        self.assertFalse(report["failed"])
        self.assertEqual(report["physical_reset_commands"], 1)
        self.assertEqual(report["delayed_logical_resets"], 0)
        self.assertEqual(report["secret_blocks_waiting_for_physical_reset"], 0)
        self.assertEqual(report["cleanup_reset_zones"], 1)

    def test_epoch_bin_packing_delays_then_drains_secret_reset(self) -> None:
        operations = [
            {
                "op": "append",
                "zone_id": 1,
                "group": 100,
                "blocks": 4,
                "intent": "KEM_ARTIFACT",
                "epoch_id": 0,
                "is_gc": False,
                "account_user": True,
            },
            {
                "op": "append",
                "zone_id": 2,
                "group": 200,
                "blocks": 4,
                "intent": "KEM_ARTIFACT",
                "epoch_id": 1,
                "is_gc": False,
                "account_user": True,
            },
            {"op": "reset_zone", "zone_id": 1, "group": 100},
            {"op": "reset_zone", "zone_id": 2, "group": 200},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_zonefs(root)
            args = self.args(root)
            with patch.object(suite.zonefs, "run_dd_append", side_effect=self.fake_append), patch.object(
                suite.zonefs, "run_truncate_reset", side_effect=self.fake_reset
            ):
                report = suite.execute_packed_operations(operations, args, packing="epoch-bin-2")

        self.assertFalse(report["failed"])
        self.assertEqual(report["max_live_physical_zones"], 1)
        self.assertEqual(report["physical_reset_commands"], 1)
        self.assertEqual(report["delayed_logical_resets"], 1)
        self.assertEqual(report["secret_blocks_waiting_for_physical_reset"], 0)
        self.assertEqual(report["max_secret_blocks_waiting_for_physical_reset"], 8)
        self.assertEqual(report["cleanup_reset_zones"], 0)

    def test_secret_group_packing_keeps_secret_cohorts_and_packs_payload(self) -> None:
        operations = [
            {
                "op": "append",
                "zone_id": 1,
                "group": 100,
                "blocks": 4,
                "intent": "KEM_ARTIFACT",
                "epoch_id": 0,
                "is_gc": False,
                "account_user": True,
            },
            {
                "op": "append",
                "zone_id": 2,
                "group": 200,
                "blocks": 4,
                "intent": "KEM_ARTIFACT",
                "epoch_id": 1,
                "is_gc": False,
                "account_user": True,
            },
            {
                "op": "append",
                "zone_id": 3,
                "group": 300,
                "blocks": 4,
                "intent": "PAYLOAD",
                "epoch_id": 0,
                "is_gc": False,
                "account_user": True,
            },
            {
                "op": "append",
                "zone_id": 4,
                "group": 400,
                "blocks": 4,
                "intent": "PAYLOAD",
                "epoch_id": 1,
                "is_gc": False,
                "account_user": True,
            },
            {"op": "reset_zone", "zone_id": 1, "group": 100},
            {"op": "reset_zone", "zone_id": 2, "group": 200},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_zonefs(root)
            args = self.args(root)
            with patch.object(suite.zonefs, "run_dd_append", side_effect=self.fake_append), patch.object(
                suite.zonefs, "run_truncate_reset", side_effect=self.fake_reset
            ):
                report = suite.execute_packed_operations(operations, args, packing="secret-group")

        self.assertFalse(report["failed"])
        self.assertEqual(report["max_live_physical_zones"], 3)
        self.assertEqual(report["physical_reset_commands"], 2)
        self.assertEqual(report["delayed_logical_resets"], 0)
        self.assertEqual(report["secret_blocks_waiting_for_physical_reset"], 0)
        self.assertEqual(report["cleanup_reset_zones"], 1)

    def test_residual_migration_resets_mixed_zone_when_under_threshold(self) -> None:
        operations = [
            {
                "op": "append",
                "zone_id": 1,
                "group": 100,
                "blocks": 4,
                "intent": "KEM_ARTIFACT",
                "is_gc": False,
                "account_user": True,
            },
            {
                "op": "append",
                "zone_id": 2,
                "group": 200,
                "blocks": 4,
                "intent": "PAYLOAD",
                "is_gc": False,
                "account_user": True,
            },
            {"op": "reset_zone", "zone_id": 1, "group": 100},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_zonefs(root)
            args = self.args(root, physical_residual_threshold=4)
            with patch.object(suite.zonefs, "run_dd_append", side_effect=self.fake_append), patch.object(
                suite.zonefs, "run_truncate_reset", side_effect=self.fake_reset
            ):
                report = suite.execute_packed_operations(operations, args, packing="any")

        self.assertFalse(report["failed"])
        self.assertEqual(report["residual_migration_commands"], 1)
        self.assertEqual(report["residual_migrated_blocks"], 4)
        self.assertEqual(report["residual_migration_budget_skips"], 0)
        self.assertEqual(report["physical_reset_commands"], 1)
        self.assertEqual(report["secret_blocks_waiting_for_physical_reset"], 0)
        self.assertEqual(report["gc_blocks"], 4)

    def test_residual_copy_budget_leaves_exposure_instead_of_over_copying(self) -> None:
        operations = [
            {
                "op": "append",
                "zone_id": 1,
                "group": 100,
                "blocks": 4,
                "intent": "KEM_ARTIFACT",
                "is_gc": False,
                "account_user": True,
            },
            {
                "op": "append",
                "zone_id": 2,
                "group": 200,
                "blocks": 4,
                "intent": "PAYLOAD",
                "is_gc": False,
                "account_user": True,
            },
            {"op": "reset_zone", "zone_id": 1, "group": 100},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_zonefs(root)
            args = self.args(root, physical_residual_threshold=4, physical_residual_copy_budget=3)
            with patch.object(suite.zonefs, "run_dd_append", side_effect=self.fake_append), patch.object(
                suite.zonefs, "run_truncate_reset", side_effect=self.fake_reset
            ):
                report = suite.execute_packed_operations(operations, args, packing="any")

        self.assertFalse(report["failed"])
        self.assertEqual(report["residual_migration_commands"], 0)
        self.assertEqual(report["residual_migrated_blocks"], 0)
        self.assertEqual(report["residual_migration_budget_skips"], 1)
        self.assertEqual(report["physical_reset_commands"], 0)
        self.assertEqual(report["secret_blocks_waiting_for_physical_reset"], 4)
        self.assertEqual(report["delayed_logical_resets"], 1)

    def test_summarize_groups_by_policy_and_packing(self) -> None:
        rows = [
            {
                "policy": "quasar",
                "packing": "any",
                "sim": {"user_write_blocks": 100, "gc_write_blocks": 0, "stale_secret_blocks_remaining": 0},
                "physical": {
                    "failed": False,
                    "append_blocks": 100,
                    "user_blocks": 100,
                    "gc_blocks": 0,
                    "prefill_blocks": 0,
                    "physical_bytes_written": 100 * 4096,
                    "physical_append_commands": 1,
                    "logical_reset_commands": 2,
                    "physical_reset_commands": 0,
                    "delayed_logical_resets": 1,
                    "secret_logical_reset_blocks": 10,
                    "secret_blocks_waiting_for_physical_reset": 10,
                    "max_secret_blocks_waiting_for_physical_reset": 10,
                    "max_live_physical_zones": 1,
                    "max_active_pack_keys": 1,
                    "space_utilization": 0.5,
                },
            }
        ]

        summary = suite.summarize(rows, wall_time_ns=1_000)

        item = summary["by_policy_packing"]["quasar::any"]
        self.assertEqual(item["rows"], 1)
        self.assertEqual(item["delayed_reset_ratio"], 0.5)
        self.assertEqual(item["avg_space_utilization"], 0.5)


if __name__ == "__main__":
    unittest.main()
