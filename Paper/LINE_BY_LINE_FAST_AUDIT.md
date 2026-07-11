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
| First evidence figure | Old YCSB plot made the WAF gap look small and visually weak. | Replace it with `fig1-intro-pressure`: GC blocks plus stale-secret blocks on actual-ZNS YCSB pressure rows. | fixed; verify in PDF |
| Workload breadth | Evidence was table-heavy and did not visually match DOGI-style breadth. | Add `fig2-pressure-breadth`: Sysbench, Exchange, Varmail, Alibaba-like pressure rows with DOGI/MiDAS/SepBIT/QUASAR-DOGI. | fixed; verify in PDF |
| Mechanism attribution | Ablation existed mostly as a table. | Add `fig3-component-ablation`: history-only, lifecycle hints, and hybrid fallback. | fixed; verify in PDF |
| Space-amplification attack | Space tradeoff was present but not enough of a reviewer-facing graph. | Add `fig4-resource-overhead`, panel 1: WAF vs closed-zone fill plus DOGI stale-secret point. | fixed; verify in PDF |
| Overhead | Overhead was prose plus numbers, not a FAST-style figure. | Add `fig4-resource-overhead`, panels 2--3: policy cost and xNVMe append-latency bound. | fixed; verify in PDF |
| Robustness | Straggler/strict-mode cost was buried in text. | Add `fig6-robustness`: waiting secrets, physical WAF, residual copied blocks. | fixed; verify in PDF |
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
| Upper bound | Epoch oracle shows what becomes possible once death time is visible. | `fig:epoch-upper-bound`. |
| Limitation of history | DOGI/MiDAS/SepBIT see LBA/frequency/history, not session close or rotation. | Motivation, Table 1, `fig:pressure-breadth`. |
| Design mechanisms | Hint schema, zone families, admission/open-zone budget, conservative reset. | Design section and architecture figure. |
| Workload breadth | DOGI six-axis controls plus YCSB, Sysbench, Exchange, Varmail, Alibaba pressure. | Methodology, tables, `fig:pressure-breadth`. |
| Component analysis | Hints vs history-only vs hybrid payload fallback. | `fig:component-ablation`, `tab:ablation`. |
| Sensitivity | WAF vs closed-zone fill under open-zone budget. | `fig:resource-overhead`. |
| Overhead | Policy-decision cost and lower-overhead xNVMe command-path probe. | `fig:resource-overhead`. |
| Robustness | Missing/wrong hints, tenants, stragglers, strict-zero-wait copy cost. | `fig:robustness`, robustness text. |

## Remaining Reviewer Risks

These are not solved by better plotting and must stay visible:

| Risk | Why It Matters | Current Defense | Stronger Future Evidence |
| --- | --- | --- | --- |
| Real workload realism | Generated DOGI-shaped overlays may still look synthetic. | Six DOGI axes, YCSB, Sysbench, dynamic service pressure, real liboqs/OpenSSL traces. | Real YCSB/JDBC block traces captured from a live DB stack. |
| Native DOGI equivalence | Same-path DOGI-style placement is not the full public DOGI stack. | Exact public DOGI/MiDAS/SepBIT runs are separated as sanity evidence. | More native DOGI adapter runs with trace conversion documentation. |
| Production path | Zonefs replay is not SPDK poll-mode. | xNVMe append probe plus explicit zonefs caveat. | Full SPDK replay with p99 service latency. |
| Device generality | One ZN540-class device may not represent all ZNS/FDP devices. | Device capabilities and limitations are named. | Additional ZNS/FDP devices and reset/sanitize variance. |
| Space amplification | Death-cohort zones can waste capacity. | Admission, binning, overflow, residual fallback, `fig:resource-overhead`. | Longer multi-tenant pressure and capacity-utilization sweeps. |
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
