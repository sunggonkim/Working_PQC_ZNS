import json
import tempfile
import unittest
from pathlib import Path

try:
    import replay
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from quasar import replay


def write_trace(path: Path) -> None:
    rows = [
        {
            "op": "write",
            "ts": 1,
            "object_id": 1,
            "lba": 100,
            "size_blocks": 1,
            "intent": "KEM_ARTIFACT",
            "epoch_id": 7,
            "expire_class": "EPOCH",
            "security_class": "SECRET",
            "confidence": "exact",
        },
        {
            "op": "write",
            "ts": 2,
            "object_id": 2,
            "lba": 200,
            "size_blocks": 1,
            "intent": "PAYLOAD",
            "epoch_id": 7,
            "expire_class": "UNKNOWN",
            "security_class": "PAYLOAD",
            "confidence": "exact",
        },
        {
            "op": "expire",
            "ts": 10,
            "object_id": 1,
            "lba": 100,
            "size_blocks": 1,
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


class ReplayTests(unittest.TestCase):
    def test_dry_run_builds_reset_family_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "trace.jsonl"
            write_trace(trace)
            config = replay.ReplayConfig(
                backend="dry-run",
                device=None,
                zone_capacity=512,
                emulator_zones=16,
                emulator_state=None,
                bin_width=1,
                cert_epochs=12,
                min_epoch_fill_blocks=1,
                execute=False,
            )

            commands, summary = replay.build_plan(trace, config)

            self.assertGreaterEqual(summary["append_commands"], 2)
            self.assertEqual(summary["reset_family_commands"], 1)
            self.assertTrue(any(command["op"] == "reset_family" for command in commands))
            self.assertTrue(summary["backend_status"]["available"])

    def test_backend_status_reports_missing_optional_tool(self) -> None:
        status = replay.backend_status("xnvme")
        self.assertEqual(status["required_tool"], "xnvme")
        self.assertIn("available", status)

    def test_blkzone_backend_status_and_nullblk_guard(self) -> None:
        status = replay.backend_status("blkzone-zns")
        self.assertEqual(status["required_tool"], "blkzone")
        self.assertIn("available", status)
        self.assertTrue(replay.device_is_nullblk("/dev/nullb_quasar"))
        self.assertFalse(replay.device_is_nullblk("/dev/nvme0n1"))

    def test_file_zns_backend_executes_append_and_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "trace.jsonl"
            state = Path(tmp) / "state.json"
            write_trace(trace)
            config = replay.ReplayConfig(
                backend="file-zns",
                device=None,
                zone_capacity=4,
                emulator_zones=8,
                emulator_state=state,
                bin_width=1,
                cert_epochs=12,
                min_epoch_fill_blocks=1,
                execute=True,
            )

            commands, summary = replay.build_plan(trace, config)
            replay.execute_plan(commands, config)
            state_doc = replay.load_json(state)

            self.assertEqual(summary["append_commands"], 2)
            self.assertEqual(state_doc["summary"]["emulator_append_commands"], 2)
            self.assertEqual(state_doc["summary"]["emulator_reset_commands"], 1)
            self.assertGreaterEqual(state_doc["summary"]["emulator_reset_zones"], 1)
            self.assertGreater(state_doc["summary"]["emulator_wall_time_ns"], 0)
            self.assertGreater(state_doc["summary"]["emulator_bytes_written"], 0)
            self.assertIn("emulator_append_latency_p99_ns", state_doc["summary"])


if __name__ == "__main__":
    unittest.main()
