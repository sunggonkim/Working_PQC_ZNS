import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

try:
    import fio_iolog_to_quasar as conv
except ModuleNotFoundError:  # pragma: no cover
    from tracegen import fio_iolog_to_quasar as conv


class FioIologToQuasarTests(unittest.TestCase):
    def test_parse_fio_iolog_write(self) -> None:
        self.assertEqual(conv.parse_fio_iolog_write("/tmp/f write 8192 4096"), (2, 1))
        self.assertEqual(conv.parse_fio_iolog_write("/tmp/f write 4096 8192"), (1, 2))
        self.assertIsNone(conv.parse_fio_iolog_write("fio version 2 iolog"))
        self.assertIsNone(conv.parse_fio_iolog_write("/tmp/f open"))

    def test_convert_adds_payload_expiry_and_pqc_expiry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            iolog = root / "fio.iolog"
            jsonl = root / "trace.jsonl"
            summary = root / "summary.json"
            iolog.write_text(
                "\n".join(
                    [
                        "fio version 2 iolog",
                        "/tmp/f add",
                        "/tmp/f open",
                        "/tmp/f write 0 4096",
                        "/tmp/f write 0 4096",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            args = Namespace(
                iolog=iolog,
                jsonl=jsonl,
                summary_out=summary,
                dogi_out=None,
                max_events=2,
                prefill_working_set=True,
                pqc_ratio=1.0,
                epoch_len=1,
                pqc_lba_base=1_000_000,
                pqc_lba_span=16,
                session_jitter=0,
                rotation_epochs=2,
                seed=7,
            )
            result = conv.convert(args)

            rows = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(result["payload_requests"], 2)
            self.assertEqual(result["prefill_blocks"], 1)
            self.assertGreater(result["pqc_writes"], 0)
            self.assertTrue(any(row["op"] == "expire" and row.get("lba") == 0 for row in rows))
            self.assertTrue(any(row.get("intent") in conv.SECRET_INTENTS for row in rows if row["op"] == "write"))
            self.assertTrue(summary.exists())


if __name__ == "__main__":
    unittest.main()
