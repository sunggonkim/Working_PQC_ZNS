import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import dogi_parity_audit
except ModuleNotFoundError:  # pragma: no cover
    from baselines import dogi_parity_audit


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def run_payload(waf: float = 2.5, *, dogi_select: bool = True) -> dict:
    return {
        "completed": True,
        "gc_write_gib": waf - 1.0,
        "saw_dogi_select": dogi_select,
        "saw_mlp_status": True,
        "saw_zenfs_mount": True,
        "selection_algorithm": "DogiSelect" if dogi_select else "Greedy",
        "user_write_gib": 1.0,
        "waf": waf,
    }


class DogiParityAuditTests(unittest.TestCase):
    def test_audit_separates_direct_evidence_from_full_parity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = {
                "nullblk": root / "nullblk.json",
                "compact_suite": root / "compact-suite.json",
                "dynamic_dogi": root / "dynamic-dogi.json",
                "dynamic_suite": root / "dynamic-suite.json",
                "original_lba_run": root / "original-lba-run.json",
                "original_lba_adapter": root / "original-lba-adapter.json",
                "original_lba_preflight": root / "original-lba-preflight.json",
            }
            write_json(inputs["nullblk"], run_payload(1.7))
            write_json(
                inputs["compact_suite"],
                {
                    "completed": True,
                    "workloads": 6,
                    "aggregate_waf": 2.4,
                    "rows": [run_payload(2.0), run_payload(2.1), run_payload(2.2), run_payload(2.3), run_payload(2.4), run_payload(2.5)],
                },
            )
            write_json(inputs["dynamic_dogi"], run_payload(2.9))
            write_json(
                inputs["dynamic_suite"],
                {
                    "completed_runs": 3,
                    "total_runs": 3,
                    "best_waf": 2.7,
                    "rows": [run_payload(2.9), run_payload(2.8, dogi_select=False), run_payload(2.7, dogi_select=False)],
                },
            )
            write_json(inputs["original_lba_run"], run_payload(3.2))
            write_json(inputs["original_lba_adapter"], {"logical_size_gb": 42})
            write_json(inputs["original_lba_preflight"], {"trace": {"all_lines_usable": True}})

            summary = dogi_parity_audit.audit(inputs)

            self.assertEqual(summary["audit_status"], "substantial-direct-evidence-not-full-parity")
            self.assertEqual(summary["passed_evidence"], summary["total_evidence"])
            self.assertTrue(summary["fatal_if_overclaimed"])
            self.assertIn("not full end-to-end parity", summary["reviewer_answer"])
            self.assertIn("never unit-mix", summary["paper_rule"])

    def test_main_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = {
                "nullblk": root / "nullblk.json",
                "compact_suite": root / "compact-suite.json",
                "dynamic_dogi": root / "dynamic-dogi.json",
                "dynamic_suite": root / "dynamic-suite.json",
                "original_lba_run": root / "original-lba-run.json",
                "original_lba_adapter": root / "original-lba-adapter.json",
                "original_lba_preflight": root / "original-lba-preflight.json",
            }
            for key in ["nullblk", "dynamic_dogi", "original_lba_run"]:
                write_json(inputs[key], run_payload())
            write_json(
                inputs["compact_suite"],
                {"completed": True, "workloads": 6, "aggregate_waf": 2.0, "rows": [run_payload() for _ in range(6)]},
            )
            write_json(
                inputs["dynamic_suite"],
                {"completed_runs": 3, "total_runs": 3, "best_waf": 2.0, "rows": [run_payload() for _ in range(3)]},
            )
            write_json(inputs["original_lba_adapter"], {"logical_size_gb": 42})
            write_json(inputs["original_lba_preflight"], {"trace": {"all_lines_usable": True}})
            out = root / "audit.json"
            md = root / "audit.md"

            with mock.patch.object(dogi_parity_audit, "DEFAULT_INPUTS", inputs):
                with mock.patch("sys.argv", ["dogi_parity_audit.py", "--out", str(out), "--markdown-out", str(md)]):
                    rc = dogi_parity_audit.main()

            self.assertEqual(rc, 0)
            self.assertIn("substantial-direct-evidence-not-full-parity", out.read_text(encoding="utf-8"))
            self.assertIn("Public DOGI Parity Audit", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
