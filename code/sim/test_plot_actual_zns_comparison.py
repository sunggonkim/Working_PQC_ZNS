import json
import tempfile
import unittest
from pathlib import Path

try:
    import plot_actual_zns_comparison as plots
except ModuleNotFoundError:  # pragma: no cover
    from sim import plot_actual_zns_comparison as plots


class PlotActualZnsComparisonTests(unittest.TestCase):
    def test_plotters_create_pngs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            curve = {
                "rows": [
                    {
                        "workloads": ["ycsb-a-pqc2000"],
                        "dogi_waf": 1.0,
                        "hybrid_waf": 1.0,
                        "dogi_stale_secret_blocks": 10,
                        "hybrid_stale_secret_blocks": 0,
                    },
                    {
                        "workloads": ["ycsb-a-pqc8000"],
                        "dogi_waf": 1.05,
                        "hybrid_waf": 1.0,
                        "dogi_stale_secret_blocks": 20,
                        "hybrid_stale_secret_blocks": 0,
                    },
                ]
            }
            overhead = {
                "by_policy": {
                    "dogi-history": {
                        "throughput_mib_s": 200.0,
                        "semantic_physical_reset_commands": 0,
                        "cpu_policy": {"median_ns_per_write": 2000.0},
                    },
                    "quasar": {
                        "throughput_mib_s": 180.0,
                        "semantic_physical_reset_commands": 10,
                        "cpu_policy": {"median_ns_per_write": 20.0},
                    },
                    "quasar-dogi-hybrid": {
                        "throughput_mib_s": 175.0,
                        "semantic_physical_reset_commands": 10,
                        "cpu_policy": {"median_ns_per_write": 1000.0},
                    },
                }
            }
            hardness = {
                "entries": [
                    {"name": "Fairness", "tier": "fairness", "passed": True},
                    {"name": "Pressure", "tier": "pressure", "passed": True},
                    {"name": "Hostile", "tier": "hostile-robustness", "passed": True},
                ]
            }
            space = [
                {
                    "policy": "dogi-history",
                    "waf": 1.01,
                    "closed_zone_fill_avg": 0.98,
                    "stale_secret_blocks_remaining": 100,
                },
                {
                    "policy": "quasar-dogi-hybrid",
                    "waf": 1.001,
                    "closed_zone_fill_avg": 0.95,
                    "quasar_open_zone_budget": 2,
                    "stale_secret_blocks_remaining": 0,
                },
            ]

            plots.plot_ycsb_pressure(curve, root / "ycsb.png")
            plots.plot_overhead(overhead, root / "overhead.png")
            plots.plot_workload_hardness(hardness, root / "hardness.png")
            plots.plot_space_sensitivity(space, root / "space.png")

            for name in ["ycsb.png", "overhead.png", "hardness.png", "space.png"]:
                self.assertGreater((root / name).stat().st_size, 0)

    def test_load_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            path.write_text(json.dumps({"ok": True}), encoding="utf-8")
            self.assertTrue(plots.load_json(path)["ok"])


if __name__ == "__main__":
    unittest.main()
