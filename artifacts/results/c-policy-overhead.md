# C Policy Decision Overhead

This benchmark compiles `code/sim/c_policy_overhead.c` and measures only the placement-decision path.
DOGI-style cost is modeled as storage-visible feature extraction plus a small MLP inference.
QUASAR cost is modeled as hint decoding already present in the trace plus zone-family lookup.

It is stronger than the Python microbenchmark, but it is still not a full DOGI production CPU profile.

## Aggregate

| Policy | Traces | Median ns/write | Min ns/write | Max ns/write |
| --- | ---: | ---: | ---: | ---: |
| `dogi-mlp` | 3 | 2397.8 | 350.4 | 6417.9 |
| `quasar-dogi-hybrid` | 3 | 1178.8 | 307.4 | 1908.1 |
| `quasar-hint` | 3 | 16.8 | 15.7 | 22.9 |

## Per Trace

| Trace | Policy | Events | Writes | Expires | Median ns/event | Median ns/write |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `kms-rotation.jsonl` | `dogi-mlp` | 2,100 | 1,200 | 900 | 1370.2 | 2397.8 |
| `kms-rotation.jsonl` | `quasar-hint` | 2,100 | 1,200 | 900 | 9.6 | 16.8 |
| `kms-rotation.jsonl` | `quasar-dogi-hybrid` | 2,100 | 1,200 | 900 | 673.6 | 1178.8 |
| `exchange-pqc2000.jsonl` | `dogi-mlp` | 255,240 | 149,887 | 105,353 | 205.8 | 350.4 |
| `exchange-pqc2000.jsonl` | `quasar-hint` | 255,240 | 149,887 | 105,353 | 13.4 | 22.9 |
| `exchange-pqc2000.jsonl` | `quasar-dogi-hybrid` | 255,240 | 149,887 | 105,353 | 180.5 | 307.4 |
| `trace.jsonl` | `dogi-mlp` | 300 | 180 | 120 | 3850.7 | 6417.9 |
| `trace.jsonl` | `quasar-hint` | 300 | 180 | 120 | 9.4 | 15.7 |
| `trace.jsonl` | `quasar-dogi-hybrid` | 300 | 180 | 120 | 1144.9 | 1908.1 |

Interpretation:

- Use this as C-level evidence that QUASAR hint routing is cheap relative to a learned placement decision path.
- The benchmark deliberately separates CPU decision cost from GC savings and device latency.
- A final paper should still add `perf stat` or equivalent counters on the exact DOGI binary if a physical/replay setup is available.
