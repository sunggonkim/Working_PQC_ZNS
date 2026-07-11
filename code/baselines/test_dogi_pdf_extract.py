import unittest

try:
    import dogi_pdf_extract
except ModuleNotFoundError:  # pragma: no cover
    from baselines import dogi_pdf_extract


class DogiPdfExtractTests(unittest.TestCase):
    def test_excerpt_normalizes_text(self) -> None:
        text = "alpha\n\nEvaluation Platform.  Western Digital ZN540 2TB SSD\nomega"

        out = dogi_pdf_extract.excerpt(text, "Evaluation Platform")

        self.assertIn("Evaluation Platform", out)
        self.assertNotIn("\n\n", out)


if __name__ == "__main__":
    unittest.main()
