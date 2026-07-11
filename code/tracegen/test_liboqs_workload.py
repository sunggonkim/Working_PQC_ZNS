import unittest

try:
    import liboqs_workload as lw
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from tracegen import liboqs_workload as lw


@unittest.skipIf(lw.oqs is None, "liboqs-python is not available")
class LiboqsWorkloadTests(unittest.TestCase):
    def test_measure_one_session(self) -> None:
        event = lw.measure_session(
            0,
            ts=0,
            tenant_id="tenant0",
            kem_name="ML-KEM-512",
            sig_name="ML-DSA-44",
            payload_bytes=4096,
            session_len=100,
        )

        self.assertTrue(event.kem_ok)
        self.assertTrue(event.sig_ok)
        self.assertGreater(event.kem_public_key_bytes, 0)
        self.assertGreater(event.signature_bytes, 0)


if __name__ == "__main__":
    unittest.main()
