#!/usr/bin/env python3
"""Run the QUASAR reproducibility pipeline.

The default pipeline regenerates the current non-destructive artifact set:
synthetic traces, liboqs traces, simulator results, plots, preflight reports,
file-backed ZNS replay, existing external DOGI run summaries, crash/recovery
cost model, FDP mapping model, C-level policy-overhead evidence, and final
acceptance report.

Use `--dry-run` to print the commands without executing them.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Step:
    name: str
    cmd: list[str]
    optional: bool = False


def py(*args: str) -> list[str]:
    return [sys.executable, *args]


def pipeline_steps(args: argparse.Namespace) -> list[Step]:
    events = str(args.events)
    workload_events = str(args.workload_events)
    return [
        Step(
            "generate-pqc-mixed",
            py(
                "code/tracegen/pqc_tracegen.py",
                "--events",
                events,
                "--jsonl",
                "artifacts/traces/pqc-mixed.jsonl",
                "--dogi-trace",
                "artifacts/traces/pqc-mixed.dogi",
                "--dogi-delete-markers",
            ),
        ),
        Step(
            "generate-schema-test",
            py(
                "code/tracegen/pqc_tracegen.py",
                "--events",
                str(args.schema_events),
                "--jsonl",
                "artifacts/traces/pqc-schema-test.jsonl",
                "--dogi-trace",
                "artifacts/traces/pqc-schema-test.dogi",
                "--dogi-delete-markers",
                "--seed",
                "11",
            ),
        ),
        Step(
            "liboqs-workload",
            py(
                "code/tracegen/liboqs_workload.py",
                "--sessions",
                str(args.liboqs_sessions),
                "--kem",
                "ML-KEM-768",
                "--sig",
                "ML-DSA-65",
                "--event-log",
                "artifacts/traces/liboqs-events.jsonl",
                "--jsonl",
                "artifacts/traces/liboqs-pqc.jsonl",
                "--dogi-trace",
                "artifacts/traces/liboqs-pqc.dogi",
                "--summary-out",
                "artifacts/results/liboqs-pqc-summary.json",
                "--epoch-len-ms",
                "1000",
                "--rotation-epochs",
                "12",
                "--seed",
                "17",
            ),
            optional=args.allow_missing_liboqs,
        ),
        Step(
            "verify-liboqs-trace",
            py(
                "code/sim/zns_pqc_verify.py",
                "--trace",
                "artifacts/traces/liboqs-pqc.jsonl",
                "--zones",
                "24",
                "--zone-capacity",
                "64",
                "--min-free-zones",
                "2",
                "--policies",
                "fifo",
                "sepbit-style",
                "dogi-history",
                "quasar",
                "epoch-oracle",
                "--out",
                "artifacts/results/liboqs-pqc-verification.json",
            ),
            optional=args.allow_missing_liboqs,
        ),
        Step(
            "oqs-openssl-sample",
            py(
                "code/tracegen/oqs_tls_trace.py",
                "--event-log",
                "code/tracegen/sample_oqs_events.jsonl",
                "--jsonl",
                "artifacts/traces/oqs-sample.jsonl",
                "--dogi-trace",
                "artifacts/traces/oqs-sample.dogi",
                "--dogi-delete-markers",
                "--summary-out",
                "artifacts/results/oqs-sample-summary.json",
                "--probe-out",
                "artifacts/results/openssl-pqc-capability.json",
                "--epoch-len-ms",
                "1000",
                "--rotation-epochs",
                "4",
            ),
        ),
        Step(
            "verify-oqs-sample",
            py(
                "code/sim/zns_pqc_verify.py",
                "--trace",
                "artifacts/traces/oqs-sample.jsonl",
                "--zones",
                "32",
                "--zone-capacity",
                "64",
                "--min-free-zones",
                "2",
                "--policies",
                "fifo",
                "sepbit-style",
                "dogi-history",
                "quasar",
                "epoch-oracle",
                "--out",
                "artifacts/results/oqs-sample-verification.json",
            ),
        ),
        Step(
            "dogi-adapter",
            py(
                "code/baselines/dogi_trace_adapter.py",
                "--jsonl",
                "artifacts/traces/pqc-mixed.jsonl",
                "--dogi-trace",
                "artifacts/traces/pqc-mixed-adapted.dogi",
                "--delete-markers",
                "--summary-out",
                "artifacts/results/pqc-mixed-dogi-adapter.json",
            ),
        ),
        Step(
            "dogi-fast26-pdf-extract",
            py(
                "code/baselines/dogi_pdf_extract.py",
                "--pdf",
                "Paper/Previous papers/fast26-kim-jeeyun.pdf",
                "--out",
                "artifacts/results/dogi-fast26-extraction.json",
                "--markdown-out",
                "artifacts/results/dogi-fast26-extraction.md",
            ),
        ),
        Step(
            "fetch-dogi-repo",
            py(
                "code/baselines/fetch_dogi.py",
                "--repo",
                "artifacts/external/DOGI",
                "--summary-out",
                "artifacts/results/dogi-fetch.json",
            ),
        ),
        Step(
            "dogi-preflight",
            py(
                "code/baselines/dogi_preflight.py",
                "--dogi-repo",
                "artifacts/external/DOGI",
                "--trace",
                "artifacts/traces/pqc-mixed-adapted.dogi",
                "--summary-out",
                "artifacts/results/dogi-preflight.json",
            ),
        ),
        Step(
            "dogi-nullblk-preflight",
            py(
                "code/baselines/dogi_preflight.py",
                "--dogi-repo",
                "artifacts/external/DOGI",
                "--trace",
                "artifacts/traces/pqc-mixed-adapted.dogi",
                "--device",
                "/dev/nullb_quasar",
                "--summary-out",
                "artifacts/results/dogi-preflight-nullblk.json",
            ),
        ),
        Step(
            "dogi-run-summary",
            py(
                "code/baselines/dogi_run_summary.py",
                "--log",
                "artifacts/results/dogi-nullblk-full-run.log",
                "--out",
                "artifacts/results/dogi-nullblk-full-run.json",
            ),
        ),
        Step(
            "replay-dry-run",
            py(
                "code/quasar/replay.py",
                "--trace",
                "artifacts/traces/pqc-mixed.jsonl",
                "--backend",
                "dry-run",
                "--plan-out",
                "artifacts/results/pqc-mixed-replay-plan.json",
                "--summary-out",
                "artifacts/results/pqc-mixed-replay-summary.json",
                "--min-epoch-fill-blocks",
                "1",
            ),
        ),
        Step(
            "replay-file-zns",
            py(
                "code/quasar/replay.py",
                "--trace",
                "artifacts/traces/pqc-mixed.jsonl",
                "--backend",
                "file-zns",
                "--execute",
                "--zone-capacity",
                "512",
                "--emulator-zones",
                "1400",
                "--emulator-state",
                "artifacts/results/pqc-mixed-file-zns-state.json",
                "--plan-out",
                "artifacts/results/pqc-mixed-file-zns-plan.json",
                "--summary-out",
                "artifacts/results/pqc-mixed-file-zns-summary.json",
                "--min-epoch-fill-blocks",
                "1",
            ),
        ),
        Step("zns-preflight", py("code/quasar/zns_preflight.py", "--out", "artifacts/results/zns-preflight.json")),
        Step(
            "nullblk-zoned-plan",
            py(
                "code/quasar/nullblk_zoned.py",
                "--action",
                "plan",
                "--name",
                "nullb_quasar",
                "--out",
                "artifacts/results/nullblk-zoned-plan.json",
            ),
        ),
        Step(
            "nullblk-zoned-preflight",
            py(
                "code/quasar/nullblk_zoned.py",
                "--action",
                "preflight",
                "--out",
                "artifacts/results/nullblk-zoned-preflight.json",
            ),
        ),
        Step(
            "crash-model",
            py(
                "code/quasar/crash_model.py",
                "--trace",
                "artifacts/traces/pqc-mixed.jsonl",
                "--out",
                "artifacts/results/pqc-mixed-crash-model.json",
                "--markdown-out",
                "artifacts/results/pqc-mixed-crash-model.md",
            ),
        ),
        Step(
            "verify-pqc-mixed",
            py(
                "code/sim/zns_pqc_verify.py",
                "--trace",
                "artifacts/traces/pqc-mixed.jsonl",
                "--zones",
                "1100",
                "--zone-capacity",
                "512",
                "--min-free-zones",
                "12",
                "--policies",
                "fifo",
                "sepbit-style",
                "dogi-history",
                "quasar",
                "epoch-oracle",
                "--out",
                "artifacts/results/pqc-mixed-verification.json",
            ),
        ),
        Step(
            "schema-runner",
            py(
                "code/sim/run_quasar_experiments.py",
                "--trace",
                "artifacts/traces/pqc-schema-test.jsonl",
                "--zones",
                "460",
                "--zone-capacity",
                "512",
                "--min-free-zones",
                "8",
                "--out-dir",
                "artifacts/results/schema-test-runner",
                "--min-epoch-fill-values",
                "0.0",
                "0.4",
                "--bin-width-values",
                "1",
                "4",
                "--hint-missing-values",
                "0.0",
                "0.05",
                "--wrong-epoch-values",
                "0.0",
                "0.05",
                "--straggler-values",
                "0.0",
                "0.05",
            ),
        ),
        Step(
            "generate-workload-suite",
            py(
                "code/tracegen/generate_workload_suite.py",
                "--events",
                workload_events,
                "--out-dir",
                "artifacts/traces/workloads",
                "--seed",
                "21",
            ),
        ),
        Step(
            "run-workload-suite",
            py(
                "code/sim/run_workload_suite.py",
                "--trace-dir",
                "artifacts/traces/workloads",
                "--auto-zones",
                "--auto-op-ratio",
                "0.02",
                "--zone-capacity",
                "512",
                "--min-free-zones",
                "8",
                "--out",
                "artifacts/results/e1-workloads.json",
            ),
        ),
        Step(
            "plot-results",
            py(
                "code/sim/plot_quasar_results.py",
                "--e0",
                "artifacts/results/schema-test-runner/e0-sanity.json",
                "--e1",
                "artifacts/results/e1-workloads.json",
                "--e2",
                "artifacts/results/schema-test-runner/e2-waf-vs-utilization.json",
                "--e5",
                "artifacts/results/schema-test-runner/e5-bad-hints.json",
                "--out-dir",
                "artifacts/figures",
            ),
        ),
        Step(
            "exposure-timeline",
            py(
                "code/sim/exposure_timeline.py",
                "--trace",
                "artifacts/traces/workloads/stress-rekey.jsonl",
                "--zones",
                "149",
                "--zone-capacity",
                "512",
                "--min-free-zones",
                "8",
                "--policies",
                "fifo",
                "dogi-history",
                "quasar",
                "--sample-interval",
                "500",
                "--out",
                "artifacts/results/e4-exposure-timeline.json",
                "--figure",
                "artifacts/figures/e4-exposure-timeline.png",
            ),
        ),
        Step(
            "c-policy-overhead",
            py(
                "code/sim/run_c_policy_overhead.py",
                "--skip-missing",
                "--repeats",
                "9",
                "--out",
                "artifacts/results/c-policy-overhead.json",
                "--markdown-out",
                "artifacts/results/c-policy-overhead.md",
            ),
        ),
        Step(
            "fdp-mapping",
            py(
                "code/quasar/fdp_mapping.py",
                "--trace",
                "artifacts/traces/pqc-mixed.jsonl",
                "--handles",
                "8",
                "16",
                "32",
                "64",
                "128",
                "--out",
                "artifacts/results/pqc-mixed-fdp-mapping.json",
                "--markdown-out",
                "artifacts/results/pqc-mixed-fdp-mapping.md",
            ),
        ),
        Step("acceptance", py("code/sim/acceptance_check.py", "--out", "artifacts/results/acceptance-report.json")),
        Step(
            "report-results",
            py(
                "code/sim/report_results.py",
                "--json-out",
                "artifacts/results/quasar-results-summary.json",
                "--markdown-out",
                "artifacts/results/quasar-results-summary.md",
            ),
        ),
    ]


def selected_steps(steps: list[Step], only: set[str]) -> list[Step]:
    if not only:
        return steps
    missing = only.difference(step.name for step in steps)
    if missing:
        raise SystemExit(f"unknown step(s): {', '.join(sorted(missing))}")
    return [step for step in steps if step.name in only]


def run_step(step: Step, *, dry_run: bool) -> dict:
    print(f"== {step.name} ==")
    print(" ".join(step.cmd))
    if dry_run:
        return {"name": step.name, "returncode": None, "dry_run": True, "optional": step.optional}
    proc = subprocess.run(step.cmd, check=False)
    if proc.returncode != 0 and not step.optional:
        raise SystemExit(proc.returncode)
    if proc.returncode != 0:
        print(f"optional step failed: {step.name} rc={proc.returncode}")
    return {"name": step.name, "returncode": proc.returncode, "dry_run": False, "optional": step.optional}


def write_manifest(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "steps": records,
        "passed": all(record["dry_run"] or record["returncode"] == 0 or record["optional"] for record in records),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote manifest={path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=80_000)
    parser.add_argument("--schema-events", type=int, default=30_000)
    parser.add_argument("--workload-events", type=int, default=15_000)
    parser.add_argument("--liboqs-sessions", type=int, default=200)
    parser.add_argument("--allow-missing-liboqs", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--manifest", type=Path, default=Path("artifacts/results/pipeline-manifest.json"))
    args = parser.parse_args()

    steps = selected_steps(pipeline_steps(args), set(args.only))
    records = [run_step(step, dry_run=args.dry_run) for step in steps]
    write_manifest(args.manifest, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
