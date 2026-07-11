# FAST-Style Figure And Structure Audit For QUASAR

This audit is a checkpoint list, not a pass certificate.  The previous draft
failed the visual-evidence standard implied by DOGI and `HowToWritePaper.md`:
it had too few reviewer-facing figures, the first evidence plot leaned too much
on a weak YCSB/WAF view, and the audit text was too self-congratulatory.  This
file therefore tracks what must be fixed or defended before the paper can be
called FAST-shaped.

Sources checked:

1. `HowToWritePaper.md`: local systems-paper manual and rubric.
2. `Paper/Previous papers/fast26-kim-jeeyun.pdf`: DOGI's accepted FAST role
   structure.
3. Current QUASAR paper files under `Paper/`.
4. Current evidence artifacts under `artifacts/results/`.
5. Current FAST-style figure generator:
   `code/sim/plot_fast_style_quasar_figures.py`.

## Correction Checkpoints

| Checkpoint | Previous Problem | Current Fix | Status |
| --- | --- | --- | --- |
| First evidence figure | Old YCSB plot made the WAF gap look small and visually weak. | Use `fig:intro-ycsb` as characterization, then make `fig:ycsb-pressure` the first metric-bearing PQC pressure figure. | fixed; verified in PDF |
| Workload breadth | Evidence was table-heavy and did not visually match DOGI-style breadth. | Use `fig:pressure-breadth`: Sysbench, Exchange, Varmail, Alibaba-like pressure rows with FIFO/SepBIT/MiDAS/DOGI/QUASAR. | fixed; verified in PDF |
| Mechanism attribution | Ablation existed mostly as a table. | Use `fig:component-ablation`: staged subfloats for WAF, GC, and expired PQC secrets across history-only, lifecycle hints, and hybrid fallback. | fixed; verified in PDF |
| Configuration sensitivity | Space/open-zone tradeoff was scattered across prose and tables. | Use `fig:open-zone-robustness`: live-zone budget, waiting secrets, and strict cleanup WAF cost. | fixed; verified in PDF |
| Overhead | Overhead was prose plus numbers, not a FAST-style figure. | Use `fig:prototype-overhead`: actual-ZNS replay throughput plus C-level placement-decision cost. | fixed; verified in PDF |
| Plot hygiene | Old plots repeated table numbers, used oversized pages, and mixed figure labels with the wrong data story. | Remove numeric labels from bars/points, keep Figure 5 as subfloats, and make Figures 6--7 compact one-column figures instead of `figure*`. | fixed; verified in PDF |
| Audit honesty | Old audit claimed `18/18` and “submission-grade” too early. | Remove score-as-victory language; keep remaining risks explicit. | fixed |
| Prior-paper match | “Line-by-line” cannot mean copying DOGI's exact figures because QUASAR's claim is narrower. | Use role parity: failure, bound, design, workload breadth, ablation, overhead, robustness. | fixed with scope |

## DOGI Role Parity

DOGI's FAST paper uses a role chain:

```text
LSS/ZNS WAF problem
-> oracle or upper-bound intuition
-> storage-history placement limits
-> named design mechanisms
-> DOGI/FAST workload families
-> simulator plus zoned-device prototype
-> component analysis
-> overhead
```

QUASAR must now preserve the same role chain without pretending to be a general
WAF optimizer:

| DOGI Role | QUASAR Counterpart | Evidence |
| --- | --- | --- |
| Problem setup | PQC creates protocol-lifetime storage pressure and stale-secret exposure. | Abstract, Introduction, Table 1, `fig:intro-ycsb`. |
| Upper bound | Epoch oracle shows what becomes possible once death time is visible. | Evaluation Setup's `Epoch upper bound` run-in block; not plotted as a headline figure. |
| Limitation of history | DOGI/MiDAS/SepBIT see LBA/frequency/history, not session close or rotation. | Motivation, Table 1, `fig:pressure-breadth`. |
| Design mechanisms | Hint schema, zone families, admission/open-zone budget, conservative reset. | Design section and architecture figure. |
| Workload breadth | DOGI six-axis controls plus YCSB, Sysbench, Exchange, Varmail, Alibaba pressure. | Methodology, tables, `fig:pressure-breadth`. |
| Component analysis | Hints vs history-only vs hybrid payload fallback. | `fig:component-ablation`, `tab:ablation`. |
| Configuration sensitivity | Open-zone budget, binning, missing/wrong hints, and residual cleanup cost. | `fig:open-zone-robustness`. |
| Prototype overhead | Actual-ZNS replay throughput and C-level decision-cost isolation. | `fig:prototype-overhead`. |
| Robustness | Missing/wrong hints, tenants, stragglers, strict-zero-wait copy cost. | `fig:open-zone-robustness`, robustness text. |

## DOGI Figure-Role Translation

The rewrite follows DOGI's evaluation grammar by role, not by copying its
exact metric names.  DOGI optimizes general invalidation-time prediction;
QUASAR targets PQC lifecycle placement, so the corresponding y-axes must be
WAF/GC plus expired-secret exposure.

| DOGI Figure Role | What DOGI Shows | QUASAR Translation |
| --- | --- | --- |
| Fig. 11: user-written placement comparison | Prediction accuracy and WAF across FIO, YCSB-A/F, Varmail, Alibaba, Exchange. | `fig:ycsb-pressure` and `fig:pressure-breadth` compare all same-path baselines under DOGI-friendly carriers plus PQC lifecycle side writes. |
| Fig. 12: GC-written relocation | Relocation accuracy and destination group distribution. | `fig:component-ablation` shows GC copied blocks disappearing when lifecycle hints and payload fallback separate death cohorts. |
| Fig. 13: grouping/config behavior | How group count and misprediction interact across workload types. | `fig:open-zone-robustness` shows exact grouping, binning, open-zone limits, and residual migration cost. |
| Fig. 14: component analysis | Incrementally adds DOGI mechanisms and reports WAF. | `fig:component-ablation` incrementally moves from history-only to lifecycle hints to hybrid payload fallback, with WAF/GC/exposure subfloats. |
| Fig. 15/Table 5: overhead/prototype | Inference throughput and foreground latency. | `fig:prototype-overhead` is a compact one-column figure that separates zonefs actual-ZNS throughput accounting from isolated C-level placement-decision cost. |

## Remaining Reviewer Risks

These are not solved by better plotting and must stay visible:

| Risk | Why It Matters | Current Defense | Stronger Future Evidence |
| --- | --- | --- | --- |
| Real workload realism | Generated DOGI-shaped overlays may still look synthetic. | Six DOGI axes, YCSB, Sysbench, dynamic service pressure, real liboqs/OpenSSL traces. | Real YCSB/JDBC block traces captured from a live DB stack. |
| Native DOGI equivalence | Same-path DOGI-style placement is not the full public DOGI stack. | Exact public DOGI/MiDAS/SepBIT runs are separated as sanity evidence. | More native DOGI adapter runs with trace conversion documentation. |
| Production path | Zonefs replay is not SPDK poll-mode. | xNVMe append probe plus explicit zonefs caveat. | Full SPDK replay with p99 service latency. |
| Device generality | One ZN540-class device may not represent all ZNS/FDP devices. | Device capabilities and limitations are named. | Additional ZNS/FDP devices and reset/sanitize variance. |
| Space amplification | Death-cohort zones can waste capacity. | Admission, binning, overflow, residual fallback, `fig:open-zone-robustness`. | Longer multi-tenant pressure and capacity-utilization sweeps. |
| Secure erase overclaim | Zone reset is not universal physical erasure. | Paper separates reset eligibility from sanitize/crypto-erase semantics. | Per-epoch sanitize scheduling benchmark if making a stronger erase claim. |

## Current Verdict

The corrected draft can claim role parity with DOGI-style paper structure only
after the rebuilt PDF is visually inspected.  The defensible claim remains:

```text
QUASAR is not a universal placement scheme.  For PQC lifecycle objects, it
exposes protocol death time that history-based ZNS placement cannot infer, and
the hybrid keeps learned/history placement for ordinary payload.
```

## Design-Choice Rule Audit

`HowToWritePaper.md` says each important design choice needs pressure,
alternative, chosen rule, cost, and evaluation closure. QUASAR now has that
mapping:

| Design Choice | Pressure | Alternative Considered | Cost Exposed | Evaluation Closure |
| --- | --- | --- | --- | --- |
| Lifecycle hint instead of pure history prediction | PQC object lifetime is defined by protocol state above the block layer. | Infer lifetime from LBA/frequency/invalidation history as DOGI-style placement does. | Requires a trusted hint path and conservative handling of missing/wrong hints. | Fairness matrix, YCSB pressure, multi-seed ratio sweep, bad-hint robustness. |
| Hybrid payload fallback instead of pure semantic placement | Payload still has storage-visible locality that history placement handles well. | Route all writes by semantic class. | Pure semantic grouping can leave payload GC cost. | Non-PQC controls and component ablation show DOGI fallback is the deployable default. |
| Admission/binning/overflow instead of exact epoch zone for every cohort | Real ZNS devices have open/active-zone limits and sparse epochs can waste space. | Strict per-epoch placement for every hinted object. | Space utilization and exposure precision trade off under pressure. | Space-utilization sensitivity, open-zone stress, tenant and straggler robustness. |
| Conservative epoch reset instead of immediate reset on hint | Wrong hints or crash recovery must not discard live data. | Trust hints as reset authorization. | Residual migration or downgrade-to-GC can increase WAF. | Residual frontier and strict-zero-wait results expose the copy cost. |
| Actual-ZNS zonefs replay plus xNVMe probe instead of claiming full SPDK | Need physical append/reset evidence without overclaiming production latency. | Simulator-only evaluation or unimplemented SPDK claim. | Zonefs helper overhead remains a limitation. | Physical replay, xNVMe append latency probe, and Discussion boundary. |

## Paragraph-Role Audit

| Section | Required Role From Guide | Current State | Pass? | Notes |
| --- | --- | --- | --- | --- |
| Abstract | Four-sentence argument with numbers. | Problem, gap, approach, actual-ZNS numbers, and scoped claim are present. | Pass | Now compressed to the guide's four-sentence shape. |
| Introduction P1-P3 | Domain pressure, current limitation, technical problem. | PQC pressure, ZNS placement pressure, and death-cohort mismatch appear before the first figure. | Pass | Matches AURORA/ScaleQsim role order. |
| First evidence figure | Early figure exposes bottleneck. | Actual-ZNS YCSB pressure appears at the start of the Introduction. | Pass | Caption has metric lesson and negative-control scope. |
| Prior-work classes | Group prior systems by capability. | Table 1 groups SepBIT/MiDAS/DOGI/hybrid by signal, strength, blind spot, consequence. | Pass | Good FAST-style positioning. |
| Distinction | State mechanism difference. | Death-cohort placement is a mechanism, not just "better placement." | Pass | Keep this phrase stable. |
| Design | Architecture plus mechanisms and invariants. | Architecture figure, hint schema, trust boundary, families, admission, reclaim, recovery, modes. | Pass | Strongest section after the latest pass. |
| Implementation | Concrete engineering without replacing Design. | Trace/replay framework, 32-byte hint micro-case, same-path baselines, physical path, xNVMe, sanitize. | Pass | Good scope boundary for zonefs/xNVMe. |
| Evaluation setup | Hardware, baselines, workloads, metrics. | Present and explicit; exact external baselines are not unit-mixed. | Pass | Repetition evidence exists in artifacts but is not a headline figure. |
| Main result | End-to-end comparison against fair baselines. | Fairness, YCSB pressure, multi-seed ratio sweep, Sysbench pressure, dynamic pressure. | Pass | Claim is metric-bundled, not WAF-only. |
| Ablation | Which mechanism explains the result. | Component figure and table connect history, lifecycle hints, payload fallback, admission, residual migration. | Pass | Figure and table now share the role. |
| Sensitivity/robustness | Parameter and failure-mode behavior. | Space-utilization sensitivity, missing/wrong hints, tenant pressure, residual fallback, strict mode costs. | Pass | Honest about utilization cost and high strict-mode WAF. |
| Overhead | CPU, latency, reset, resource costs. | C-level routing cost, zonefs helper caveat, xNVMe latency probe. | Pass | Does not overclaim SPDK. |
| Negative results/scope | Where system does not win. | Non-PQC controls, easy WAF rows, physical erase caveat, device diversity caveat. | Pass | This is now reviewer-facing, not buried. |

## Hard Review Risks

| Risk | Why A Reviewer May Attack | Current Defense | Remaining Strengthening |
| --- | --- | --- | --- |
| "Toy workload" | Clean PQC traces can be too easy. | Workload-hardness gate, DOGI six-axis, pressure rows, negative controls, dynamic pressure. | Real YCSB/JDBC block traces would strengthen external validity. |
| "DOGI strawman" | Style-compatible DOGI may diverge from public DOGI. | Same-path baselines are used for apples-to-apples replay; exact public DOGI/MiDAS/SepBIT are separate sanity runs. | More adapter documentation and native run logs. |
| "WAF gain too small" | Some rows show WAF near 1.0. | Paper states easy rows are exposure evidence; WAF/GC wins are pressure-dependent. | Keep headline metric bundle: WAF/GC, stale secrets, resets, overhead. |
| "Cherry-picked pressure point" | A single seed or ratio could make the result look cleaner than it is. | Three-seed ratio sweep shows 0% parity, 5% WAF-negative exposure rows, and 20% WAF/GC gains. | More physical repeated runs would further strengthen final submission evidence. |
| "Space amplification" | Death-cohort zones can waste capacity. | Admission, binning, overflow, residual fallback, utilization reporting, and the Exchange p2000 WAF-vs-utilization figure. | More devices would strengthen generality. |
| "Hint abuse" | Tenants may inflate priority. | Trust boundary, privileged hint emitters, opaque cohort IDs, quotas, admission limits. | Production policy implementation would strengthen deployment story. |
| "Physical erase overclaim" | Zone reset is not NAND erase. | Paper says this directly and separates sanitize/crypto-erase command-path evidence. | Per-epoch sanitize scheduling benchmark if making a stronger erase claim. |
| "No production SPDK" | Zonefs helper overhead is not final p99. | xNVMe command-path probe plus explicit caveat. | Full SPDK/poll-mode replay. |

## Current Bottom Line

The current paper is not "perfect", and no serious systems paper is. But it is
no longer just an idea memo or a toy simulator story. It now has the major
FAST-style spine:

```text
problem -> gap -> bound -> mechanism -> physical evidence -> ablation -> cost -> scope
```

The paper can credibly argue a scoped FAST claim: PQC creates protocol-defined
death cohorts that history-based ZNS placement cannot observe, and QUASAR
exposes that signal with small hints while keeping history placement for payload.
The next work is final-paper polish, not basic research rescue.
