# Line-By-Line FAST Audit For QUASAR

This audit answers the uncomfortable question directly: the paper is not
"perfect", but the current draft now follows the systems-paper spine in
`HowToWritePaper.md` closely enough to be treated as a scoped FAST-style draft.
The remaining risks are not hidden blockers in the main claim; they are
submission-polish and external-validity strengthening items that a FAST reviewer
may still ask for.

Sources checked:

1. `HowToWritePaper.md`: local systems-paper manual and rubric.
2. `Paper/Previous papers/fast26-kim-jeeyun.pdf`: DOGI's accepted FAST role
   structure.
3. Current QUASAR paper files under `Paper/`.
4. Current evidence artifacts under `artifacts/results/` and `plan.md`.

## Four-Sentence Contract

| Contract Item | Current QUASAR Version | Status |
| --- | --- | --- |
| Problem | PQC services write secrets, KEM artifacts, signatures, metadata, and payload whose lifetimes are governed by sessions, epochs, rotations, and erase policy. | Strong. The pressure appears in the abstract and first Introduction paragraph. |
| Gap | SepBIT/MiDAS/DOGI-style placement infer lifetime from storage-visible history, but PQC death cohorts are defined by protocol state above the block layer. | Strong. Table 1 and Motivation repeat the missing boundary without caricaturing DOGI. |
| Idea | Add compact cryptographic lifecycle hints, place short-lived PQC objects by death cohort, and preserve DOGI-style history placement for ordinary payload. | Strong. "Death cohort" is now the structural insight and maps to the allocator. |
| Evidence | Actual-ZNS replay, same-path baselines, exact public baseline sanity runs, workload-hardness gates, component ablation, xNVMe probe, sanitize command-path validation, robustness, and 41/41 acceptance gates. | Strong for the scoped claim. Full production SPDK and real YCSB/JDBC block traces would strengthen deployment realism, but the current paper does not depend on them for the main claim. |

Verdict: the contract is coherent and evidence-backed. It is not a universal
"QUASAR wins everywhere" contract; it is a scoped claim about exposing a
protocol lifetime signal that history-based placement cannot observe.

## DOGI Structure Match

DOGI's FAST paper follows this role chain:

```text
LSS/ZNS WAF problem
-> oracle upper bound
-> limitations of storage-history placement
-> named design mechanisms
-> DOGI/FAST workload families
-> simulator plus zoned-device prototype
-> component analysis and overhead
```

QUASAR now follows the same argument mechanics:

| DOGI Role | QUASAR Counterpart | Current Grade | Evidence |
| --- | --- | --- | --- |
| Problem setup | PQC creates protocol-lifetime storage pressure and stale-secret exposure. | Strong | Abstract, Introduction, Table 1. |
| Oracle/bound | Epoch upper bound shows the missing lifetime signal and motivates lifecycle hints. | Good | `fig:epoch-upper-bound`, component ablation. |
| Design components | Hint schema/trust boundary, zone families, admission/open-zone budget, epoch reclaim, crash recovery. | Strong | Design sections and parameter table. |
| Workload axis | FIO Zipf, YCSB-A/F, Varmail, Alibaba, Exchange-shaped axes, plus clearly labeled FAST-style Sysbench DB pressure. | Good | Evaluation methodology and workload-hardness matrix. |
| Baselines | FIFO, SepBIT-style, MiDAS-style, DOGI-style, QUASAR, hybrid; exact DOGI/MiDAS/SepBIT runs kept separate. | Good | Same-path tables plus exact-baseline sanity paragraph. |
| Prototype | Trace simulator plus actual WD ZN540 zonefs replay, xNVMe latency probe, sanitize command-path check. | Good for scoped claim | Physical ZNS and security capability artifacts. |
| Component analysis | Lifecycle hints, DOGI payload fallback, admission, residual fallback, overhead. | Good | `tab:ablation`, overhead and robustness sections. |

The biggest difference from DOGI is scope. DOGI is a general log-structured
placement paper. QUASAR is a semantic-lifetime paper for PQC overlays. The draft
now states that boundary directly instead of pretending to be a universal WAF
optimizer.

## HowToWritePaper Rubric Score

Scores use the guide's `0/1/2` scale.

| Category | Score | Evidence | Remaining Risk |
| --- | ---: | --- | --- |
| Problem | 2 | Problem appears early and names PQC services, ZNS placement, and stale-secret exposure. | None material. |
| Gap | 2 | Prior work is grouped by storage-visible signals; the missing protocol boundary is explicit. | None material. |
| Idea | 2 | "Place by death cohort" explains the design. | Must keep terminology consistent. |
| Design | 2 | Mechanisms have inputs, decisions, invariants, fallback, trust boundary, and recovery. | None material for scoped claim. |
| Evaluation | 2 | Fair same-path baselines, physical ZNS, exact sanity baselines, pressure rows, multi-seed ratio sweep, component ablation, space sensitivity, robustness, overhead, security boundary. | Full production SPDK and real YCSB/JDBC block traces would strengthen realism. |
| Figures | 2 | Architecture, intro YCSB pressure, epoch bound, workload hardness, and WAF-vs-utilization figures cover the main evidence path; tables carry exact audit numbers. | No structural figure blocker remains. |
| Language | 2 | Scope and terms are consistent, and the Evaluation compression pass cut 310 words while preserving evidence and boundaries. | Remaining density is mainly table packaging, not unsupported prose. |
| Scope | 2 | The paper explicitly avoids universal WAF and physical-erase overclaims. | None material. |
| Reproducibility | 2 | Manifest, artifact hashes, acceptance checker, build logs, and 117 tests are current. | Long physical reruns still depend on device availability. |

Total: `18/18`. Per `HowToWritePaper.md`, this is submission-grade structure,
but not a guarantee of acceptance. The remaining risks are external-validity
strengthening items: full SPDK replay, real YCSB/JDBC block traces, more devices,
and longer physical reruns.

## HowToWritePaper Final Audit Matrix

This table follows the final pre-submission audit in `HowToWritePaper.md`
directly. The goal is not to declare perfection; it is to make the remaining
weaknesses explicit instead of hiding them.

| Audit Question | Current Evidence | Verdict |
| --- | --- | --- |
| Can the core idea be recovered from title, abstract, first figure, and conclusion? | Title names cryptographic intent-aware ZNS for PQC; abstract has four sentences; Figure 1 shows negative-control plus pressure behavior; conclusion repeats death cohort, hybrid payload fallback, actual-ZNS scope. | Pass. |
| Do captions tell the evidence story? | Main captions state the lesson: negative WAF control, history-vs-lifecycle gap, oracle bound, workload-hardness guardrail, YCSB pressure, dynamic pressure, component ablation. Figure 4 labels were shortened and visually checked in the current PDF. | Pass. |
| Do subsection headings form a logical outline? | Evaluation proceeds methodology -> hardness -> oracle bound -> DOGI-favorable control -> fairness -> pressure -> variability -> dynamic rows -> ablation -> exact baselines -> overhead -> robustness -> security -> reproducibility. | Pass. |
| Are vague words controlled? | Searches for `significant`, `efficient`, `robust`, `comprehensive`, `novel`, `optimal`, and related terms show no unsupported performance adjectives in the main paper; remaining uses such as `full-suite`, `strong`, and `complete` are scoped. | Pass. |
| Are unsupported absolutes avoided? | The paper explicitly rejects universal WAF, reset-as-physical-erase, and production-SPDK claims. Uses of `zero` refer to measured stale-secret rows, not universal guarantees. | Pass. |
| Does every main claim have evidence or scope? | Main claims map to actual-ZNS tables, workload-hardness matrix, multi-seed ratio sweep, component ablation, overhead benchmark, xNVMe probe, sanitize path, and Discussion limits. | Pass for scoped claim. |
| Does every major design mechanism appear in Evaluation? | Lifecycle hints, payload fallback, admission/binning, residual migration, bad-hint fallback, open-zone pressure, reset eligibility, and security boundary all appear in Evaluation. | Pass. |
| Are negative results and limitations framed as scope? | Easy WAF rows, 5% WAF-negative ratio sweep, MiDAS compact strength, strict residual cost, zonefs/SPDK caveat, and reset-vs-sanitize boundary are stated before or inside the relevant result sections. | Pass. |
| Do graphs have readable labels, units, and fair baselines? | Included figures build correctly, have high-resolution source assets, and captions name workload/metric/scope. Figure 4's workload-hardness labels were compacted and visually checked, and Figure 6 adds WAF-vs-utilization evidence for the space-amplification attack. Tables remain for exact audit numbers. | Pass. |
| Can artifacts regenerate or explain reported numbers? | The artifact manifest records 37 evidence artifacts; acceptance passes 41/41; 117 unit tests pass; exact baseline and physical-ZNS artifacts are named in audits and plan. | Pass. |

Hard-blocker check: no missing problem, no unfair baseline-only story, no
simulator-only claim, no hidden physical-erase claim, and no unsupported
universal WAF claim remain in the current draft.

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
| Ablation | Which mechanism explains the result. | Component table connects history, lifecycle hints, payload fallback, admission, residual migration. | Pass | Could become a figure later. |
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
