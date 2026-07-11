import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import physical_zonefs_replay
except ModuleNotFoundError:  # pragma: no cover
    from quasar import physical_zonefs_replay


class PhysicalZonefsReplayTests(unittest.TestCase):
    def test_select_zone_files_skips_nonempty_and_low_indices(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seq = root / "seq"
            seq.mkdir()
            for index in range(5):
                (seq / str(index)).write_bytes(b"x" if index == 3 else b"")

            selected = physical_zonefs_replay.select_zone_files(
                root, start_index=2, max_zone_files=2, require_empty=True
            )

            self.assertEqual(selected, [seq / "2", seq / "4"])

    def test_build_replay_plan_uses_quasar_families(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "trace.jsonl"
            rows = [
                {
                    "ts": 0,
                    "op": "write",
                    "object_id": 1,
                    "lba": 1,
                    "size_blocks": 1,
                    "intent": "KEM_ARTIFACT",
                    "epoch_id": 7,
                    "security_class": "SECRET",
                    "confidence": "exact",
                },
                {
                    "ts": 1,
                    "op": "expire",
                    "object_id": 1,
                },
            ]
            trace.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            args = SimpleNamespace(
                zone_capacity=512,
                max_zone_files=4,
                bin_width=4,
                cert_epochs=8,
                min_epoch_fill_blocks=1,
                max_appends=8,
                trace=trace,
                include_resets=False,
                coalesce_adjacent_appends=False,
            )

            commands, summary = physical_zonefs_replay.build_replay_plan(args)

            self.assertEqual(len(commands), 1)
            self.assertIn("EPOCH_SECRET:e7:KEM_ARTIFACT:SECRET", commands[0]["family"])
            self.assertEqual(summary["physical_reset_commands_skipped"], 1)

    def test_execute_zonefs_records_append_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seq = root / "seq"
            seq.mkdir()
            (seq / "10").write_bytes(b"")
            args = SimpleNamespace(
                mount=root,
                start_zone_index=10,
                max_zone_files=1,
                allow_nonempty_zone_files=False,
                max_blocks_per_append=1,
                execute=True,
                max_rows_in_output=8,
                fail_on_append_error=False,
                trace=Path("trace.jsonl"),
                reset_selected_zones_at_start=False,
                include_resets=False,
            )
            commands = [{"op": "append", "family": "EPOCH_SECRET:e0:KEM_ARTIFACT:SECRET", "blocks": 1, "ts": 0}]
            failed = {
                "target": str(seq / "10"),
                "blocks": 1,
                "bytes_requested": 4096,
                "before_size": 0,
                "after_size": 0,
                "latency_ns": 123,
                "returncode": 1,
                "stderr": "simulated failure",
                "stdout": "",
                "succeeded": False,
            }

            with patch.object(physical_zonefs_replay, "run_dd_append", return_value=failed):
                report = physical_zonefs_replay.execute_zonefs(commands, args)

            self.assertTrue(report["failed"])
            self.assertEqual(report["append_commands_attempted"], 1)
            self.assertEqual(report["append_commands_completed"], 0)
            self.assertIn("simulated failure", report["failures"][0]["stderr"])

    def test_run_helper_append_parses_helper_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "zone"
            target.write_bytes(b"")
            helper = root / "helper.py"
            helper.write_text(
                "#!/usr/bin/env python3\n"
                "import json, pathlib, sys\n"
                "target = pathlib.Path(sys.argv[1])\n"
                "blocks = int(sys.argv[2])\n"
                "target.write_bytes(target.read_bytes() + b'x' * blocks * 4096)\n"
                "print(json.dumps({'elapsed_ns': 77, 'blocks': blocks}))\n",
                encoding="utf-8",
            )
            helper.chmod(0o755)

            result = physical_zonefs_replay.run_helper_append(target, 2, helper)

            self.assertTrue(result["succeeded"])
            self.assertEqual(result["before_size"], 0)
            self.assertEqual(result["after_size"], 8192)
            self.assertEqual(result["helper_elapsed_ns"], 77)


if __name__ == "__main__":
    unittest.main()
