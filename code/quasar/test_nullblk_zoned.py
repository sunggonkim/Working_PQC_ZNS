import tempfile
import unittest
from pathlib import Path

try:
    import nullblk_zoned
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from quasar import nullblk_zoned


class NullBlkZonedTests(unittest.TestCase):
    def test_plan_contains_zoned_parameters(self) -> None:
        config = nullblk_zoned.NullBlkConfig(
            name="nullb_quasar",
            size_mib=1024,
            blocksize=4096,
            zone_size_mib=64,
            zone_capacity_mib=64,
            zone_max_open=32,
            zone_max_active=64,
            memory_backed=True,
        )

        lines = nullblk_zoned.command_plan(config, Path("/sys/kernel/config/nullb"))
        joined = "\n".join(lines)

        self.assertIn("modprobe null_blk configfs=1", joined)
        self.assertIn("/sys/kernel/config/nullb/nullb_quasar/zoned", joined)
        self.assertIn("/sys/kernel/config/nullb/nullb_quasar/zone_size", joined)
        self.assertIn("/sys/kernel/config/nullb/nullb_quasar/power", joined)
        self.assertIn("blkzone report /dev/nullb_quasar", joined)

    def test_preflight_reports_fake_configfs_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "nullb"
            root.mkdir()

            result = nullblk_zoned.preflight(root)

            self.assertEqual(result["configfs_root"], str(root))
            self.assertTrue(result["configfs_root_exists"])
            self.assertIn("null_blk_module_available", result)

    def test_write_attr_requires_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            attr = Path(tmp) / "zoned"
            attr.write_text("0", encoding="utf-8")

            nullblk_zoned.write_attr(attr, "1")

            self.assertEqual(attr.read_text(encoding="utf-8"), "1")
            with self.assertRaises(FileNotFoundError):
                nullblk_zoned.write_attr(Path(tmp) / "missing", "1")


if __name__ == "__main__":
    unittest.main()
