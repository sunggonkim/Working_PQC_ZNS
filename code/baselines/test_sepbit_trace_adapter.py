import json
import tempfile
import unittest
from pathlib import Path

try:
    import sepbit_trace_adapter
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from baselines import sepbit_trace_adapter


class SepbitTraceAdapterTests(unittest.TestCase):
    def test_adapt_trace_writes_ali_csv_group_and_property(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trace = root / "trace.jsonl"
            trace.write_text(
                "\n".join(
                    [
                        json.dumps({"op": "write", "ts": 7, "lba": 10, "size_blocks": 2}),
                        json.dumps({"op": "prefill", "ts": 8, "lba": 20, "size_blocks": 1}),
                        json.dumps({"op": "expire", "ts": 9, "lba": 10, "size_blocks": 2}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            summary = sepbit_trace_adapter.adapt_trace(
                trace,
                trace_out=root / "sepbit.csv",
                group_out=root / "group",
                property_out=root / "property.txt",
                log_id="pqc",
                delete_markers=True,
            )

            self.assertEqual(summary["writes"], 2)
            self.assertEqual(summary["tombstones"], 1)
            self.assertEqual(summary["unique_lbas"], 3)
            self.assertEqual((root / "sepbit.csv").read_text(encoding="utf-8").splitlines()[0], "pqc,W,40960,8192,7000")
            self.assertIn(str((root / "sepbit.csv").resolve()), (root / "group").read_text(encoding="utf-8"))
            self.assertEqual((root / "property.txt").read_text(encoding="utf-8").split()[0], "pqc")

    def test_adapt_trace_can_compact_lbas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trace = root / "trace.jsonl"
            trace.write_text(
                "\n".join(
                    [
                        json.dumps({"op": "write", "ts": 1, "lba": 1000, "size_blocks": 2}),
                        json.dumps({"op": "write", "ts": 2, "lba": 2000, "size_blocks": 1}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            summary = sepbit_trace_adapter.adapt_trace(
                trace,
                trace_out=root / "sepbit.csv",
                group_out=root / "group",
                property_out=root / "property.txt",
                log_id="pqc",
                delete_markers=False,
                compact_lba=True,
            )

            lines = (root / "sepbit.csv").read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], "pqc,W,0,8192,1000")
            self.assertEqual(lines[1], "pqc,W,8192,4096,2000")
            self.assertEqual(summary["original_max_lba"], 2000)
            self.assertEqual(summary["max_lba"], 2)
            self.assertTrue(summary["compact_lba"])


if __name__ == "__main__":
    unittest.main()
