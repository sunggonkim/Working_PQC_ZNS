import tempfile
import unittest
from pathlib import Path

try:
    import zns_preflight
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from quasar import zns_preflight


class ZnsPreflightTests(unittest.TestCase):
    def test_scan_zoned_devices_from_fake_sysfs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sys_block = Path(tmp)
            (sys_block / "sda/queue").mkdir(parents=True)
            (sys_block / "sdb/queue").mkdir(parents=True)
            (sys_block / "sda/queue/zoned").write_text("none\n", encoding="utf-8")
            (sys_block / "sdb/queue/zoned").write_text("host-managed\n", encoding="utf-8")

            devices = zns_preflight.scan_zoned_devices(sys_block)

            by_name = {device["name"]: device for device in devices}
            self.assertFalse(by_name["sda"]["is_zoned"])
            self.assertTrue(by_name["sdb"]["is_zoned"])

    def test_device_replay_ready_requires_access_and_report_success(self) -> None:
        device = {
            "is_zoned": True,
            "path_exists": True,
            "readable": True,
            "writable": True,
        }
        good_report = {"available": True, "returncode": 0}
        bad_report = {"available": True, "returncode": 1}

        self.assertTrue(zns_preflight.device_replay_ready(device, good_report))
        self.assertFalse(zns_preflight.device_replay_ready(device | {"writable": False}, good_report))
        self.assertFalse(zns_preflight.device_replay_ready(device, bad_report))
        self.assertFalse(zns_preflight.device_replay_ready(device, None))


if __name__ == "__main__":
    unittest.main()
