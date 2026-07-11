import hashlib
import tempfile
import unittest
from pathlib import Path

try:
    import validate_reproducibility_manifest as validator
except ModuleNotFoundError:  # pragma: no cover
    from sim import validate_reproducibility_manifest as validator


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ValidateReproducibilityManifestTests(unittest.TestCase):
    def test_validate_passes_when_hashes_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "artifact.json"
            data = b'{"ok": true}\n'
            path.write_bytes(data)
            manifest = {
                "artifacts": [
                    {
                        "id": "artifact",
                        "path": "artifact.json",
                        "bytes": len(data),
                        "sha256": digest(data),
                    }
                ]
            }

            summary = validator.validate(manifest, root)
            text = validator.markdown(summary)

        self.assertTrue(summary["passed"])
        self.assertEqual(summary["mismatch_count"], 0)
        self.assertIn("SHA256 Match", text)

    def test_validate_fails_when_hashes_are_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "artifact.json"
            path.write_bytes(b"new")
            manifest = {
                "artifacts": [
                    {
                        "id": "artifact",
                        "path": "artifact.json",
                        "bytes": 3,
                        "sha256": digest(b"old"),
                    }
                ]
            }

            summary = validator.validate(manifest, root)

        self.assertFalse(summary["passed"])
        self.assertEqual(summary["mismatch_count"], 1)
        self.assertFalse(summary["mismatches"][0]["sha256_match"])


if __name__ == "__main__":
    unittest.main()
