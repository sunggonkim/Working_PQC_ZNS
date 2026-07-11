import json
import tempfile
import unittest
from pathlib import Path

try:
    import oqs_tls_trace as oqs
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from tracegen import oqs_tls_trace as oqs


class OqsTlsTraceTests(unittest.TestCase):
    def test_expand_handshake_event_to_quasar_trace(self) -> None:
        events = [
            oqs.CryptoEvent(
                ts=10,
                event="handshake",
                session_id="s1",
                tenant_id="tenantA",
                kem="ML-KEM-768",
                sig="ML-DSA-65",
                payload_bytes=8192,
                session_end_ts=100,
            )
        ]

        rows = oqs.expand_events(
            events,
            epoch_len_ms=1000,
            rotation_epochs=4,
            session_jitter_ms=0,
            lba_space=100_000,
            seed=1,
        )

        writes = [row for row in rows if row["op"] == "write"]
        expires = [row for row in rows if row["op"] == "expire"]
        intents = {row["intent"] for row in writes}
        self.assertIn("KEM_ARTIFACT", intents)
        self.assertIn("EPHEMERAL_SECRET", intents)
        self.assertIn("CERT_METADATA", intents)
        self.assertIn("SIGNATURE_LOG", intents)
        self.assertIn("PAYLOAD", intents)
        self.assertGreaterEqual(len(expires), 2)
        self.assertTrue(all(row["confidence"] == "exact" for row in writes))

    def test_jsonl_and_dogi_outputs(self) -> None:
        rows = oqs.expand_events(
            [
                oqs.CryptoEvent(
                    ts=0,
                    event="handshake",
                    session_id="s2",
                    tenant_id="tenant0",
                    kem="ML-KEM-512",
                    sig="ML-DSA-44",
                    payload_bytes=0,
                    session_end_ts=50,
                )
            ],
            epoch_len_ms=100,
            rotation_epochs=2,
            session_jitter_ms=0,
            lba_space=10_000,
            seed=2,
        )
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "trace.jsonl"
            dogi = Path(tmp) / "trace.dogi"
            oqs.write_jsonl(jsonl, rows)
            extra = oqs.write_dogi(dogi, rows, delete_markers=True)

            loaded = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(loaded), len(rows))
            self.assertGreater(extra["dogi_tombstones"], 0)
            self.assertGreater(dogi.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
