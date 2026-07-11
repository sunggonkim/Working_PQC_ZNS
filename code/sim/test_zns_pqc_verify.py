import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

try:
    import zns_pqc_verify as sim
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from sim import zns_pqc_verify as sim


def write_trace(events: list[dict]) -> Path:
    tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".jsonl")
    with tmp:
        for event in events:
            tmp.write(json.dumps(event, sort_keys=True) + "\n")
    return Path(tmp.name)


def default_args(trace: Path, **overrides) -> Namespace:
    args = {
        "trace": trace,
        "zones": 24,
        "zone_capacity": 8,
        "min_free_zones": 2,
        "lba_bucket_size": 16,
        "quasar_cert_epochs": 4,
        "quasar_min_epoch_fill": 0.0,
        "quasar_bin_width": 1,
        "quasar_open_zone_budget": 0,
        "quasar_residual_threshold": 0,
        "quasar_residual_fraction": 0.0,
        "quasar_disable_overflow": False,
        "quasar_disable_secret_priority": False,
        "hint_missing_rate": 0.0,
        "wrong_epoch_rate": 0.0,
        "straggler_rate": 0.0,
        "base_write_ns": 10_000,
        "gc_copy_ns": 15_000,
        "dogi_ml_ns_per_batch": 600_000,
        "dogi_batch_size": 128,
        "quasar_hint_ns": 200,
        "seed": 7,
    }
    args.update(overrides)
    return Namespace(**args)


def secret_write(ts: int, object_id: int, epoch_id: int) -> dict:
    return {
        "op": "write",
        "ts": ts,
        "object_id": object_id,
        "lba": 1000 + object_id,
        "size_blocks": 1,
        "intent": "KEM_ARTIFACT",
        "epoch_id": epoch_id,
        "expire_class": "EPOCH",
        "security_class": "SECRET",
        "confidence": "exact",
        "expire_ts": 100,
    }


def expire(ts: int, object_id: int) -> dict:
    return {
        "op": "expire",
        "ts": ts,
        "object_id": object_id,
        "lba": 1000 + object_id,
        "size_blocks": 1,
    }


class ZnsPqcVerifyTests(unittest.TestCase):
    def test_quasar_resets_expired_secret_zone(self) -> None:
        events = [secret_write(i, i, 0) for i in range(6)]
        events.extend(expire(100 + i, i) for i in range(6))
        trace = write_trace(events)

        stats = sim.run_policy(default_args(trace), "quasar")

        self.assertEqual(stats["gc_write_blocks"], 0)
        self.assertEqual(stats["stale_secret_blocks_remaining"], 0)
        self.assertGreater(stats["resets"], 0)
        self.assertGreater(stats["reset_eligible_zones"], 0)

    def test_missing_hints_fall_back_without_losing_live_data(self) -> None:
        events = [secret_write(i, i, 0) for i in range(6)]
        events.extend(expire(100 + i, i) for i in range(3))
        trace = write_trace(events)

        stats = sim.run_policy(default_args(trace, hint_missing_rate=1.0), "quasar")

        self.assertEqual(stats["hint_missing_injected"], 6)
        self.assertEqual(stats["live_blocks"], 3)
        self.assertEqual(stats["quasar_overflow_writes"], 6)
        self.assertGreaterEqual(stats["stale_secret_blocks_remaining"], 3)

    def test_hybrid_missing_hints_use_dogi_fallback(self) -> None:
        events = [secret_write(i, i, i % 2) for i in range(10)]
        events.extend(expire(100 + i, i) for i in range(10))
        trace = write_trace(events)

        stats = sim.run_policy(default_args(trace, hint_missing_rate=1.0), "quasar-dogi-hybrid")

        self.assertEqual(stats["hint_missing_injected"], 10)
        self.assertEqual(stats["hybrid_quasar_managed_writes"], 0)
        self.assertEqual(stats["hybrid_payload_fallback_writes"], 10)
        self.assertEqual(stats["fallback_prediction_samples"], 10)

    def test_open_zone_budget_bins_non_priority_epoch_families(self) -> None:
        events = [secret_write(i, i, i) for i in range(8)]
        trace = write_trace(events)

        stats = sim.run_policy(
            default_args(
                trace,
                quasar_open_zone_budget=1,
                quasar_bin_width=4,
                quasar_min_epoch_fill=0.0,
            ),
            "quasar",
        )

        self.assertEqual(stats["quasar_exact_epoch_writes"], 1)
        self.assertEqual(stats["quasar_binned_epoch_writes"], 7)

    def test_adaptive_quasar_bins_tiny_epochs_before_exact_admission(self) -> None:
        events = [secret_write(i, i, i) for i in range(8)]
        trace = write_trace(events)

        stats = sim.run_policy(
            default_args(
                trace,
                quasar_open_zone_budget=1,
                quasar_adaptive_exact_min_blocks=4,
                quasar_adaptive_tenant_bin_width=4,
            ),
            "quasar-adaptive",
        )

        self.assertEqual(stats["quasar_exact_epoch_writes"], 0)
        self.assertEqual(stats["quasar_binned_epoch_writes"], 8)
        self.assertEqual(stats["quasar_tenant_bin_writes"], 8)
        self.assertEqual(stats["quasar_exact_rejected_size_writes"], 8)

    def test_adaptive_quasar_coarse_bins_when_exact_budget_is_full(self) -> None:
        events = [secret_write(i, i, 0) for i in range(4)]
        events.extend(secret_write(10 + i, 10 + i, 100 + (i // 2)) for i in range(6))
        trace = write_trace(events)

        stats = sim.run_policy(
            default_args(
                trace,
                quasar_open_zone_budget=1,
                quasar_adaptive_exact_min_blocks=2,
                quasar_adaptive_tenant_bin_width=4,
                quasar_adaptive_coarse_bin_width=1_000,
                quasar_adaptive_coarse_pressure=0.5,
            ),
            "quasar-adaptive",
        )

        self.assertGreater(stats["quasar_exact_epoch_writes"], 0)
        self.assertGreater(stats["quasar_coarse_bin_writes"], 0)
        self.assertGreater(stats["quasar_exact_rejected_budget_writes"], 0)

    def test_dogi_history_reports_prediction_samples(self) -> None:
        events = [secret_write(i, i, i % 2) for i in range(20)]
        events.extend(expire(80 + i, i) for i in range(20))
        trace = write_trace(events)

        stats = sim.run_policy(default_args(trace), "dogi-history")

        self.assertEqual(stats["prediction_samples"], 20)
        self.assertIn("prediction_accuracy", stats)
        self.assertIn("write_latency_p99_ns", stats)
        self.assertGreater(stats["write_latency_p99_ns"], 0)

    def test_history_heuristics_run_without_protocol_hints(self) -> None:
        events = [secret_write(i, i, i % 3) for i in range(18)]
        events.extend(expire(60 + i, i) for i in range(18))
        trace = write_trace(events)

        for policy in ("sepbit-style", "midas-style"):
            with self.subTest(policy=policy):
                stats = sim.run_policy(default_args(trace), policy)
                self.assertEqual(stats["prediction_samples"], 18)
                self.assertGreater(stats["user_write_blocks"], 0)
                self.assertIn("prediction_accuracy", stats)

    def test_fast_exposure_counter_matches_scan(self) -> None:
        events = [secret_write(i, i, i % 2) for i in range(10)]
        events.extend(expire(100 + i, i) for i in range(5))
        simulator = sim.Simulator(
            policy=sim.FifoPolicy(),
            zone_count=24,
            zone_capacity=8,
            min_free_zones=2,
            residual_threshold=0,
            hint_missing_rate=0.0,
            wrong_epoch_rate=0.0,
            straggler_rate=0.0,
            random_seed=7,
            base_write_ns=10_000,
            gc_copy_ns=15_000,
            policy_cpu_ns_per_write=0,
        )

        for event in events:
            simulator.current_ts = int(event["ts"])
            if event["op"] == "write":
                simulator.write(event)
            else:
                simulator.expire(event)
            self.assertEqual(
                simulator._remaining_secret_exposure(),
                simulator._scan_remaining_secret_exposure(),
            )


if __name__ == "__main__":
    unittest.main()
