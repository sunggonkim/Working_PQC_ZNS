import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

try:
    import report_results
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from sim import report_results


def write_json(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class ReportResultsTests(unittest.TestCase):
    def test_make_report_includes_core_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = Namespace(
                mixed=write_json(
                    root / "mixed.json",
                    [
                        {
                            "policy": "fifo",
                            "waf": 2.0,
                            "gc_write_blocks": 10,
                            "zone_utilization": 0.9,
                            "epoch_impurity": 0.1,
                            "intent_impurity": 0.2,
                            "stale_secret_blocks_remaining": 5,
                        }
                    ],
                ),
                e1=write_json(
                    root / "e1.json",
                    [
                        {"workload": "w", "policy": "fifo", "waf": 2.0},
                        {"workload": "w", "policy": "quasar", "waf": 1.0},
                    ],
                ),
                timeline=write_json(
                    root / "timeline.json",
                    [
                        {"policy": "fifo", "ts": 0, "stale_secret_blocks": 10},
                        {"policy": "quasar", "ts": 0, "stale_secret_blocks": 0},
                    ],
                ),
                acceptance=write_json(root / "acceptance.json", {"passed": True, "passed_gates": 13, "total_gates": 13}),
                liboqs_summary=write_json(
                    root / "liboqs-summary.json",
                    {"sessions": 1, "kem": "ML-KEM-512", "sig": "ML-DSA-44", "all_kem_ok": True, "all_sig_ok": True},
                ),
                liboqs_verification=write_json(
                    root / "liboqs-verification.json",
                    [
                        {"policy": "dogi-history", "waf": 2.0},
                        {"policy": "quasar", "waf": 1.0, "stale_secret_blocks_remaining": 0},
                    ],
                ),
                file_zns_summary=write_json(
                    root / "file-zns.json",
                    {
                        "append_commands": 2,
                        "reset_family_commands": 1,
                        "emulator_reset_zones": 1,
                        "emulator_final_used_zones": 1,
                        "emulator_zone_count": 4,
                    },
                ),
                nullblk_summary=write_json(
                    root / "nullblk-summary.json",
                    {
                        "append_commands": 2,
                        "reset_family_commands": 1,
                        "real_reset_zones": 1,
                        "real_bytes_written": 8192,
                        "real_final_used_zones": 1,
                        "real_zone_count": 4,
                    },
                ),
                zns_preflight=write_json(root / "zns.json", {"zoned_devices": [], "can_run_real_zns_replay": False}),
                dogi_preflight=write_json(
                    root / "dogi.json",
                    {"repo": {"parser_matches_adapter": True}, "can_run_full_prototype": False},
                ),
                dogi_nullblk_preflight=write_json(
                    root / "dogi-nullblk.json",
                    {"can_run_full_prototype": True},
                ),
                dogi_run=write_json(
                    root / "dogi-run.json",
                    {
                        "completed": True,
                        "trace_path": "/tmp/pqc-mixed-adapted.dogi",
                        "user_write_gib": 2.5,
                        "gc_write_gib": 1.7,
                        "waf": 1.68,
                        "zenfs_free_mb": 10048,
                    },
                ),
                nullblk_preflight=write_json(
                    root / "nullblk.json",
                    {"null_blk_module_available": True, "can_create_without_sudo": False},
                ),
            )

            summary, markdown = report_results.make_report(args)

            self.assertTrue(summary["acceptance"]["passed"])
            self.assertIn("## Mixed Trace", markdown)
            self.assertIn("## liboqs Trace", markdown)
            self.assertIn("## External DOGI Prototype", markdown)


if __name__ == "__main__":
    unittest.main()
