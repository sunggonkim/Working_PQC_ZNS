import tempfile
import unittest
from pathlib import Path

try:
    import midas_run_summary
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from baselines import midas_run_summary


class MidasRunSummaryTests(unittest.TestCase):
    def test_parse_completed_midas_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "midas.log"
            log.write_text(
                "\n".join(
                    [
                        "Storage Capacity: 1GiB  (LBA NUMBER: 262144)",
                        "[progress: 1GB]",
                        "TOTAL WAF:\t1.003, TMP WAF:\t1.003",
                        "runtime: 2 sec ",
                        "Total Read Traffic : 48853",
                        "Total Write Traffic: 147212",
                        "",
                        "Total WAF: 1.25",
                        "",
                        "TRIM 645",
                        "DATAR 0",
                        "DATAW 117904",
                        "GCDR 48853",
                        "GCDW 29308",
                    ]
                ),
                encoding="utf-8",
            )

            result = midas_run_summary.parse_midas_log(
                log,
                trace=Path("trace.dogi"),
                returncode=0,
                build_gigaunit="1L",
                pps=128,
                adapter_summary={"logical_size_gb": 1},
            )

            self.assertTrue(result["completed"])
            self.assertEqual(result["storage_capacity_gib"], 1)
            self.assertEqual(result["lba_number"], 262144)
            self.assertEqual(result["total_waf"], 1.25)
            self.assertAlmostEqual(result["recomputed_waf_from_dataw_gcdw"], (117904 + 29308) / 117904)
            self.assertEqual(result["counters"]["gcdw"], 29308)
            self.assertEqual(result["build"]["gigaunit"], "1L")


if __name__ == "__main__":
    unittest.main()
