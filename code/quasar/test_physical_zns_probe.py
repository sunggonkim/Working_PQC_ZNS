import tempfile
import unittest
from pathlib import Path

try:
    import physical_zns_probe
except ModuleNotFoundError:  # pragma: no cover
    from quasar import physical_zns_probe


class PhysicalZnsProbeTests(unittest.TestCase):
    def test_lba_size_from_id_ns(self) -> None:
        data = {"flbas": 2, "lbafs": [{"ds": 9}, {"ds": 9}, {"ds": 12}]}

        self.assertEqual(physical_zns_probe.lba_size_from_id_ns(data), 4096)

    def test_parse_report_text(self) -> None:
        text = "nr_zones: 905\nSLBA: 0 WP: 0x43500 Cap: 0x43500 State: 0xe0 Type: 0x2 Attrs: 0 AttrsInfo: 0\n"

        parsed = physical_zns_probe.parse_report_text(text)

        self.assertEqual(parsed["nr_zones"], 905)
        self.assertEqual(parsed["first_zone"]["cap"], 0x43500)
        self.assertEqual(parsed["first_zone"]["state"], 0xE0)

    def test_id_ns_summary_computes_bytes(self) -> None:
        data = {
            "flbas": 0,
            "lbafs": [{"ds": 12}],
            "nsze": 10,
            "ncap": 8,
            "nuse": 2,
        }

        summary = physical_zns_probe.id_ns_summary(data)

        self.assertEqual(summary["nsze_bytes"], 40960)
        self.assertEqual(summary["ncap_bytes"], 32768)

    def test_lspci_hint_detects_zn540(self) -> None:
        text = "65:00.0 Non-Volatile memory controller: Western Digital Ultrastar DC ZN540 ZNS NVMe SSD\n"

        hint = physical_zns_probe.lspci_zns_hint(text)

        self.assertTrue(hint["zn540_seen"])


if __name__ == "__main__":
    unittest.main()
