import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

try:
    import per_cohort_key_erase as key_erase
except ModuleNotFoundError:  # pragma: no cover
    from quasar import per_cohort_key_erase as key_erase


class PerCohortKeyEraseTests(unittest.TestCase):
    def test_per_cohort_destroy_preserves_unrelated_cohorts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = Namespace(
                cohorts=4,
                records_per_cohort=4,
                payload_bytes=128,
                tenants=2,
                destroy_cohort="epoch-2",
                store_out=root / "store.jsonl",
                out=root / "summary.json",
                markdown_out=root / "summary.md",
            )

            summary = key_erase.run(args)

        self.assertEqual(summary["target_records"], 4)
        self.assertTrue(summary["target_records_inaccessible_after_destroy"])
        self.assertTrue(summary["unrelated_cohorts_preserved"])
        self.assertTrue(summary["wrong_key_rejection"]["all_rejected"])
        self.assertFalse(summary["sanitize_called"])

    def test_markdown_states_boundary(self) -> None:
        md = key_erase.markdown(
            {
                "cohorts": 2,
                "records": 4,
                "destroyed_cohort": "epoch-1",
                "store_bytes": 100,
                "before_destroy": {"ok": 4},
                "after_destroy": {"ok": 2, "missing_key": 2},
                "wrong_key_rejection": {"attempted": 2, "rejected": 2},
                "unrelated_cohorts_preserved": True,
                "claim_boundary": "not proof that zone reset physically erases NAND",
            }
        )

        self.assertIn("Per-Cohort Key-Isolated Crypto Erase", md)
        self.assertIn("cohort-scoped erase path", md)
        self.assertIn("not proof that zone reset physically erases NAND", md)


if __name__ == "__main__":
    unittest.main()
