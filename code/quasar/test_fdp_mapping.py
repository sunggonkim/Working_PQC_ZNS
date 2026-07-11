import json
import tempfile
import unittest
from pathlib import Path

try:
    import fdp_mapping
except ModuleNotFoundError:  # pragma: no cover
    from quasar import fdp_mapping


class FdpMappingTests(unittest.TestCase):
    def test_analyze_trace_reports_handle_purity(self) -> None:
        rows = [
            {
                "op": "write",
                "ts": 0,
                "object_id": 1,
                "lba": 10,
                "size_blocks": 2,
                "intent": "KEM_ARTIFACT",
                "epoch_id": 1,
                "security_class": "SECRET",
                "confidence": "exact",
            },
            {
                "op": "write",
                "ts": 1,
                "object_id": 2,
                "lba": 11,
                "size_blocks": 1,
                "intent": "PAYLOAD",
                "epoch_id": 1,
                "security_class": "PAYLOAD",
                "confidence": "exact",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "trace.jsonl"
            trace.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            result = fdp_mapping.analyze_trace(
                trace,
                handles=4,
                bin_width=1,
                cert_epochs=12,
                min_epoch_fill_blocks=1,
            )

        self.assertEqual(result["writes"], 2)
        self.assertEqual(result["total_blocks"], 3)
        self.assertGreaterEqual(result["occupied_handles"], 1)
        self.assertGreater(result["family_purity"], 0)
        self.assertGreater(result["intent_purity"], 0)
        self.assertEqual(len(result["family_to_handle"]), result["family_count"])

    def test_stable_handle_is_deterministic(self) -> None:
        self.assertEqual(
            fdp_mapping.stable_handle("EPOCH_SECRET:e1:KEM_ARTIFACT:SECRET", 16),
            fdp_mapping.stable_handle("EPOCH_SECRET:e1:KEM_ARTIFACT:SECRET", 16),
        )


if __name__ == "__main__":
    unittest.main()
