#!/usr/bin/env python3
"""Compile and run the C-level policy overhead benchmark."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from pathlib import Path


DEFAULT_TRACES = [
    Path("artifacts/traces/liboqs-profiles/traces/kms-rotation.jsonl"),
    Path("artifacts/traces/dogi-paper-ratio-sweep-50k/exchange-pqc2000.jsonl"),
    Path("artifacts/traces/openssl-oqsprovider-tls-socket/trace.jsonl"),
]


def compile_benchmark(source: Path, binary: Path) -> None:
    binary.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "gcc",
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-o",
        str(binary),
        str(source),
    ]
    subprocess.run(cmd, check=True)


def run_benchmark(binary: Path, trace: Path, repeats: int) -> dict:
    completed = subprocess.run(
        [str(binary), "--trace", str(trace), "--repeats", str(repeats)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    data = json.loads(completed.stdout)
    for row in data["rows"]:
        row["trace"] = str(trace)
        row["trace_name"] = trace.name
        row["events"] = data["events"]
        row["writes"] = data["writes"]
        row["expires"] = data["expires"]
        row["repeats"] = data["repeats"]
    return data


def summarize(rows: list[dict]) -> dict:
    by_policy: dict[str, list[float]] = {}
    for row in rows:
        by_policy.setdefault(row["policy"], []).append(float(row["ns_per_write_median"]))
    return {
        policy: {
            "traces": len(values),
            "median_ns_per_write": statistics.median(values),
            "min_ns_per_write": min(values),
            "max_ns_per_write": max(values),
        }
        for policy, values in sorted(by_policy.items())
    }


def write_markdown(path: Path, rows: list[dict], aggregate: dict) -> None:
    lines = [
        "# C Policy Decision Overhead",
        "",
        "This benchmark compiles `code/sim/c_policy_overhead.c` and measures only the placement-decision path.",
        "DOGI-style cost is modeled as storage-visible feature extraction plus a small MLP inference.",
        "QUASAR cost is modeled as hint decoding already present in the trace plus zone-family lookup.",
        "",
        "It is stronger than the Python microbenchmark, but it is still not a full DOGI production CPU profile.",
        "",
        "## Aggregate",
        "",
        "| Policy | Traces | Median ns/write | Min ns/write | Max ns/write |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for policy, item in aggregate.items():
        lines.append(
            "| `{policy}` | {traces} | {median:.1f} | {minv:.1f} | {maxv:.1f} |".format(
                policy=policy,
                traces=item["traces"],
                median=item["median_ns_per_write"],
                minv=item["min_ns_per_write"],
                maxv=item["max_ns_per_write"],
            )
        )

    lines.extend(
        [
            "",
            "## Per Trace",
            "",
            "| Trace | Policy | Events | Writes | Expires | Median ns/event | Median ns/write |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in rows:
        lines.append(
            "| `{trace}` | `{policy}` | {events:,} | {writes:,} | {expires:,} | {ns_event:.1f} | {ns_write:.1f} |".format(
                trace=row["trace_name"],
                policy=row["policy"],
                events=int(row["events"]),
                writes=int(row["writes"]),
                expires=int(row["expires"]),
                ns_event=float(row["ns_per_event_median"]),
                ns_write=float(row["ns_per_write_median"]),
            )
        )

    lines.extend(
        [
            "",
            "Interpretation:",
            "",
            "- Use this as C-level evidence that QUASAR hint routing is cheap relative to a learned placement decision path.",
            "- The benchmark deliberately separates CPU decision cost from GC savings and device latency.",
            "- A final paper should still add `perf stat` or equivalent counters on the exact DOGI binary if a physical/replay setup is available.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("code/sim/c_policy_overhead.c"))
    parser.add_argument("--binary", type=Path, default=Path("artifacts/bin/c_policy_overhead"))
    parser.add_argument("--traces", nargs="+", type=Path, default=DEFAULT_TRACES)
    parser.add_argument("--repeats", type=int, default=9)
    parser.add_argument("--skip-missing", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/c-policy-overhead.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/c-policy-overhead.md"))
    args = parser.parse_args()

    compile_benchmark(args.source, args.binary)

    runs = []
    rows = []
    for trace in args.traces:
        if not trace.exists():
            if args.skip_missing:
                continue
            raise FileNotFoundError(trace)
        run = run_benchmark(args.binary, trace, args.repeats)
        runs.append(run)
        rows.extend(run["rows"])

    aggregate = summarize(rows)
    result = {
        "source": str(args.source),
        "binary": str(args.binary),
        "runs": runs,
        "rows": rows,
        "aggregate": aggregate,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(args.markdown_out, rows, aggregate)
    print(f"wrote {args.out}")
    print(f"wrote {args.markdown_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
