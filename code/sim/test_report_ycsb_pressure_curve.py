import json
import tempfile
import unittest
from pathlib import Path

try:
    import report_ycsb_pressure_curve as curve
except ModuleNotFoundError:  # pragma: no cover
    from sim import report_ycsb_pressure_curve as curve


def packed_report(stem: str, dogi_waf: float, dogi_gc: int, dogi_stale: int, hybrid_resets: int) -> dict:
    rows = {}
    for policy in curve.BASELINES:
        rows[f"{policy}::secret-group"] = {
            "sim_waf": dogi_waf if policy == "dogi-history" else 1.0,
            "sim_gc_blocks": dogi_gc if policy == "dogi-history" else 0,
            "sim_stale_secret_blocks": dogi_stale,
            "physical_reset_commands": 0,
            "secret_blocks_waiting_for_physical_reset": 7,
            "max_live_physical_zones": 3,
        }
    rows["quasar-dogi-hybrid::secret-group"] = {
        "sim_waf": 1.0,
        "sim_gc_blocks": 0,
        "sim_stale_secret_blocks": 0,
        "physical_reset_commands": hybrid_resets,
        "secret_blocks_waiting_for_physical_reset": 0,
        "max_live_physical_zones": 5,
    }
    return {
        "traces": [f"artifacts/traces/{stem}.jsonl"],
        "logical_zones": 512,
        "summary": {
            "row_count": 6,
            "failed_rows": 0,
            "wall_time_s": 1.0,
            "by_policy_packing": rows,
        },
    }


class ReportYcsbPressureCurveTests(unittest.TestCase):
    def test_build_summary_identifies_easy_and_pressure_points(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            easy = root / "ycsb-a-pqc2000.json"
            hard = root / "ycsb-a-pqc8000.json"
            easy.write_text(json.dumps(packed_report("ycsb-a-pqc2000", 1.0, 0, 100, 2)), encoding="utf-8")
            hard.write_text(json.dumps(packed_report("ycsb-a-pqc8000", 1.2, 40, 200, 4)), encoding="utf-8")

            summary = curve.build_summary([easy, hard])

        self.assertEqual(summary["row_count"], 2)
        self.assertEqual(summary["failed_rows"], 0)
        self.assertEqual(summary["semantic_gap_rows"], 2)
        self.assertEqual(summary["waf_pressure_rows"], 1)
        self.assertFalse(summary["rows"][0]["waf_pressure"])
        self.assertTrue(summary["rows"][1]["waf_pressure"])
        self.assertIn("p2000", curve.markdown(summary))


if __name__ == "__main__":
    unittest.main()
