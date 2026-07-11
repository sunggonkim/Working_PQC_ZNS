import unittest

try:
    import run_actual_zns_summary_pipeline as runner
except ModuleNotFoundError:  # pragma: no cover
    from sim import run_actual_zns_summary_pipeline as runner


class ActualZnsSummaryPipelineTests(unittest.TestCase):
    def test_pipeline_order_keeps_manifest_hashes_stable(self) -> None:
        steps = runner.pipeline_steps()
        names = [step.name for step in steps]

        self.assertLess(names.index("ycsb-pressure-curve"), names.index("workload-hardness"))
        self.assertLess(names.index("fast-ycsb-pressure-summary"), names.index("workload-hardness"))
        self.assertLess(names.index("fast-dynamic-pressure-summary"), names.index("workload-hardness"))
        self.assertLess(names.index("ycsb-pressure-curve"), names.index("actual-zns-figures"))
        self.assertLess(names.index("reproducibility-manifest-initial"), names.index("reproducibility-validation-initial"))
        self.assertLess(names.index("reproducibility-validation-initial"), names.index("acceptance-after-validation"))
        self.assertLess(names.index("dogi-exact-suite-summary"), names.index("external-readiness-after-validation"))
        self.assertLess(names.index("external-readiness-after-validation"), names.index("claim-matrix-final"))
        self.assertLess(names.index("claim-matrix-final"), names.index("unified-report-final"))
        self.assertLess(names.index("unified-report-final"), names.index("goal-completion-audit"))
        self.assertLess(names.index("goal-completion-audit"), names.index("reproducibility-manifest-final"))
        self.assertLess(names.index("goal-completion-audit-initial"), names.index("reproducibility-manifest-initial"))
        self.assertLess(names.index("reproducibility-manifest-final"), names.index("reproducibility-validation-final"))
        self.assertEqual(names[-1], "reproducibility-validation-final")

    def test_include_tests_appends_unit_tests_after_artifact_validation(self) -> None:
        steps = runner.pipeline_steps(include_tests=True)
        names = [step.name for step in steps]

        self.assertEqual(names[-2], "reproducibility-validation-final")
        self.assertEqual(names[-1], "unit-tests")

    def test_selected_steps_rejects_unknown_step(self) -> None:
        with self.assertRaises(SystemExit):
            runner.selected_steps(runner.pipeline_steps(), {"missing-step"})


if __name__ == "__main__":
    unittest.main()
