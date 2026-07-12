# Unified Baseline vs QUASAR Comparison

This report separates evidence by compatibility of units and stack.

## Main Conclusion

- The deployable policy should be **QUASAR-DOGI hybrid with secret-group packing**: DOGI-style placement remains useful for normal payload locality, while QUASAR handles PQC secret death cohorts.
- The six DOGI-paper workload-axis replay is the fairness matrix. It mainly proves stale-secret exposure and semantic reset behavior because WAF is often already near 1.0.
- The FAST-style Sysbench-OLTP pressure replay is the stress figure. It shows WAF/GC separation when update-heavy DB traffic and PQC metadata create real pressure.
- The FAST/YCSB pressure replay confirms the workload concern: p2000 YCSB can be too easy, while p4000 through p10000 YCSB-A/F exposes WAF/GC separation.
- The actual-ZNS YCSB pressure curve now includes p2000 as a negative WAF control and p4000/p6000/p8000/p10000 as pressure points.
- Adaptive QUASAR binning was tested but did not beat the current hybrid in the single-tenant pressure suite, so the default remains QUASAR-DOGI hybrid.
- Multi-tenant pressure adds a second mode: tuned adaptive hybrid can eliminate reset-time secret tenant mixing at measurable reset/open-zone cost.
- Physical hint robustness shows a real improvement boundary: clean/missing/wrong hints execute, stragglers can exceed the ZNS open-zone budget, and residual epoch-bin fallback restores zero final secret waiting at explicit GC-copy cost.
- Residual fallback sweep generalizes this boundary: Exchange and Sysbench representatives are practical, while YCSB-F p8000 shows strict zero-wait mode can be too expensive.
- The residual controller converts that sweep into deployable choices: low-overhead, balanced, and strict-zero-wait profiles choose different residual copy budgets from the measured frontier.
- The YCSB-F straggler baseline replay runs FIFO/SepBIT/MiDAS/DOGI on the same actual-ZNS hard condition and confirms they issue no semantic resets.
- Actual-ZNS overhead is now reported separately: hybrid pays semantic reset work, while C-level policy-decision cost remains below DOGI-style MLP inference.
- A real sysbench fileio block trace with concurrent liboqs PQC KMS/audit side writes closes the application-trace realism gap without claiming SPDK/ZenFS latency.
- Per-cohort key isolation closes the erase-scope/blast-radius gap for crypto-erase deployments without treating shared-namespace sanitize as an epoch cleanup primitive.
- Security semantics are bounded explicitly: current evidence proves reset eligibility and cohort-scoped crypto-erase feasibility, not that zone reset physically erases NAND.
- Claim matrix is generated as a writing guardrail: supported, qualified, and boundary claims are separated from forbidden overclaims.
- Workload hardness matrix is generated as a benchmark guardrail: negative controls, pressure workloads, headline claim eligibility, and QUASAR-hostile workloads are separated.
- Deployment policy selector is generated as an implementation guardrail: default hybrid, tenant isolation, residual migration, and overflow fallback are explicit modes.
- Reproducibility manifest records the actual-ZNS artifacts, hashes, paper claims, and regeneration commands.
- Reproducibility validation checks that current artifact files still match the manifest hashes.
- Exact DOGI/MiDAS/SepBIT artifacts are included, but their units are not directly interchangeable with QUASAR's native packed ZNS replay.

## Reproducibility Manifest

- Scope: reproducibility manifest for actual-ZNS baseline-vs-QUASAR comparison
- Passed: `True`
- Artifacts: `46`
- Commands: `14`
- Missing or empty: `[]`
- Hash validation passed: `True`
- Hash mismatches: `0`

## Deployment Policy Selector

- Scope: QUASAR deployment policy selector derived from actual-ZNS and simulator pressure artifacts
- Passed modes: `4/4`
- Default policy: `quasar-dogi-hybrid`
- Takeaway: The improved deployable design is not a single universal knob. The default remains QUASAR-DOGI hybrid; tenant isolation and residual migration are explicit modes enabled only when the workload/security objective requires their overhead.

| Mode | Policy | Pass | When |
| --- | --- | --- | --- |
| `default` | `quasar-dogi-hybrid` | `yes` | single-tenant or normal PQC pressure without tenant isolation requirement |
| `tenant-isolation` | `quasar-adaptive-hybrid tenant-local bins` | `yes` | multi-tenant secret reset must not mix tenant cohorts |
| `strict-residual` | `epoch-bin residual-migration controller` | `yes` | delayed expiry or stragglers would otherwise leave secret bytes waiting |
| `fallback-overflow` | `overflow and conservative reset confirmation` | `yes` | hint confidence is low, missing, or inconsistent |

## Workload Hardness Matrix

- Scope: DOGI/FAST-compatible workload hardness matrix for QUASAR evaluation
- Passed: `9/9`
- By tier: `{'claim-gate': {'passed': 1, 'total': 1}, 'fairness': {'passed': 1, 'total': 1}, 'hostile-robustness': {'passed': 3, 'total': 3}, 'negative-control': {'passed': 2, 'total': 2}, 'pressure': {'passed': 2, 'total': 2}}`
- Takeaway: The suite now contains a DOGI-favorable non-PQC control, a negative WAF control, DOGI-compatible pressure rows, FAST-style DB pressure, dynamic service pressure, an explicit main-claim eligibility gate, and QUASAR-hostile robustness cases. This prevents the paper from relying on an overly easy PQC-only workload.

| Entry | Tier | Pass | Purpose |
| --- | --- | --- | --- |
| DOGI six-axis fairness matrix | `fairness` | `yes` | Match DOGI/FAST workload axes without pretending every row is a WAF stress test. |
| DOGI-favorable non-PQC control | `negative-control` | `yes` | Prove that the evaluation does not cripple DOGI: when no PQC death-cohort signal exists, DOGI-style history placement is the right tool. |
| YCSB p2000 negative WAF control | `negative-control` | `yes` | Prove that easy DOGI-axis workloads are not WAF stress tests. |
| YCSB p4000/p6000/p8000/p10000 DOGI-compatible pressure | `pressure` | `yes` | Use DOGI/FAST YCSB axes with enough PQC density and zone pressure to create GC. |
| Sysbench-OLTP FAST-style DB pressure | `pressure` | `yes` | Show that the result is not only a synthetic YCSB artifact. |
| Main WAF/GC claim eligibility gate | `claim-gate` | `yes` | Prevent easy negative-control workloads from being used as the headline WAF figure. |
| Multi-tenant PQC pressure | `hostile-robustness` | `yes` | Attack QUASAR's open-zone/family count assumptions with many tenants. |
| Bad-hint and straggler robustness | `hostile-robustness` | `yes` | Show that QUASAR has boundaries and needs fallback under imperfect lifetimes. |
| Residual fallback frontier | `hostile-robustness` | `yes` | Measure when strict zero-wait exposure is affordable and when it is too expensive. |

### Headline WAF/GC Claim Gate

- Pass: `yes`
- Rule: >=3 YCSB pressure rows with all history baselines, DB pressure eligible, >=2 dynamic pressure rows with all policies
- YCSB eligible pressure rows: `7`
- YCSB baseline-complete rows: `9`
- Dynamic eligible rows: `3`
- Dynamic baseline-complete rows: `3`
- DB pressure eligible: `True`
- Required history baselines: `['dogi-history', 'fifo', 'midas-style', 'sepbit-style']`
- Required dynamic policies: `['dogi-history', 'fifo', 'midas-style', 'quasar', 'quasar-dogi-hybrid', 'sepbit-style']`

Only rows satisfying this gate should be used for the headline WAF/GC claim. Easy p2000 rows remain negative-control or semantic-exposure evidence.

## Same-Path Physical ZNS Fairness Matrix

- Scope: same physical ZNS packed replay over six DOGI-paper workload axes at pqc2000
- Rows: `72`, failed rows: `0`
- Wall time: `472.460` s
- Physical zone capacity: `275712` 4KiB blocks
- Append engine: `helper`, helper chunk blocks: `1`

| Policy | WAF | GC Blocks | Stale Secrets | Semantic Physical Resets | Secret Waiting End | Avg Util | Max Live Phys Zones |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| FIFO | 1.0040 | 3,903 | 99,141 | 0 | 0 | 0.363 | 3 |
| SepBIT-style | 1.0023 | 2,241 | 99,822 | 0 | 85 | 0.131 | 6 |
| MiDAS-style | 1.0006 | 581 | 99,898 | 0 | 0 | 0.156 | 5 |
| DOGI-style | 1.0006 | 625 | 99,834 | 0 | 56 | 0.130 | 6 |
| QUASAR | 1.0011 | 1,121 | 0 | 98 | 0 | 0.722 | 5 |
| QUASAR-DOGI hybrid | 1.0001 | 106 | 0 | 98 | 0 | 0.722 | 5 |

Hybrid vs DOGI-style on this fairness matrix:

- WAF reduction: `0.1%`
- GC reduction: `83.0%`
- Stale secret blocks removed: `99,834`

## FAST-Style DB Pressure Stress

- Scope: FAST-style Sysbench-OLTP pressure stress, not a DOGI paper workload
- Rows: `24`, failed rows: `0`
- Wall time: `204.726` s
- Total physical writes: `24.31` GiB

| Policy / Packing | WAF | GC Blocks | Stale Secrets | Semantic Physical Resets | Secret Waiting End | Avg Util | Max Live Phys Zones |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `fifo::secret-group` | 1.0720 | 26,938 | 38,736 | 0 | 20,480 | 0.494 | 2 |
| `sepbit-style::secret-group` | 1.0498 | 18,651 | 41,002 | 0 | 19,353 | 0.162 | 6 |
| `midas-style::secret-group` | 1.0346 | 12,949 | 42,815 | 0 | 16,087 | 0.193 | 5 |
| `dogi-history::secret-group` | 1.0301 | 11,256 | 38,438 | 0 | 20,388 | 0.160 | 6 |
| `quasar::secret-group` | 1.0175 | 6,567 | 0 | 80 | 0 | 0.846 | 5 |
| `quasar-dogi-hybrid::secret-group` | 1.0016 | 609 | 0 | 80 | 0 | 0.836 | 5 |

Hybrid vs DOGI-style on DB pressure:

- WAF reduction: `2.8%`
- GC reduction: `94.6%`
- Stale secret blocks removed: `38,438`

## FAST/YCSB Pressure Stress

- Scope: FAST/YCSB-A/F pressure stress with higher PQC ratios and tight free-zone margins
- Boundary: synthetic PQC metadata overlays on DOGI-style YCSB axes, not private original DOGI traces.

| Workload | Zones | DOGI WAF | Hybrid WAF | WAF Reduction | DOGI GC Blocks | Hybrid GC Blocks | GC Reduction | DOGI Stale Secrets | Hybrid Stale Secrets |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ycsb-a-pqc4000` | 560 | 1.0454 | 1.0000 | 4.3% | 15,316 | 0 | 100.0% | 46,266 | 0 |
| `ycsb-a-pqc8000` | 863 | 1.0282 | 1.0000 | 2.7% | 13,462 | 0 | 100.0% | 110,018 | 0 |
| `ycsb-f-pqc4000` | 733 | 1.0000 | 1.0000 | 0.0% | 0 | 0 | N/A | 74,274 | 0 |
| `ycsb-f-pqc8000` | 733 | 1.0528 | 1.0000 | 5.0% | 24,289 | 0 | 100.0% | 100,847 | 0 |

Representative physical YCSB replays:

| Workload | Rows | Failed | Logical Zones | Wall Time | DOGI WAF | Hybrid WAF | DOGI GC Blocks | Hybrid GC Blocks | DOGI Stale Secrets | Hybrid Stale Secrets | Hybrid Semantic Resets |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ycsb-a-pqc10000` | 6 | 0 | 1,024 | 145.208 s | 1.0066 | 1.0000 | 3,357 | 0 | 150,221 | 0 | 26 |
| `ycsb-a-pqc4000` | 6 | 0 | 560 | 106.256 s | 1.0454 | 1.0000 | 15,316 | 0 | 46,266 | 0 | 28 |
| `ycsb-a-pqc6000` | 6 | 0 | 712 | 124.102 s | 1.0376 | 1.0000 | 15,308 | 0 | 76,950 | 0 | 28 |
| `ycsb-f-pqc10000` | 6 | 0 | 900 | 143.232 s | 1.0279 | 1.0000 | 13,741 | 0 | 144,901 | 0 | 26 |
| `ycsb-f-pqc6000` | 6 | 0 | 733 | 115.407 s | 1.0105 | 1.0000 | 4,166 | 0 | 96,050 | 0 | 28 |
| `ycsb-f-pqc8000` | 6 | 0 | 733 | 134.766 s | 1.0528 | 1.0000 | 24,289 | 0 | 100,847 | 0 | 28 |

Actual-ZNS easy-to-pressure YCSB curve:

- Rows: `9`, failed rows: `0`
- WAF-pressure rows: `7`
- Semantic-gap rows: `9`

| Workloads | PQC Level | DOGI WAF | Hybrid WAF | DOGI GC | Hybrid GC | DOGI Stale | Hybrid Stale | DOGI Resets | Hybrid Resets |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ycsb-a-pqc2000`, `ycsb-f-pqc2000` | 2,000 | 1.0000 | 1.0000 | 0 | 0 | 35,472 | 0 | 0 | 28 |
| `ycsb-a-pqc4000` | 4,000 | 1.0454 | 1.0000 | 15,316 | 0 | 46,266 | 0 | 0 | 28 |
| `ycsb-f-pqc4000` | 4,000 | 1.0000 | 1.0000 | 0 | 0 | 74,274 | 0 | 0 | 28 |
| `ycsb-a-pqc6000` | 6,000 | 1.0376 | 1.0000 | 15,308 | 0 | 76,950 | 0 | 0 | 28 |
| `ycsb-f-pqc6000` | 6,000 | 1.0105 | 1.0000 | 4,166 | 0 | 96,050 | 0 | 0 | 28 |
| `ycsb-a-pqc8000` | 8,000 | 1.0282 | 1.0000 | 13,462 | 0 | 110,018 | 0 | 0 | 28 |
| `ycsb-f-pqc8000` | 8,000 | 1.0528 | 1.0000 | 24,289 | 0 | 100,847 | 0 | 0 | 28 |
| `ycsb-a-pqc10000` | 10,000 | 1.0066 | 1.0000 | 3,357 | 0 | 150,221 | 0 | 0 | 26 |
| `ycsb-f-pqc10000` | 10,000 | 1.0279 | 1.0000 | 13,741 | 0 | 144,901 | 0 | 0 | 26 |

Curve reading: `pqc2000` is the negative WAF control; WAF is already 1.0, but storage-history baselines still miss semantic reset. `pqc4000/pqc6000/pqc8000/pqc10000` show where GC/WAF separation appears on the same actual ZNS path. The larger `pqc10000` rows keep the claim realistic: WAF does not universally explode, but stale-secret exposure remains large and QUASAR/hybrid keeps GC and stale secrets at zero.

## Actual-ZNS Overhead

- Scope: actual ZNS replay overhead plus C-level policy-decision overhead
- Artifacts: `7`, rows: `84`, failed rows: `0`
- Caveat: Actual-ZNS latency is measured through zonefs helper appends/truncates and includes user-space helper overhead. C-level CPU numbers isolate only placement-decision cost.

| Policy | Append Cmds | Semantic Resets | Throughput MiB/s | Append Avg ms | Worst Append p99 ms | Reset Avg ms | CPU Median ns/write |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `dogi-history` | 560 | 0 | 208.10 | 118.839 | 161.605 | 1.826 | 2397.8 |
| `quasar` | 744 | 318 | 186.01 | 89.539 | 162.671 | 2.975 | 16.8 |
| `quasar-dogi-hybrid` | 743 | 318 | 177.25 | 88.841 | 163.609 | 2.974 | 1178.8 |

Overhead reading:

- Hybrid/DOGI append-average latency ratio: `0.748`
- Hybrid/DOGI throughput ratio: `0.852`
- Hybrid semantic reset delta: `318`
- Hybrid/DOGI C-level policy-decision median ratio: `0.492`

Use this as overhead accounting, not as a final production latency claim, because the actual-ZNS replay uses zonefs helper appends/truncates.

## xNVMe Raw ZNS Latency Probe

- Backend: `xnvme-linux-nvme-sync`
- Completed: `True`
- Device: `/dev/nvme0n1`
- Append count: `4096`
- Caveat: Raw xNVMe/Linux NVMe ioctl Zone Append probe. This bypasses zonefs helper overhead, but it is not an SPDK poll-mode result because the local build lacks a new enough liburing/SPDK backend.

| Metric | Value |
| --- | ---: |
| Append avg ns | 21487.3 |
| Append p50 ns | 21,843 |
| Append p95 ns | 23,124 |
| Append p99 ns | 26,064 |
| Append max ns | 174,261 |
| Reset before ns | 27,612 |
| Reset after ns | 4,469,600 |
| Throughput MiB/s | 181.79 |

This is the lower-overhead native command-path sanity check missing from the zonefs-helper overhead panel.

## Real Application Block Trace

- Artifact: `real-app-sysbench-pqc-block-trace`
- Device: `/dev/sdc2`
- Sysbench mode: `rndrw`
- Sysbench elapsed: `8.026` s
- Blkparse events: `194,570`
- Blkparse write events: `155,360`
- PQC sessions: `64`
- PQC records: `192`
- Boundary: Closes the real-application block-trace blocker for sysbench+PQC side writes; does not close SPDK/ZenFS latency, public DOGI parity, physical FDP, erase scope, or device diversity.

## Security Claim Boundary

- Device: `WZS4C8T1TDSP303` firmware `R6Z10009`
- SANICAP: `0x60000003`
- Sanitize supported: `True`
- Sanitize log status: `(1) Most Recent Sanitize Command Completed Successfully.`
- Per-cohort crypto-erase artifact: `per-cohort-key-isolated-crypto-erase`
- Destroyed cohort: `epoch-4`
- Target records inaccessible: `True`
- Unrelated records preserved: `True`
- Wrong-key rejection: `32/32`
- Shared-namespace sanitize called by key-erase artifact: `False`

| Operation | Advertised |
| --- | --- |
| Crypto erase sanitize | `True` |
| Block erase sanitize | `True` |
| Overwrite sanitize | `False` |

QUASAR proves reset eligibility and stale-secret exposure reduction, and this device's NVMe crypto-erase sanitize command path has been executed and validated as a destructive device/namespace-scoped operation. Zone reset alone is still not a physical erase proof, and sanitize must not be treated as a per-zone or per-epoch command on a shared namespace. A strong physical erase deployment requires a dedicated namespace/media pool, per-cohort encryption-key isolation, or future per-zone erase semantics whose blast radius matches the cohort being destroyed.

This is a cohort-scoped crypto-erase deployment path, not proof that zone reset physically erases NAND. It closes the erase blast-radius issue by moving the destructive primitive from device-wide sanitize to per-cohort encryption-key destruction; chip-off physical remanence still depends on the secrecy and destruction of the cohort DEK.

## Claim Matrix

- Claims: `14`
- Status counts: `{'qualified': 1, 'supported': 9, 'supported-boundary': 4}`

| Claim | Status | Caveat |
| --- | --- | --- |
| Storage-history baselines miss PQC death cohorts. | `supported` | This is a semantic/exposure claim; WAF may remain near 1.0 on easy traces. |
| QUASAR-DOGI hybrid removes stale-secret exposure on clean hinted actual-ZNS replays. | `supported` | Requires correct lifecycle hints and durable epoch-close logic. |
| WAF/GC gains are pressure-dependent, not universal. | `supported` | Do not claim QUASAR dominates every workload on total WAF. |
| The evaluation is not based on an overly easy PQC-only trace. | `supported` | Clean epoch traces remain sanity checks; the main benchmark must use DOGI/FAST-compatible overlays and hostile stress. |
| The improved deployable QUASAR design uses explicit modes rather than one universal knob. | `supported` | Do not present adaptive binning or strict residual migration as free default behavior. |
| The actual-ZNS comparison is reproducible from an artifact manifest. | `supported` | The manifest indexes current artifacts; long-running raw physical replays may still need explicit rerun time and device availability. |
| Residual migration is a deployable strict-exposure mode with explicit cost. | `supported` | Strict mode is not the default for every workload. |
| Hybrid has explicit reset overhead but lower policy-decision CPU cost than DOGI-style MLP. | `supported` | Actual-ZNS latency uses zonefs helper appends/truncates, so use as overhead accounting, not final production p99. |
| Zone reset alone is not physical erase; sanitize is validated only as a destructive device/namespace-scoped path. | `supported-boundary` | QUASAR proves reset eligibility and stale-secret exposure reduction, and this device's NVMe crypto-erase sanitize command path has been executed and validated as a destructive device/namespace-scoped operation. Zone reset alone is still not a physical erase proof, and sanitize must not be treated as a per-zone or per-epoch command on a shared namespace. A strong physical erase deployment requires a dedicated namespace/media pool, per-cohort encryption-key isolation, or future per-zone erase semantics whose blast radius matches the cohort being destroyed. |
| Per-cohort key isolation provides a cohort-scoped crypto-erase deployment path. | `supported-boundary` | This is crypto-erase by per-cohort key destruction, not proof that zone reset physically erases NAND or that every SSD exposes per-zone erase semantics. |
| Exact external baselines are included but have non-identical unit systems. | `qualified` | Do not mix exact-baseline internal units with QUASAR native ZNS throughput as if they were identical. |
| FDP can carry QUASAR's lifecycle signal, but scarce placement handles create collision pressure. | `supported-boundary` | This is a trace-driven handle-pressure model, not a physical FDP device performance result. |
| A real application block trace with PQC lifecycle side writes is captured. | `supported-boundary` | This closes the real-application trace realism gap, but it is not SPDK/ZenFS latency, public DOGI parity, or a ZNS placement result. |
| The current artifact set is paper-ready for the scoped system claim. | `supported` | Production-grade SPDK/ZenFS replay remains a Reviewer-2 blocker for the broader goal. |

Forbidden overclaims: QUASAR always wins on WAF; zone reset alone proves physical erase; shared-namespace sanitize is per-zone epoch cleanup; helper-based zonefs latency is production p99; exact external baseline units are directly interchangeable with packed ZNS replay.

YCSB-F p8000 actual-ZNS hard-case ladder:

| Scenario | Policy / Mode | Evidence | WAF | Secret Waiting End | Stale Secrets | Semantic Resets | Residual Blocks | Max Zones |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| pressure, no straggler | `fifo` | actual ZNS | 1.0758 | 56,832 | 92,959 | 0 | N/A | 3 |
| pressure, no straggler | `sepbit-style` | actual ZNS | 1.0364 | 35,292 | 114,520 | 0 | N/A | 7 |
| pressure, no straggler | `midas-style` | actual ZNS | 1.0193 | 25,726 | 128,224 | 0 | N/A | 5 |
| pressure, no straggler | `dogi-history` | actual ZNS | 1.0528 | 52,036 | 100,847 | 0 | N/A | 8 |
| pressure, no straggler | `QUASAR-DOGI clean` | actual ZNS | 1.0000 | 0 | 0 | 28 | N/A | 6 |
| straggler baseline | `fifo` | actual ZNS | 1.0759 | 56,832 | 92,959 | 0 | N/A | 3 |
| straggler baseline | `sepbit-style` | actual ZNS | 1.0364 | 35,292 | 114,520 | 0 | N/A | 7 |
| straggler baseline | `midas-style` | actual ZNS | 1.0193 | 25,726 | 128,224 | 0 | N/A | 5 |
| straggler baseline | `dogi-history` | actual ZNS | 1.0528 | 52,036 | 100,847 | 0 | N/A | 8 |
| straggler, controller low-overhead | `QUASAR-DOGI low-overhead` | actual ZNS | 1.0137 | 71,722 | 72,773 | 0 | 0 | 12 |
| straggler, controller balanced | `QUASAR-DOGI balanced` | actual ZNS | 1.3329 | 31,744 | 72,773 | 10 | 146,790 | 13 |
| straggler, controller strict | `QUASAR-DOGI strict-zero-wait` | actual ZNS | 3.5535 | 0 | 72,773 | 49 | 1,168,095 | 13 |

YCSB-F interpretation: WAF alone is misleading. MiDAS/SepBIT/DOGI can keep WAF close to 1.0 while leaving tens of thousands of secret blocks waiting and issuing no semantic resets. QUASAR-DOGI clean mode removes exposure; under stragglers, the controller explicitly trades WAF/copy cost for bounded or zero waiting.

## Adaptive Policy Audit

- Scope: adaptive QUASAR admission/binning comparison on YCSB and Sysbench pressure suites
- Default policy: `quasar-dogi-hybrid`
- Candidate policy: `quasar-adaptive-hybrid`
- Decision: `keep-current-hybrid`
- Reason: Adaptive binning did not beat the current hybrid on WAF, GC blocks, stale-secret blocks, or family count in the current single-tenant pressure suite.

| Suite | Current Hybrid Wins | Adaptive Hybrid Wins | Ties |
| --- | ---: | ---: | ---: |
| FAST/YCSB pressure | 4 | 0 | 0 |
| Sysbench pressure | 2 | 0 | 0 |

## Multi-Tenant Tenant-Isolation Mode

- Scope: multi-tenant PQC pressure with reset-time secret tenant isolation
- Decision: `add-tenant-isolation-mode`

| Workload | Policy | WAF | GC Blocks | Stale Secrets | Reset Secret Tenant Impurity | Families |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `multitenant-t032-pqc4000` | DOGI-style | 1.0261 | 4,446 | 24,599 | 0.914 | N/A |
| `multitenant-t032-pqc4000` | Current hybrid | 1.0000 | 3 | 0 | 0.942 | 44 |
| `multitenant-t032-pqc4000` | Tenant-isolation mode | 1.0029 | 488 | 0 | 0.000 | 1,284 |
| `multitenant-t032-pqc8000` | DOGI-style | 1.0403 | 9,352 | 46,728 | 0.923 | N/A |
| `multitenant-t032-pqc8000` | Current hybrid | 1.0000 | 0 | 0 | 0.942 | 44 |
| `multitenant-t032-pqc8000` | Tenant-isolation mode | 1.0003 | 72 | 0 | 0.000 | 1,284 |

Representative physical multi-tenant replay:

| Policy | WAF | GC Blocks | Stale Secrets | Semantic Resets | Secret Waiting End | Reset Secret Tenant Impurity | Avg Util | Max Live Phys Zones | Families |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DOGI-style | 1.0261 | 4,446 | 24,599 | 0 | 14,722 | 0.914 | 0.145 | 6 | N/A |
| Current hybrid | 1.0000 | 3 | 0 | 41 | 0 | 0.942 | 0.716 | 5 | 44 |
| Tenant-isolation mode | 1.0029 | 488 | 0 | 1,281 | 0 | 0.000 | 0.718 | 71 | 1,284 |

## Physical Hint Robustness

- Scope: actual ZNS bad-hint and straggler replay on YCSB-A p4000
- Trace: `artifacts/traces/fast-ycsb-pressure/ycsb-a-pqc4000.jsonl`
- Device limits: `mar=13`, `mor=13`
- Decision: `add-open-zone-aware-residual-fallback`

| Case | Sim WAF | Physical WAF | GC Blocks | Stale Secrets | Secret Waiting End | Physical Resets | Residual Blocks | Max Live Phys Zones | Max Pack Keys | Failed Rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DOGI clean | 1.0454 | 1.0454 | 15,316 | 46,266 | 16,944 | 0 | N/A | 8 | 7 | 0 |
| Hybrid clean | 1.0000 | 1.0000 | 0 | 0 | 0 | 28 | N/A | 6 | 5 | 0 |
| Hybrid missing hints 5% | 1.0000 | 1.0000 | 0 | 3,361 | 7 | 28 | N/A | 12 | 11 | 0 |
| Hybrid wrong epoch 5% | 1.0000 | 1.0000 | 0 | 0 | 0 | 112 | N/A | 12 | 11 | 0 |
| Hybrid straggler 5%, secret-group | 1.0153 | 1.0153 | 5,150 | 25,477 | 40,454 | 0 | N/A | 30 | 29 | 1 |
| Hybrid straggler 5%, epoch-bin-4 | 1.0153 | 1.0153 | 5,150 | 25,477 | 40,454 | 0 | N/A | 13 | 13 | 0 |
| Hybrid straggler 5%, epoch-bin-5 + residual | 1.0153 | 1.7098 | 5,150 | 25,477 | 0 | 27 | 234,549 | 13 | 12 | 0 |

Robustness interpretation: Exact secret-group packing is best for clean hints, missing hints, and wrong epochs, but delayed expiry/stragglers can exceed the WD ZN540 open-zone budget. Epoch-bin-4 keeps max live physical zones at the device limit and completes, but leaves stale-secret exposure. Epoch-bin-5 plus residual migration completes on the actual ZNS device, keeps max live physical zones within mor/mar, and reduces final secret waiting to zero at explicit GC-copy cost.

## Residual Fallback Frontier

- Scope: residual fallback threshold sweep across straggler workloads
- Decision: `use-residual-fallback-as-strict-exposure-mode`
- Dry-run rows: `48`

| Workload | Best Zero-Wait Candidate | Physical WAF | Residual Blocks | Max Zones | Actual ZNS Representative |
| --- | --- | ---: | ---: | ---: | --- |
| `exchange-pqc2000` | `epoch-bin-5`, th=12288 | 1.0182 | 3,515 | 10 | `epoch-bin-5`, th=4096, physical WAF 1.0182, waiting 0 |
| `sysbench-oltp-pqc4000` | `epoch-bin-8`, th=4096 | 1.2161 | 36,679 | 13 | `epoch-bin-8`, th=4096, physical WAF 1.2161, waiting 0 |
| `ycsb-f-pqc8000` | `epoch-bin-5`, th=32768 | 3.5535 | 1,168,095 | 13 | low_overhead: `epoch-bin-5`, th=4096, WAF 1.0137, waiting 71,722; balanced: `epoch-bin-6`, th=32768, WAF 1.3329, waiting 31,744; strict_zero_wait: `epoch-bin-5`, th=32768, WAF 3.5535, waiting 0 |

Residual interpretation: expose residual migration as a strict-exposure mode. It is practical for Exchange/Sysbench-style pressure but too expensive to make unconditional for every YCSB-F-like workload.

Bounded-overhead residual budget curve:

| Workload | Packing | Threshold | Copy Budget | Physical WAF | Secret Waiting End | Residual Blocks | Budget Skips |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `ycsb-f-pqc8000` | `epoch-bin-5` | 32,768 | 50,000 | 1.1096 | 70,656 | 44,105 | 68 |
| `ycsb-f-pqc8000` | `epoch-bin-5` | 32,768 | 100,000 | 1.2055 | 68,608 | 88,196 | 64 |
| `ycsb-f-pqc8000` | `epoch-bin-5` | 32,768 | 200,000 | 1.4461 | 43,008 | 198,860 | 51 |
| `ycsb-f-pqc8000` | `epoch-bin-5` | 32,768 | 400,000 | 1.8358 | 39,936 | 378,084 | 40 |

Budget interpretation: copy budget is the deployable low-overhead knob. It caps WAF/copy cost and reports the stale-secret exposure it leaves behind, while strict zero-wait mode remains available for high-assurance deployments.

Actual-ZNS bounded-overhead residual budget curve:

| Workload | Packing | Threshold | Copy Budget | Physical WAF | Secret Waiting End | Residual Blocks | Budget Skips | Resets | Max Zones |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ycsb-f-pqc8000` | `epoch-bin-5` | 32,768 | 50,000 | 1.1096 | 70,656 | 44,105 | 68 | 4 | 12 |
| `ycsb-f-pqc8000` | `epoch-bin-5` | 32,768 | 100,000 | 1.2055 | 68,608 | 88,196 | 64 | 8 | 12 |
| `ycsb-f-pqc8000` | `epoch-bin-5` | 32,768 | 200,000 | 1.4461 | 43,008 | 198,860 | 51 | 12 | 12 |
| `ycsb-f-pqc8000` | `epoch-bin-5` | 32,768 | 400,000 | 1.8358 | 39,936 | 378,084 | 40 | 18 | 12 |

Residual policy controller selections:

| Workload | Profile | Mode | Packing | Threshold | Recommended Copy Budget | Physical WAF | Secret Waiting End |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| `exchange-pqc2000` | `balanced` | `strict-zero-wait` | `epoch-bin-5` | 12,288 | 3,515 | 1.0182 | 0 |
| `exchange-pqc2000` | `low_overhead` | `strict-zero-wait` | `epoch-bin-5` | 12,288 | 3,515 | 1.0182 | 0 |
| `exchange-pqc2000` | `strict_zero_wait` | `strict-zero-wait` | `epoch-bin-5` | 12,288 | unbounded | 1.0182 | 0 |
| `sysbench-oltp-pqc4000` | `balanced` | `strict-zero-wait` | `epoch-bin-8` | 4,096 | 36,679 | 1.2161 | 0 |
| `sysbench-oltp-pqc4000` | `low_overhead` | `strict-zero-wait` | `epoch-bin-8` | 4,096 | 36,679 | 1.2161 | 0 |
| `sysbench-oltp-pqc4000` | `strict_zero_wait` | `strict-zero-wait` | `epoch-bin-8` | 4,096 | unbounded | 1.2161 | 0 |
| `ycsb-f-pqc8000` | `balanced` | `threshold-only-residual` | `epoch-bin-6` | 32,768 | 146,790 | 1.3329 | 31,744 |
| `ycsb-f-pqc8000` | `low_overhead` | `no-residual-copy` | `epoch-bin-5` | 4,096 | 0 | 1.0137 | 71,722 |
| `ycsb-f-pqc8000` | `strict_zero_wait` | `strict-zero-wait` | `epoch-bin-5` | 32,768 | unbounded | 3.5535 | 0 |

Controller interpretation: low-overhead mode can leave bounded exposure, balanced mode chooses a finite copy budget or threshold-only residual point, and strict mode keeps the zero-wait option explicit.

## Exact External Baselines

These are strong sanity checks, not direct apples-to-apples throughput comparisons with QUASAR's packed ZNS replay.

| Artifact | Scope | Main Result | Caveat |
| --- | --- | --- | --- |
| Exact DOGI physical compact | exact external DOGI prototype on physical ZNS, compacted LBA span | aggregate WAF `2.401`, avg WAF `2.333`, user `8.194` GiB, GC `11.478` GiB | Compacted LBA span preserves reuse order but is not the full original LBA span used by a production run. |
| Exact DOGI Alibaba p8000 physical compact | exact external DOGI prototype on physical ZNS, Alibaba-like p8000 compact trace | WAF `2.993`, user `4.588` GiB, GC `9.142` GiB, selection `DogiSelect` | This is the public DOGI binary on a compacted Alibaba-like PQC pressure trace. It validates the exact DOGI stack on the physical ZNS device, but units still differ from QUASAR's same-path packed replay. |
| Exact DOGI-family Alibaba p8000 suite | exact public DOGI prototype placement variants on physical ZNS, Alibaba-like p8000 compact trace | completed `3/3`, best `CostBenefit` WAF `2.804` | These are public DOGI prototype internal GiB counters on a compacted trace. They are exact DOGI-stack evidence but should not be mixed as apples-to-apples numbers with QUASAR's packed replay metrics. |
| Exact DOGI Alibaba p8000 original-LBA | exact external DOGI prototype on physical ZNS, Alibaba-like p8000 original LBA span | completed `true`, WAF `3.212`, user `4.589` GiB, GC `10.149` GiB | This run keeps the original LBA span and therefore removes the compact-LBA caveat for the Alibaba-like p8000 DOGI pressure trace. It is still an exact DOGI-stack counter, not a same-path QUASAR packed-replay metric. |
| Exact MiDAS memory repeat4 | exact external MiDAS memory-backed prototype on exchange-pqc2000 repeat4 compact trace | total WAF `1.010`, recomputed WAF `1.013` | MiDAS exact artifact uses internal page/traffic units and a memory-backed prototype, so it is evidence about MiDAS strength but not a direct ZNS throughput comparison. |
| Exact SepBIT repeat4 | exact external SepBIT trace_replay simulator on the same exchange repeat4 compact trace | SepBIT WA `2.400`, NoSep WA `3.696` | SepBIT numbers are trace_replay simulator WA, not native ZNS physical append latency. |

## Claim Boundary

- Do not claim QUASAR dominates MiDAS/DOGI/SepBIT on every workload or in every unit system.
- The strongest supported claim is narrower and cleaner: when PQC objects have protocol-known death cohorts, QUASAR-DOGI hybrid exposes that missing signal to placement and reset scheduling.
- MiDAS exact remaining strong on repeat4 is useful: it prevents overclaiming and pushes the paper toward semantic reset/exposure plus pressure-dependent WAF.
- Original-LBA exact DOGI now completes for Alibaba p8000; compact exact DOGI remains useful for multi-workload and placement-variant coverage.
