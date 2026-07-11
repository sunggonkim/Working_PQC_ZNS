import tempfile
import unittest
from pathlib import Path

try:
    import dogi_preflight
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from baselines import dogi_preflight


def make_fake_dogi_repo(root: Path) -> None:
    (root / "prototype/app").mkdir(parents=True)
    (root / "prototype").mkdir(exist_ok=True)
    (root / "prototype/CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.10)\n", encoding="utf-8")
    (root / "prototype/app/CMakeLists.txt").write_text("add_executable(app main.cc)\n", encoding="utf-8")
    (root / "prototype/app/global.cc").write_text(
        '\n'.join(
            [
                'int LogicalSizeGb = 8;',
                'char wk_name[128] = "/tmp/trace";',
                'const char kZnsDevicePath[] = "/dev/nvme0n1";',
            ]
        ),
        encoding="utf-8",
    )
    (root / "prototype/app/main.cc").write_text(
        '\n'.join(
            [
                'if (result[1] != "1") continue;',
                'start = atoll(result[2].c_str())*4096;',
                'length = atoi(result[3].c_str());',
            ]
        ),
        encoding="utf-8",
    )


class DogiPreflightTests(unittest.TestCase):
    def test_preflight_recognizes_adapter_parser_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "DOGI"
            make_fake_dogi_repo(repo)
            trace = Path(tmp) / "trace.dogi"
            trace.write_text("1 1 10 4096\n2 1 11 8192\n", encoding="utf-8")

            result = dogi_preflight.preflight(repo, trace)

            self.assertTrue(result["repo"]["parser_matches_adapter"])
            self.assertTrue(result["trace"]["all_lines_usable"])
            self.assertIn("cmake", result["tools"])


if __name__ == "__main__":
    unittest.main()
