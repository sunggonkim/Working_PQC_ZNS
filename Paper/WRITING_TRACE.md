# QUASAR Writing Trace

This file records how the QUASAR draft follows the local writing guide and the previous accepted-paper drafts without copying their text.

## Source Mechanics Used

| Source | Mechanic copied | QUASAR location |
| --- | --- | --- |
| `HowToWritePaper.md` systems contract | Problem, gap, idea, evidence are stated before implementation detail. | Abstract and Introduction. |
| AURORA Introduction | Reach the systems bottleneck by paragraph 3. | `1.Introduction.tex`: PQC storage pressure, ZNS placement, death cohort gap. |
| AURORA/ScaleQsim Introduction | Use an early capability/gap table before contributions. | Table 1 in `1.Introduction.tex`. |
| DOGI paper structure | Define storage-placement baselines and workload families before evaluation claims, then group results into large evaluation families rather than fragmented micro-sections. | `2.Background.tex`, `6.Evaluation.tex`. |
| DOGI/FAST workload fairness | Preserve DOGI-friendly locality before adding PQC lifecycle stress. | `3.Motivation.tex`; `6.Evaluation.tex` Evaluation Setup and PQC Lifecycle Pressure blocks. |
| DOGI NoDaP role | Use an oracle only as an upper bound that exposes the missing lifetime signal, then turn the gap into design requirements. | `3.Motivation.tex`, `4.Design.tex`, `6.Evaluation.tex`. |
| Bottom-review interface attack | Explain why ZNS is measured and test how FDP would carry the same signal under handle pressure. | `2.Background.tex`, `4.Design.tex`, `6.Evaluation.tex`, `7.RelatedWork.tex`, `8.Discussion.tex`. |
| Bottom-review OS plumbing attack | Make the 32-byte hint path concrete instead of assuming POSIX carries it. | `4.Design.tex` Table `hint-delivery`, `5.Implementation.tex`. |
| Bottom-review security attack | Scope stored PQC state, separate reset eligibility from NIST-grade sanitization, and state that shared-namespace NVMe sanitize is not per-zone epoch cleanup. | `1.Introduction.tex`, `2.Background.tex`, `6.Evaluation.tex`, `7.RelatedWork.tex`, `8.Discussion.tex`. |
| ScaleQsim/AURORA Design | Start Design with architecture and procedure, then explain mechanisms. | `4.Design.tex`. |
| AURORA Evaluation | State setup, baselines, exclusions, and feasibility before results. | `6.Evaluation.tex`. |
| HowToWritePaper paragraph grammar | Claim first, concrete object, number/procedure, cause, bridge. | Each `\textbf{}` result block inside the five Evaluation subsections. |

## Paragraph-Role Map

The previous papers were used as a paragraph-role template.  The prose is original, but the argument jobs follow the local examples.

### Introduction

| Prior-paper role | QUASAR paragraph |
| --- | --- |
| Broad domain pressure, compactly introduced. | PQC moves from standardization to systems pressure. |
| Exact system substrate and bottleneck. | ZNS append/reset makes placement central. |
| Why prior systems miss the bottleneck. | History-based placement cannot see protocol death cohorts. |
| Early capability/gap table. | Table 1 compares SepBIT/MiDAS/DOGI with QUASAR-DOGI hybrid. |
| Mechanism distinction. | QUASAR uses lifecycle hints and death-cohort zone families. |
| Oracle-derived requirements. | Epoch upper bound yields lifecycle exposure, budgeted exact placement, and conservative reset requirements. |
| Security scope before overclaim. | Zone reset is separated from physical sanitize semantics; destructive sanitize is scoped to device/namespace blast radius. |
| Evidence paragraph with numbers. | Actual-ZNS fairness, Sysbench, and dynamic pressure results. |
| Contribution list. | Death cohort, architecture, implementation/evaluation, scoped claim. |

### Design

| Prior-paper role | QUASAR section |
| --- | --- |
| Overall architecture before details. | `4.Design.tex`, Overview and Figure 1. |
| State abstraction first. | Hint schema and zone family abstraction. |
| Concrete hint plumbing. | Hint delivery and enforcement table covers replay/user-space, SPDK/xNVMe, xattr/ioctl, io_uring, and FDP paths. |
| Requirement-to-mechanism mapping. | `4.Design.tex` maps protocol lifetime, placement budget, and reset safety to mechanisms and evaluation checks. |
| Procedure with decision rules. | Allocation rule and conservative epoch reclaim listings. |
| Invariant and fallback. | Epoch manager reset safety, overflow, residual migration. |
| Deployment modes. | Default hybrid, tenant isolation, strict residual, overflow. |
| Interface modes. | Native ZNS for measured append/reset accounting; FDP placement handles as deployment extension. |

### Evaluation

| Prior-paper role | QUASAR section |
| --- | --- |
| Setup and baselines before results. | Methodology, baselines, workloads. |
| Main fairness comparison. | Same-path actual-ZNS fairness matrix. |
| Workload breadth and pressure. | YCSB, Sysbench, Exchange/Varmail/Alibaba. |
| Claim eligibility gate. | DOGI-friendly first, PQC-hostile second; pure PQC-only traces are sanity checks only. |
| Real benchmark gate. | Initial real FIO iolog conversion is included as exposure-only sanity, and Sysbench/MySQL execution is marked as not yet a block-trace result. |
| Oracle/bound before claim. | Epoch upper bound is explicit, scoped, and not counted as QUASAR. |
| Component analysis. | Component ablation quantifies lifecycle hints, DOGI payload fallback, adaptive admission/binning, and residual fallback. |
| External baseline sanity. | Exact DOGI/MiDAS/SepBIT artifacts are separated from same-path replay. |
| FDP deployment pressure. | Trace-driven FDP mapping reports family/intent purity and families per placement handle across 8--128 handles. |
| Breakdown/overhead. | C-level decision cost and xNVMe command-path probe. |
| Correctness/security boundary. | Sanitize capability and explicit reset-vs-erase scope, including the shared-namespace blast-radius limitation. |

## Anti-Plagiarism Boundary

The draft follows paragraph roles and section order from the previous papers.  It does not copy their prose.  DOGI details are paraphrased from the local PDF and cited through `ref.bib`.

## Claim Boundaries Preserved

- Do not claim QUASAR always beats DOGI on WAF.
- Do not claim zone reset alone physically erases NAND.
- Do not claim shared-namespace NVMe sanitize/crypto-erase is a per-zone or per-epoch cleanup primitive.
- Do not claim every TLS session key must be persisted; QUASAR targets deployments that already write bounded PQC lifecycle state.
- Do not imply FDP is irrelevant; QUASAR is the lifecycle signal and ZNS/FDP are possible carriers.
- Do not imply the FDP result is hardware performance; it is a trace-driven handle-pressure model.
- Do not describe the 32-byte hint as if POSIX `write()` already transports it.
- Do not mix exact external DOGI/MiDAS/SepBIT unit systems with same-path actual-ZNS replay.
- Use easy p2000 rows as semantic-exposure evidence, not headline WAF evidence.
- Use the initial real-FIO iolog gate as pipeline/exposure evidence only until real YCSB/Sysbench traces exist.

## Files Created

- `0.Main.tex`
- `1.Introduction.tex`
- `2.Background.tex`
- `3.Motivation.tex`
- `4.Design.tex`
- `5.Implementation.tex`
- `6.Evaluation.tex`
- `7.RelatedWork.tex`
- `8.Discussion.tex`
- `9.Conclusion.tex`
- `ref.bib`
- `Makefile`
