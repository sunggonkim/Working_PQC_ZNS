import argparse
import unittest
from pathlib import Path

try:
    import openssl_oqsprovider_tls_socket_trace as tls
except ModuleNotFoundError:  # pragma: no cover - root-level unittest discovery
    from tracegen import openssl_oqsprovider_tls_socket_trace as tls


class OpenSslOqsProviderTlsSocketTraceTests(unittest.TestCase):
    def test_parse_client_success(self) -> None:
        self.assertTrue(tls.parse_client_success("", "CONNECTION ESTABLISHED\nProtocol version: TLSv1.3\n"))
        self.assertFalse(tls.parse_client_success("", "Protocol version: TLSv1.2\n"))

    def test_event_rows_from_handshakes(self) -> None:
        args = argparse.Namespace(
            group="mlkem768",
            seed=11,
            session_spacing_ms=5,
            session_min_ms=40,
            session_max_ms=40,
            payload_min_bytes=0,
            payload_max_bytes=0,
            tenants=2,
        )

        events = tls.event_rows_from_handshakes(args, [{"ok": True, "returncode": 0, "elapsed_ns": 100}])

        self.assertEqual(events[0]["event"], "tls_kem")
        self.assertEqual(events[0]["kem"], "ML-KEM-768")
        self.assertTrue(events[0]["tls_ok"])
        self.assertEqual(events[0]["session_end_ts"], 40)

    def test_summarize_records_tls_status(self) -> None:
        args = argparse.Namespace(
            openssl_bin="/usr/bin/openssl",
            provider_module_path=Path("/tmp/oqs"),
            group="mlkem768",
            cert=Path("/tmp/server.crt"),
            key=Path("/tmp/server.key"),
        )

        summary = tls.summarize(
            [{"tls_ok": True}],
            [{"elapsed_ns": 100}, {"elapsed_ns": 200}],
            {"writes": 2},
            args,
        )

        self.assertTrue(summary["all_tls_ok"])
        self.assertEqual(summary["kem"], "ML-KEM-768")
        self.assertEqual(summary["avg_client_handshake_ns"], 150)
        self.assertEqual(summary["trace"]["writes"], 2)


if __name__ == "__main__":
    unittest.main()
