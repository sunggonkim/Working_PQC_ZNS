import json
import tempfile
import unittest
from pathlib import Path

try:
    import run_replay_latency_suite as suite
except ModuleNotFoundError:  # pragma: no cover - root-level unittest discovery
    from quasar import run_replay_latency_suite as suite


def write_trace(path: Path) -> None:
    rows = [
        {
            "op": "write",
            "ts": 1,
            "object_id": 1,
            "lba": 0,
            "size_blocks": 2,
            "intent": "KEM_ARTIFACT",
            "epoch_id": 1,
            "expire_class": "EPOCH",
            "security_class": "SECRET",
            "confidence": "exact",
        },
        {
            "op": "expire",
            "ts": 2,
            "object_id": 1,
            "lba": 0,
            "size_blocks": 2,
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


class ReplayLatencySuiteTests(unittest.TestCase):
    def test_file_zns_latency_suite_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trace = root / "trace.jsonl"
            write_trace(trace)

            row = suite.run_one(
                trace,
                out_dir=root / "out",
                zone_capacity=4,
                emulator_zones=8,
                bin_width=1,
                cert_epochs=12,
                min_epoch_fill_blocks=1,
            )
            aggregate = suite.summarize([row])

            self.assertEqual(row["append_commands"], 1)
            self.assertEqual(row["reset_family_commands"], 1)
            self.assertGreater(row["emulator_wall_time_ns"], 0)
            self.assertGreaterEqual(row["emulator_append_latency_p99_ns"], 0)
            self.assertEqual(aggregate["trace_count"], 1)
            self.assertGreater(aggregate["total_emulator_bytes_written"], 0)


if __name__ == "__main__":
    unittest.main()
