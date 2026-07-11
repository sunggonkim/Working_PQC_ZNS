import argparse
import unittest
from pathlib import Path

try:
    import openssl_oqsprovider_service_trace as service
except ModuleNotFoundError:  # pragma: no cover - root-level unittest discovery
    from tracegen import openssl_oqsprovider_service_trace as service


class OpenSslOqsProviderServiceTraceTests(unittest.TestCase):
    def test_parse_measurements_jsonl(self) -> None:
        rows = service.parse_measurements(
            '{"session":0,"kem_ok":true,"sig_ok":true,"ciphertext_bytes":1088}\n'
            '{"session":1,"kem_ok":true,"sig_ok":true,"ciphertext_bytes":1088}\n'
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["ciphertext_bytes"], 1088)

    def test_event_rows_from_measurements(self) -> None:
        events = service.event_rows_from_measurements(
            [
                {
                    "session": 0,
                    "kem_ok": True,
                    "sig_ok": True,
                    "ciphertext_bytes": 1088,
                    "shared_secret_bytes": 32,
                    "signature_bytes": 3309,
                    "kem_keygen_ns": 1,
                    "kem_encap_ns": 2,
                    "kem_decap_ns": 3,
                    "sig_keygen_ns": 4,
                    "sig_sign_ns": 5,
                    "sig_verify_ns": 6,
                }
            ],
            kem="ML-KEM-768",
            sig="ML-DSA-65",
            tenants=4,
            session_spacing_ms=10,
            session_min_ms=50,
            session_max_ms=50,
            payload_min_bytes=0,
            payload_max_bytes=0,
            seed=3,
            event_type="tls_handshake",
            provider_module_path=Path("/tmp/oqs"),
            probe_bin=Path("/tmp/probe"),
        )

        self.assertEqual(events[0]["ts"], 0)
        self.assertEqual(events[0]["session_end_ts"], 50)
        self.assertEqual(events[0]["kem"], "ML-KEM-768")
        self.assertTrue(events[0]["kem_ok"])

    def test_summarize_marks_c_api_kem_supported(self) -> None:
        args = argparse.Namespace(
            provider_module_path=Path("/tmp/oqs"),
            probe_bin=Path("/tmp/probe"),
            kem="ML-KEM-768",
            sig="ML-DSA-65",
            kem_alg="mlkem768",
            sig_alg="mldsa65",
        )
        summary = service.summarize(
            [
                {
                    "kem_ok": True,
                    "sig_ok": True,
                    "ciphertext_bytes": 1088,
                    "shared_secret_bytes": 32,
                    "signature_bytes": 3309,
                    "kem_keygen_ns": 10,
                    "kem_encap_ns": 20,
                    "kem_decap_ns": 30,
                    "sig_keygen_ns": 40,
                    "sig_sign_ns": 50,
                    "sig_verify_ns": 60,
                }
            ],
            {"writes": 4},
            args=args,
        )

        self.assertTrue(summary["kem_encap_c_api_supported"])
        self.assertTrue(summary["all_kem_ok"])
        self.assertEqual(summary["ciphertext_bytes"], 1088)
        self.assertEqual(summary["trace"]["writes"], 4)


if __name__ == "__main__":
    unittest.main()
