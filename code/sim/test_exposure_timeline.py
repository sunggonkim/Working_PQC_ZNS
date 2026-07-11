import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

try:
    import exposure_timeline as timeline
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from sim import exposure_timeline as timeline


def write_trace(events: list[dict]) -> Path:
    tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".jsonl")
    with tmp:
        for event in events:
            tmp.write(json.dumps(event, sort_keys=True) + "\n")
    return Path(tmp.name)


def args_for(trace: Path) -> Namespace:
    return Namespace(
        trace=trace,
        zones=16,
        zone_capacity=8,
        min_free_zones=2,
        lba_bucket_size=16,
        quasar_cert_epochs=4,
        quasar_min_epoch_fill=0.0,
        quasar_bin_width=1,
        quasar_open_zone_budget=0,
        quasar_residual_threshold=0,
        quasar_residual_fraction=0.0,
        quasar_disable_overflow=False,
        quasar_disable_secret_priority=False,
        hint_missing_rate=0.0,
        wrong_epoch_rate=0.0,
        straggler_rate=0.0,
        base_write_ns=10_000,
        gc_copy_ns=15_000,
        dogi_ml_ns_per_batch=600_000,
        dogi_batch_size=128,
        quasar_hint_ns=200,
        seed=7,
        sample_interval=10,
        sample_on_expire=False,
    )


def secret_write(ts: int, object_id: int) -> dict:
    return {
        "op": "write",
        "ts": ts,
        "object_id": object_id,
        "lba": 100 + object_id,
        "size_blocks": 1,
        "intent": "KEM_ARTIFACT",
        "epoch_id": 0,
        "expire_class": "EPOCH",
        "security_class": "SECRET",
        "confidence": "exact",
    }


def expire(ts: int, object_id: int) -> dict:
    return {
        "op": "expire",
        "ts": ts,
        "object_id": object_id,
        "lba": 100 + object_id,
        "size_blocks": 1,
    }


class ExposureTimelineTests(unittest.TestCase):
    def test_quasar_drops_stale_secret_blocks_after_epoch_expire(self) -> None:
        events = [secret_write(i, i) for i in range(4)]
        events.extend(expire(100 + i, i) for i in range(4))
        trace = write_trace(events)
        args = args_for(trace)

        fifo_rows = timeline.run_timeline(args, "fifo")
        quasar_rows = timeline.run_timeline(args, "quasar")

        self.assertGreater(max(row["stale_secret_blocks"] for row in fifo_rows), 0)
        self.assertEqual(quasar_rows[-1]["stale_secret_blocks"], 0)

    def test_hybrid_timeline_accepts_prefill_events(self) -> None:
        prefill = dict(secret_write(0, 1000))
        prefill["op"] = "prefill"
        prefill["intent"] = "PAYLOAD"
        prefill["security_class"] = "PAYLOAD"
        events = [prefill]
        events.extend(secret_write(i + 1, i) for i in range(4))
        events.extend(expire(100 + i, i) for i in range(4))
        trace = write_trace(events)

        rows = timeline.run_timeline(args_for(trace), "quasar-dogi-hybrid")

        self.assertEqual(rows[-1]["stale_secret_blocks"], 0)


if __name__ == "__main__":
    unittest.main()
