import tempfile
import unittest
from pathlib import Path

try:
    import run_adaptive_admission
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from sim import run_adaptive_admission


class AdaptiveAdmissionTests(unittest.TestCase):
    def test_configs_include_adaptive_hybrid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = run_adaptive_admission.argparse.Namespace(
                trace_out=root / "trace.jsonl",
                trace_summary_out=root / "trace-summary.json",
                events=16,
                tenants=4,
                epoch_len=4,
                epoch_namespace=1_000_000,
                tenant_skew=2,
                expire_jitter=1,
                rotation_epochs=4,
                pqc_writes_per_tick=1,
                pqc_lba_base=20_000_000,
                tenant_lba_stride=100_000,
                payload_working_set=16,
                payload_hot_set=4,
                payload_hot_fraction=0.8,
                payload_updates_per_tick=1,
                zones=0,
                auto_op_ratio=0.25,
                zone_capacity=16,
                min_free_zones=2,
                lba_bucket_size=64,
                quasar_cert_epochs=4,
                quasar_residual_fraction=0.0,
                adaptive_exact_min_blocks=4,
                adaptive_tenant_bin_width=4,
                adaptive_coarse_bin_width=1_000_000,
                adaptive_coarse_pressure=0.75,
                adaptive_family_pressure=8.0,
                adaptive_urgent_lifetime=8,
                base_write_ns=10_000,
                gc_copy_ns=15_000,
                dogi_ml_ns_per_batch=600_000,
                dogi_batch_size=128,
                quasar_hint_ns=200,
                seed=13,
                max_retries=1,
            )
            run_adaptive_admission.stress.generate_trace(run_adaptive_admission.trace_args(args))
            configs = run_adaptive_admission.configs(args, zones=8)

            policies = [policy for _name, policy, _ns in configs]

            self.assertIn("quasar-adaptive-hybrid", policies)
            self.assertIn("dogi-history", policies)


if __name__ == "__main__":
    unittest.main()
