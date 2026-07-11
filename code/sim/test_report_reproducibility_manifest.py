import json
import tempfile
import unittest
from pathlib import Path

try:
    import report_reproducibility_manifest as manifest
except ModuleNotFoundError:  # pragma: no cover
    from sim import report_reproducibility_manifest as manifest


class ReproducibilityManifestTests(unittest.TestCase):
    def test_summarize_records_hashes_and_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for item in manifest.ARTIFACTS:
                path = root / item["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                if item["id"] == "acceptance":
                    path.write_text(json.dumps({"passed": True, "passed_gates": 1, "total_gates": 1}), encoding="utf-8")
                elif item["id"] == "external_readiness":
                    path.write_text(json.dumps({"paper_ready_external": True, "blockers": [], "pending": []}), encoding="utf-8")
                elif item["id"] == "deployment_selector":
                    path.write_text(json.dumps({"passed": True, "passed_modes": 4, "total_modes": 4}), encoding="utf-8")
                elif item["id"] == "workload_hardness":
                    path.write_text(json.dumps({"passed": True}), encoding="utf-8")
                elif item["path"].endswith(".json"):
                    path.write_text(json.dumps({"ok": True}), encoding="utf-8")
                else:
                    path.write_bytes(b"png")

            summary = manifest.summarize(root)
            text = manifest.markdown(summary)

        self.assertTrue(summary["passed"])
        self.assertEqual(summary["artifact_count"], len(manifest.ARTIFACTS))
        self.assertFalse(summary["missing_or_empty"])
        self.assertTrue(all(item["sha256"] for item in summary["artifacts"]))
        self.assertIn("Regeneration Commands", text)
        self.assertIn("acceptance", summary["readiness"])


if __name__ == "__main__":
    unittest.main()
