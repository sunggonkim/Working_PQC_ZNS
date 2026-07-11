import unittest

try:
    import report_deployment_policy_selector as selector
except ModuleNotFoundError:  # pragma: no cover
    from sim import report_deployment_policy_selector as selector


class DeploymentPolicySelectorTests(unittest.TestCase):
    def test_summarize_builds_four_passing_modes(self) -> None:
        adaptive = {
            "decision": "keep-current-hybrid",
            "ycsb_pressure": {"current_wins": 4, "adaptive_wins": 0, "workloads": {"a": {}, "b": {}, "c": {}, "d": {}}},
            "sysbench_pressure": {"current_wins": 2, "adaptive_wins": 0, "workloads": {"s1": {}, "s2": {}}},
        }
        multitenant = {
            "decision": "add-tenant-isolation-mode",
            "physical": {
                "tenant_isolation_vs_current": {
                    "reset_secret_tenant_impurity_reduction": 1.0,
                    "waf_increase": 0.01,
                    "gc_extra_blocks": 10,
                    "physical_reset_extra_commands": 5,
                }
            },
        }
        residual = {
            "decision": "use-residual-fallback-as-strict-exposure-mode",
            "controller_profiles": [
                {"profile": "low_overhead"},
                {"profile": "balanced"},
                {"profile": "strict_zero_wait"},
            ],
            "controller_decisions": [
                {"profile": "strict_zero_wait", "selected": {"secret_waiting_end": 0, "physical_waf": 1.1}},
                {"profile": "strict_zero_wait", "selected": {"secret_waiting_end": 0, "physical_waf": 1.2}},
                {"profile": "strict_zero_wait", "selected": {"secret_waiting_end": 0, "physical_waf": 1.7}},
                {"profile": "strict_zero_wait", "selected": {"secret_waiting_end": 0, "physical_waf": 3.5}},
            ],
        }
        robustness = {
            "missing_hint_5pct": {"failed_rows": 0},
            "wrong_epoch_5pct": {"failed_rows": 0},
            "straggler_5pct_epoch_bin_5_residual_12288": {
                "failed_rows": 0,
                "hybrid": {"secret_waiting_end": 0, "physical_waf": 1.7},
            },
        }
        hardness = {"passed": True}

        summary = selector.summarize(adaptive, multitenant, residual, robustness, hardness)
        text = selector.markdown(summary)

        self.assertTrue(summary["passed"])
        self.assertEqual(summary["passed_modes"], 4)
        self.assertIn("tenant-isolation", text)
        self.assertIn("strict-residual", text)
        self.assertIn("not a single universal knob", text)


if __name__ == "__main__":
    unittest.main()
