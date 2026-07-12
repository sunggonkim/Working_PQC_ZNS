import tempfile
import unittest
from pathlib import Path

try:
    import plot_fast_style_quasar_figures as plots
except ModuleNotFoundError:  # pragma: no cover
    from sim import plot_fast_style_quasar_figures as plots


class FastStyleFigureTests(unittest.TestCase):
    def test_fdp_handle_pressure_plot_is_created(self) -> None:
        payload = {
            "runs": [
                {
                    "handles": 8,
                    "family_purity": 0.88,
                    "intent_purity": 0.93,
                    "avg_families_per_occupied_handle": 10.0,
                },
                {
                    "handles": 16,
                    "family_purity": 0.90,
                    "intent_purity": 0.94,
                    "avg_families_per_occupied_handle": 5.0,
                },
                {
                    "handles": 64,
                    "family_purity": 0.96,
                    "intent_purity": 0.98,
                    "avg_families_per_occupied_handle": 1.7,
                },
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "fdp.pdf"
            plots.plot_fdp_handle_pressure(payload, out)
            self.assertGreater(out.stat().st_size, 0)
            self.assertGreater(out.with_suffix(".png").stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
