# Actual-ZNS YCSB Pressure Curve

p2000 is an easy WAF point but still exposes semantic reset failure; p4000/p6000/p8000/p10000 add GC pressure while preserving the stale-secret gap. The larger p10000 YCSB rows show the realistic DOGI-axis failure mode: moderate GC/WAF pressure plus large stale-secret exposure, not universal WAF explosion.

| Workloads | PQC Level | Logical Zones | Rows | Failed | DOGI WAF | Hybrid WAF | WAF Reduction | DOGI GC | Hybrid GC | DOGI Stale | Hybrid Stale | DOGI Resets | Hybrid Resets | DOGI Waiting | Hybrid Waiting |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ycsb-a-pqc2000`, `ycsb-f-pqc2000` | 2,000 | 512 | 12 | 0 | 1.0000 | 1.0000 | 0.0% | 0 | 0 | 35,472 | 0 | 0 | 28 | 0 | 0 |
| `ycsb-a-pqc4000` | 4,000 | 560 | 6 | 0 | 1.0454 | 1.0000 | 4.3% | 15,316 | 0 | 46,266 | 0 | 0 | 28 | 16,944 | 0 |
| `ycsb-f-pqc4000` | 4,000 | 733 | 6 | 0 | 1.0000 | 1.0000 | 0.0% | 0 | 0 | 74,274 | 0 | 0 | 28 | 0 | 0 |
| `ycsb-a-pqc6000` | 6,000 | 712 | 6 | 0 | 1.0376 | 1.0000 | 3.6% | 15,308 | 0 | 76,950 | 0 | 0 | 28 | 22,291 | 0 |
| `ycsb-f-pqc6000` | 6,000 | 733 | 6 | 0 | 1.0105 | 1.0000 | 1.0% | 4,166 | 0 | 96,050 | 0 | 0 | 28 | 14,935 | 0 |
| `ycsb-a-pqc8000` | 8,000 | 863 | 6 | 0 | 1.0282 | 1.0000 | 2.7% | 13,462 | 0 | 110,018 | 0 | 0 | 28 | 26,251 | 0 |
| `ycsb-f-pqc8000` | 8,000 | 733 | 6 | 0 | 1.0528 | 1.0000 | 5.0% | 24,289 | 0 | 100,847 | 0 | 0 | 28 | 52,036 | 0 |
| `ycsb-a-pqc10000` | 10,000 | 1,024 | 6 | 0 | 1.0066 | 1.0000 | 0.7% | 3,357 | 0 | 150,221 | 0 | 0 | 26 | 9,490 | 0 |
| `ycsb-f-pqc10000` | 10,000 | 900 | 6 | 0 | 1.0279 | 1.0000 | 2.7% | 13,741 | 0 | 144,901 | 0 | 0 | 26 | 33,094 | 0 |

## Baseline Semantic Failure Check

| Workloads | FIFO Stale/Reset | SepBIT Stale/Reset | MiDAS Stale/Reset | DOGI Stale/Reset | Semantic Gap | WAF Pressure |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `ycsb-a-pqc2000`, `ycsb-f-pqc2000` | 35,472/0 | 35,472/0 | 35,472/0 | 35,472/0 | yes | no |
| `ycsb-a-pqc4000` | 40,488/0 | 65,571/0 | 63,159/0 | 46,266/0 | yes | yes |
| `ycsb-f-pqc4000` | 73,732/0 | 74,274/0 | 74,274/0 | 74,274/0 | yes | no |
| `ycsb-a-pqc6000` | 70,210/0 | 100,770/0 | 98,395/0 | 76,950/0 | yes | yes |
| `ycsb-f-pqc6000` | 87,275/0 | 104,079/0 | 110,745/0 | 96,050/0 | yes | yes |
| `ycsb-a-pqc8000` | 102,724/0 | 135,454/0 | 134,789/0 | 110,018/0 | yes | yes |
| `ycsb-f-pqc8000` | 92,959/0 | 114,520/0 | 128,224/0 | 100,847/0 | yes | yes |
| `ycsb-a-pqc10000` | 141,424/0 | 158,845/0 | 158,884/0 | 150,221/0 | yes | yes |
| `ycsb-f-pqc10000` | 133,533/0 | 159,007/0 | 172,228/0 | 144,901/0 | yes | yes |

## Reading

- `pqc2000` is deliberately included as a negative WAF control: DOGI-style WAF is already 1.0, so the correct claim is stale-secret exposure, not WAF reduction.
- `pqc4000`, `pqc6000`, `pqc8000`, and `pqc10000` show when the same YCSB family starts producing GC/WAF separation.
- The `pqc10000` rows are larger DOGI-axis checks: they strengthen the workload-hardness story while keeping the claim realistic.
- Across the curve, FIFO/SepBIT/MiDAS/DOGI issue zero semantic resets for expired PQC secret cohorts, while QUASAR-DOGI hybrid drains stale secrets to zero.
