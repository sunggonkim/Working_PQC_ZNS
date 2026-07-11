import unittest
from argparse import Namespace

import run_pipeline


class RunPipelineTests(unittest.TestCase):
    def test_pipeline_contains_acceptance_after_artifact_steps(self) -> None:
        args = Namespace(
            events=100,
            schema_events=100,
            workload_events=100,
            liboqs_sessions=1,
            allow_missing_liboqs=False,
        )
        steps = run_pipeline.pipeline_steps(args)
        names = [step.name for step in steps]

        self.assertIn("liboqs-workload", names)
        self.assertIn("fetch-dogi-repo", names)
        self.assertIn("dogi-nullblk-preflight", names)
        self.assertIn("dogi-run-summary", names)
        self.assertIn("replay-file-zns", names)
        self.assertIn("nullblk-zoned-plan", names)
        self.assertIn("nullblk-zoned-preflight", names)
        self.assertIn("c-policy-overhead", names)
        self.assertIn("fdp-mapping", names)
        self.assertLess(names.index("zns-preflight"), names.index("nullblk-zoned-plan"))
        self.assertLess(names.index("dogi-preflight"), names.index("dogi-run-summary"))
        self.assertLess(names.index("dogi-run-summary"), names.index("acceptance"))
        self.assertLess(names.index("c-policy-overhead"), names.index("acceptance"))
        self.assertLess(names.index("fdp-mapping"), names.index("acceptance"))
        self.assertLess(names.index("acceptance"), names.index("report-results"))
        self.assertEqual(names[-1], "report-results")

    def test_selected_steps_rejects_unknown_step(self) -> None:
        args = Namespace(
            events=100,
            schema_events=100,
            workload_events=100,
            liboqs_sessions=1,
            allow_missing_liboqs=False,
        )
        steps = run_pipeline.pipeline_steps(args)

        with self.assertRaises(SystemExit):
            run_pipeline.selected_steps(steps, {"nope"})


if __name__ == "__main__":
    unittest.main()
