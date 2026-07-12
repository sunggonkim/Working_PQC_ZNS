import tempfile
import unittest
from pathlib import Path

try:
    import capture_real_app_block_trace as capture
except ModuleNotFoundError:  # pragma: no cover
    from tracegen import capture_real_app_block_trace as capture


class CaptureRealAppBlockTraceTests(unittest.TestCase):
    def test_parse_blkparse_counts_actions_and_rwbs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blkparse.txt"
            path.write_text(
                "\n".join(
                    [
                        "  8,34   0        1     0.000001000  123  Q   W 0 + 8 [sysbench]",
                        "  8,34   0        2     0.000002000  123  G   W 0 + 8 [sysbench]",
                        "  8,34   0        3     0.000003000  456  Q   R 8 + 8 [python3]",
                        "  8,34   0        4     0.000004000  456  Q   WS 16 + 8 [python3]",
                        "not an event line",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            summary = capture.parse_blkparse(path)

        self.assertEqual(summary["event_lines"], 4)
        self.assertEqual(summary["action_counts"], {"Q": 3, "G": 1})
        self.assertEqual(summary["write_events"], 3)
        self.assertEqual(summary["read_events"], 1)
        self.assertEqual(summary["rwbs_counts"]["WS"], 1)

    def test_markdown_contains_claim_boundary(self) -> None:
        md = capture.markdown(
            {
                "device": "/dev/sdc2",
                "mount": {"source": "/dev/sdc2", "target": "/", "fstype": "ext4"},
                "sysbench_mode": "rndrw",
                "sysbench": {"elapsed_s": 1.25},
                "pqc_side_writer": {"sessions_completed": 4, "records": 12},
                "blktrace": {"event_lines": 100, "write_events": 70, "read_events": 30},
            }
        )

        self.assertIn("Real Application Block Trace", md)
        self.assertIn("PQC sessions completed", md)
        self.assertIn("does not close SPDK/ZenFS", md)


if __name__ == "__main__":
    unittest.main()
