# Actual-ZNS Overhead Summary

- Scope: actual ZNS replay overhead plus C-level policy-decision overhead
- Artifacts: `7`
- Rows: `84`, failed rows: `0`
- Caveat: Actual-ZNS latency is measured through zonefs helper appends/truncates and includes user-space helper overhead. C-level CPU numbers isolate only placement-decision cost.

| Policy | Rows | Append Commands | Semantic Resets | Total Resets incl. cleanup | Physical MiB | Throughput MiB/s | Append Avg ms | Worst Append p99 ms | Reset Avg ms | Worst Reset p99 ms | Max Live Zones | CPU Median ns/write |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `fifo` | 14 | 518 | 0 | 929 | 16109.8 | 235.26 | 130.988 | 164.101 | 1.587 | 17.643 | 3 | N/A |
| `sepbit-style` | 14 | 557 | 0 | 984 | 15814.7 | 209.77 | 118.434 | 157.743 | 1.843 | 15.498 | 7 | N/A |
| `midas-style` | 14 | 542 | 0 | 969 | 15758.7 | 199.03 | 121.814 | 161.601 | 1.724 | 19.536 | 6 | N/A |
| `dogi-history` | 14 | 560 | 0 | 988 | 15906.5 | 208.10 | 118.839 | 161.605 | 1.826 | 15.608 | 8 | 2397.8 |
| `quasar` | 14 | 744 | 318 | 1,232 | 15687.6 | 186.01 | 89.539 | 162.671 | 2.975 | 22.550 | 6 | 16.8 |
| `quasar-dogi-hybrid` | 14 | 743 | 318 | 1,232 | 15655.6 | 177.25 | 88.841 | 163.609 | 2.974 | 22.883 | 6 | 1178.8 |

Hybrid vs DOGI-history:

- Append average latency ratio: `0.748`
- Throughput ratio: `0.852`
- Semantic reset command delta: `318`
- C-level policy-decision median ratio: `0.492`

Reading:

- QUASAR-DOGI hybrid pays extra semantic reset work because it actually makes secret cohorts reset-eligible.
- The helper-based actual-ZNS path is useful for relative append/reset feasibility, but not a final low-overhead latency number.
- The C-level policy benchmark isolates the allocator decision cost: DOGI-style MLP is much more expensive than QUASAR hint routing, while the hybrid sits between them because it preserves DOGI-style payload handling.
