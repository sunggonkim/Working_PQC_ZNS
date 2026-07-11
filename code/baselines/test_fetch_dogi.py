import tempfile
import unittest
from pathlib import Path

try:
    import fetch_dogi
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from baselines import fetch_dogi


class FetchDogiTests(unittest.TestCase):
    def test_repo_ready_checks_required_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "DOGI"
            (repo / "prototype/app").mkdir(parents=True)
            (repo / "prototype/app/global.cc").write_text("", encoding="utf-8")
            (repo / "prototype/app/main.cc").write_text("", encoding="utf-8")
            (repo / "prototype/CMakeLists.txt").write_text("", encoding="utf-8")

            self.assertTrue(fetch_dogi.repo_ready(repo))

    def test_fetch_is_noop_when_repo_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "DOGI"
            (repo / "prototype/app").mkdir(parents=True)
            (repo / "prototype/app/global.cc").write_text("", encoding="utf-8")
            (repo / "prototype/app/main.cc").write_text("", encoding="utf-8")
            (repo / "prototype/CMakeLists.txt").write_text("", encoding="utf-8")

            result = fetch_dogi.fetch(repo)

            self.assertEqual(result["action"], "already-present")
            self.assertTrue(result["ready"])


if __name__ == "__main__":
    unittest.main()
