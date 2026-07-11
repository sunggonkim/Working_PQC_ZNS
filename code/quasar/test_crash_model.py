import json
import tempfile
import unittest
from pathlib import Path

try:
    import crash_model
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from quasar import crash_model


def write_trace(path: Path) -> None:
    rows = [
        {
            "op": "write",
            "ts": 1,
            "object_id": 1,
            "lba": 11,
            "size_blocks": 1,
            "intent": "KEM_ARTIFACT",
            "epoch_id": 0,
            "security_class": "SECRET",
        },
        {
            "op": "expire",
            "ts": 100,
            "object_id": 1,
            "lba": 11,
            "size_blocks": 1,
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


class CrashModelTests(unittest.TestCase):
    def test_recovery_cases_preserve_reset_safety(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "trace.jsonl"
            write_trace(trace)

            cases, summary = crash_model.run_cases(trace)

            self.assertEqual(summary["failed_cases"], 0)
            self.assertEqual(summary["passed_cases"], len(cases))
            self.assertFalse(summary["unsafe_reset_attempted"])
            self.assertGreater(summary["fully_expired_families"], 0)
            self.assertTrue(all(case.live_objects_reachable for case in cases))

    def test_metadata_cost_reports_recovery_overhead(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "trace.jsonl"
            write_trace(trace)

            cost = crash_model.metadata_cost(trace, zone_capacity_blocks=4)

            self.assertEqual(cost["write_count"], 1)
            self.assertGreater(cost["metadata_bytes"]["total"], 0)
            self.assertGreater(cost["metadata_overhead_percent_of_user_bytes"], 0)
            self.assertGreater(cost["recovery_scan"]["estimated_scan_zones"], 0)
            self.assertGreaterEqual(cost["resettable_family_count"], 1)


if __name__ == "__main__":
    unittest.main()
