import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import dogi_exact_suite_summary as suite
except ModuleNotFoundError:  # pragma: no cover
    from baselines import dogi_exact_suite_summary as suite


def write_run(path: Path, placement: str, waf: float, completed: bool = True) -> None:
    user = 2.0
    gc = user * (waf - 1.0)
    path.write_text(
        (
            "{\n"
            f'  "completed": {str(completed).lower()},\n'
            f'  "gc_write_gib": {gc},\n'
            f'  "placement_algorithm": "{placement}",\n'
            f'  "selection_algorithm": "{placement}",\n'
            '  "saw_zenfs_mount": true,\n'
            '  "trace_path": "/tmp/trace.dogi",\n'
            f'  "user_write_gib": {user},\n'
            f'  "waf": {waf}\n'
            "}\n"
        ),
        encoding="utf-8",
    )


class DogiExactSuiteSummaryTests(unittest.TestCase):
    def test_summarize_selects_best_completed_placement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = {
                "DOGI": root / "dogi.json",
                "Greedy": root / "greedy.json",
                "CostBenefit": root / "costbenefit.json",
            }
            write_run(runs["DOGI"], "DOGI", 2.9)
            write_run(runs["Greedy"], "Greedy", 2.7)
            write_run(runs["CostBenefit"], "CostBenefit", 2.8)

            summary = suite.summarize(runs)

            self.assertEqual(summary["completed_runs"], 3)
            self.assertEqual(summary["total_runs"], 3)
            self.assertEqual(summary["best_placement"], "Greedy")
            self.assertAlmostEqual(summary["best_waf"], 2.7)
            self.assertIn("not be mixed", summary["caveat"])

    def test_main_writes_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = {
                "DOGI": root / "dogi.json",
                "Greedy": root / "greedy.json",
                "CostBenefit": root / "costbenefit.json",
            }
            for placement, path in runs.items():
                write_run(path, placement, 2.5)
            out = root / "suite.json"
            md = root / "suite.md"

            with mock.patch.object(suite, "DEFAULT_RUNS", runs):
                with mock.patch("sys.argv", ["dogi_exact_suite_summary.py", "--out", str(out), "--markdown-out", str(md)]):
                    rc = suite.main()

            self.assertEqual(rc, 0)
            self.assertIn("Exact Public DOGI Prototype Suite", md.read_text(encoding="utf-8"))
            self.assertIn('"completed_runs": 3', out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
