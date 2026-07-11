import json
import tempfile
import unittest
from pathlib import Path

try:
    import dogi_trace_adapter as adapter
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from baselines import dogi_trace_adapter as adapter


def write_trace(path: Path) -> None:
    rows = [
        {
            "op": "prefill",
            "ts": 0,
            "object_id": 0,
            "lba": 1,
            "size_blocks": 1,
        },
        {
            "op": "write",
            "ts": 1,
            "object_id": 1,
            "lba": 10,
            "size_blocks": 2,
            "intent": "KEM_ARTIFACT",
            "epoch_id": 0,
        },
        {
            "op": "expire",
            "ts": 20,
            "object_id": 1,
            "lba": 10,
            "size_blocks": 2,
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


class DogiTraceAdapterTests(unittest.TestCase):
    def test_adapt_trace_with_tombstone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "trace.jsonl"
            dogi = Path(tmp) / "trace.dogi"
            write_trace(jsonl)

            summary = adapter.adapt_trace(jsonl, dogi, delete_markers=True)

            lines = dogi.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 3)
            self.assertEqual(summary["dogi_writes"], 2)
            self.assertEqual(summary["dogi_tombstones"], 1)
            self.assertIn("LogicalSizeGb", summary["global_cc_snippet"])

    def test_adapt_trace_without_tombstone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "trace.jsonl"
            dogi = Path(tmp) / "trace.dogi"
            write_trace(jsonl)

            summary = adapter.adapt_trace(jsonl, dogi, delete_markers=False)

            lines = dogi.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(summary["skipped_expires"], 1)

    def test_compact_lba_reduces_logical_span(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "trace.jsonl"
            rows = [
                {"op": "write", "ts": 1, "object_id": 1, "lba": 1_000_000, "size_blocks": 2},
                {"op": "write", "ts": 2, "object_id": 2, "lba": 2_000_000, "size_blocks": 1},
                {"op": "write", "ts": 3, "object_id": 3, "lba": 1_000_000, "size_blocks": 1},
            ]
            jsonl.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            dogi = Path(tmp) / "trace.dogi"

            summary = adapter.adapt_trace(jsonl, dogi, delete_markers=False, compact_lba=True)
            lines = dogi.read_text(encoding="utf-8").splitlines()

            self.assertEqual(summary["compact_lba_entries"], 2)
            self.assertLess(summary["max_lba"], 4)
            self.assertIn(" 1 0 8192", lines[0])
            self.assertIn(" 1 0 4096", lines[2])


if __name__ == "__main__":
    unittest.main()
