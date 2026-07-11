import tempfile
import unittest
from pathlib import Path

try:
    import sepbit_run_summary
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from baselines import sepbit_run_summary


class SepbitRunSummaryTests(unittest.TestCase):
    def test_parse_completed_sepbit_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "sepbit.log"
            log.write_text(
                "\n".join(
                    [
                        "SUMMARY: ",
                        "    Requests   : 132615",
                        "    nGC     : 1835",
                        "  LBAs         : 471620",
                        "  bytes_to_System: 1931755520",
                        "  bytes_to_Storage: 4693204992",
                        "  ** WA **     : 2.429503",
                        "  nBlocks:     : 206282",
                        "  nInvalidBlks : 30853",
                        "  garb prop    : 0.149567097468514",
                        " removed avg gp: 0.282418681880109",
                        "",
                        "  Run time(s)  : 5.348",
                        "  pqc: nBlocks: 206282, nInvalidBlocks: 30853 , garbage prop = 0.150  , segment WA = 2.429503",
                    ]
                ),
                encoding="utf-8",
            )

            result = sepbit_run_summary.parse_sepbit_log(
                log,
                returncode=0,
                method="SepBIT",
                selection="Greedy",
                adapter_summary={"writes": 80000},
            )

            self.assertTrue(result["completed"])
            self.assertEqual(result["summary"]["requests"], 132615)
            self.assertEqual(result["summary"]["ngc"], 1835)
            self.assertEqual(result["summary"]["wa"], 2.429503)
            self.assertEqual(result["segment_summary"]["segment_wa"], 2.429503)
            self.assertEqual(result["method"], "SepBIT")


if __name__ == "__main__":
    unittest.main()
