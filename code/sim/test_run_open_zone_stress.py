import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

try:
    import run_open_zone_stress
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from sim import run_open_zone_stress


def default_args(root: Path, **overrides) -> Namespace:
    values = {
        "trace_out": root / "trace.jsonl",
        "trace_summary_out": root / "trace-summary.json",
        "json_out": root / "summary.json",
        "markdown_out": root / "summary.md",
        "figure": root / "summary.png",
        "events": 48,
        "tenants": 6,
        "epoch_len": 4,
        "epoch_namespace": 1_000_000,
        "tenant_skew": 3,
        "expire_jitter": 1,
        "rotation_epochs": 4,
        "pqc_writes_per_tick": 1,
        "pqc_lba_base": 20_000_000,
        "tenant_lba_stride": 100_000,
        "payload_working_set": 32,
        "payload_hot_set": 8,
        "payload_hot_fraction": 0.85,
        "payload_updates_per_tick": 1,
        "trace_missing_hint_rate": 0.0,
        "zones": 0,
        "auto_op_ratio": 0.25,
        "zone_capacity": 16,
        "min_free_zones": 2,
        "lba_bucket_size": 64,
        "quasar_cert_epochs": 4,
        "quasar_min_epoch_fill": 0.0,
        "quasar_residual_fraction": 0.0,
        "open_zone_budget_values": [1],
        "bin_width_values": [4],
        "secret_priority_modes": ["priority"],
        "hint_missing_values": [0.0],
        "base_write_ns": 10_000,
        "gc_copy_ns": 15_000,
        "dogi_ml_ns_per_batch": 600_000,
        "dogi_batch_size": 128,
        "quasar_hint_ns": 200,
        "seed": 11,
        "max_retries": 2,
        "verbose": False,
    }
    values.update(overrides)
    return Namespace(**values)


class OpenZoneStressTests(unittest.TestCase):
    def test_generate_trace_creates_tenant_isolated_epoch_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = default_args(root)

            summary = run_open_zone_stress.generate_trace(args)
            rows = [json.loads(line) for line in args.trace_out.read_text(encoding="utf-8").splitlines()]
            writes = [row for row in rows if row["op"] == "write" and row["intent"] != "PAYLOAD"]

            self.assertGreater(len(writes), 0)
            self.assertGreater(len({row["tenant_id"] for row in writes}), 1)
            self.assertGreater(len({row["epoch_id"] for row in writes}), args.tenants)
            self.assertEqual(summary["tenants"], args.tenants)
            self.assertTrue(args.trace_summary_out.exists())

    def test_tight_open_budget_forces_binned_epoch_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = default_args(root)
            run_open_zone_stress.generate_trace(args)

            rows = run_open_zone_stress.run_experiments(args)
            summary = run_open_zone_stress.summarize(rows)
            candidates = [row for row in rows if row["experiment"] == "open_zone_stress"]

            self.assertEqual(summary["candidate_count"], 1)
            self.assertGreater(candidates[0].get("quasar_binned_epoch_writes", 0), 0)
            self.assertIn("budget_summary", summary)


if __name__ == "__main__":
    unittest.main()
