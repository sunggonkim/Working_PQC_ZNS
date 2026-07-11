import unittest

try:
    import openssl_oqsprovider_workload as work
except ModuleNotFoundError:  # pragma: no cover - root-level unittest discovery
    from tracegen import openssl_oqsprovider_workload as work


class OpenSslOqsProviderWorkloadTests(unittest.TestCase):
    def test_algorithm_name_normalization(self) -> None:
        self.assertEqual(work.canonical_kem("mlkem768"), "ML-KEM-768")
        self.assertEqual(work.canonical_kem("ML-KEM-1024"), "ML-KEM-1024")
        self.assertEqual(work.canonical_sig("mldsa65"), "ML-DSA-65")
        self.assertEqual(work.canonical_sig("ML-DSA-87"), "ML-DSA-87")

    def test_summarize_records_provider_measurements(self) -> None:
        event = work.OpenSslMeasuredEvent(
            ts=0,
            event="kms_wrap",
            session_id="s0",
            tenant_id="tenant0",
            kem="ML-KEM-768",
            sig="ML-DSA-65",
            payload_bytes=0,
            session_end_ts=10,
            openssl_bin="/usr/bin/openssl",
            provider_module_path="/tmp/ossl-mod",
            kem_provider_name="mlkem768",
            sig_provider_name="mldsa65",
            kem_private_pem_bytes=4946,
            kem_public_pem_bytes=1686,
            sig_private_pem_bytes=8196,
            sig_public_pem_bytes=2726,
            signature_bytes=3309,
            kem_keypair_ns=100,
            kem_pubout_ns=200,
            sig_keypair_ns=300,
            sig_pubout_ns=400,
            sig_sign_ns=500,
            sig_verify_ns=600,
            sig_ok=True,
        )
        summary = work.summarize([event], {"kem_provider_detected": True}, {"writes": 3})

        self.assertEqual(summary["sessions"], 1)
        self.assertTrue(summary["all_sig_ok"])
        self.assertEqual(summary["signature_bytes"], 3309)
        self.assertFalse(summary["kem_encap_cli_supported"])
        self.assertEqual(summary["trace"]["writes"], 3)


if __name__ == "__main__":
    unittest.main()
