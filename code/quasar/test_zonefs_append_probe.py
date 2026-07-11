import tempfile
import unittest
import json
from pathlib import Path

try:
    import zonefs_append_probe
except ModuleNotFoundError:  # pragma: no cover
    from quasar import zonefs_append_probe


class ZonefsAppendProbeTests(unittest.TestCase):
    def test_choose_zone_file_prefers_numeric_empty_seq_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seq = root / "seq"
            seq.mkdir()
            (seq / "10").write_bytes(b"x")
            (seq / "2").write_bytes(b"")

            chosen = zonefs_append_probe.choose_zone_file(root)

            self.assertEqual(chosen, seq / "2")

    def test_read_only_option_parser(self) -> None:
        self.assertTrue(zonefs_append_probe.is_read_only({"options": "ro,nosuid"}))
        self.assertFalse(zonefs_append_probe.is_read_only({"options": "rw,relatime"}))

    def test_choose_zone_file_uses_report_to_skip_full_zone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seq = root / "seq"
            seq.mkdir()
            (seq / "0").write_bytes(b"")
            (seq / "1").write_bytes(b"")
            report = root / "report.json"
            report.write_text(
                json.dumps({"zone_list": [{"state": "FULL"}, {"state": "EMPTY"}]}),
                encoding="utf-8",
            )

            chosen = zonefs_append_probe.choose_zone_file(root, report_path=report)

            self.assertEqual(chosen, seq / "1")


if __name__ == "__main__":
    unittest.main()
