import tempfile
import unittest
from pathlib import Path

try:
    import run_c_policy_overhead as runner
except ModuleNotFoundError:  # pragma: no cover
    from sim import run_c_policy_overhead as runner


class CPolicyOverheadRunnerTests(unittest.TestCase):
    def test_compile_and_run_small_trace(self) -> None:
        source = Path(__file__).with_name("c_policy_overhead.c")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            trace = tmp_path / "tiny.jsonl"
            trace.write_text(
                "\n".join(
                    [
                        '{"op":"write","ts":0,"object_id":1,"lba":10,"epoch_id":1,"intent":"KEM_ARTIFACT","security_class":"SECRET","size_blocks":1}',
                        '{"op":"write","ts":1,"object_id":2,"lba":11,"epoch_id":1,"intent":"PAYLOAD","security_class":"PAYLOAD","size_blocks":1}',
                        '{"op":"expire","ts":2,"object_id":1,"epoch_id":1,"intent":"KEM_ARTIFACT","security_class":"SECRET"}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            binary = tmp_path / "c_policy_overhead"

            runner.compile_benchmark(source, binary)
            result = runner.run_benchmark(binary, trace, repeats=1)
            rows = result["rows"]
            aggregate = runner.summarize(rows)

        self.assertEqual(result["events"], 3)
        self.assertEqual(result["writes"], 2)
        self.assertEqual({row["policy"] for row in rows}, {"dogi-mlp", "quasar-hint", "quasar-dogi-hybrid"})
        self.assertGreater(aggregate["dogi-mlp"]["median_ns_per_write"], 0)
        self.assertGreater(aggregate["quasar-hint"]["median_ns_per_write"], 0)


if __name__ == "__main__":
    unittest.main()
