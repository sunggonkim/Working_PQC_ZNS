# FAST Readiness Audit For QUASAR Draft

## Verdict

The draft has a FAST-shaped scoped claim, but it is not yet a full
production-grade FAST submission.  Reviewer-2 style objections remain serious:
same-path DOGI-style baselines are not a substitute for end-to-end public DOGI
parity, zonefs/xNVMe is not SPDK/ZenFS, FDP is modeled rather than implemented,
and NVMe sanitize must not be presented as per-zone physical erasure.  The
defensible claim is narrower: protocol-lifetime hints expose a PQC death-cohort
signal that storage-history placement cannot observe, and the actual-ZNS
evidence supports reset eligibility and stale-secret exposure reduction under
the measured workloads and fallback modes.

## Current Evidence State

| Requirement | Current Evidence | Status |
| --- | --- | --- |
| Follow `HowToWritePaper.md` contract. | Problem/gap/idea/evidence appear in the abstract, Introduction, Design, Evaluation, and Discussion. | Satisfied for scoped claim. |
| Match DOGI/FAST argument mechanics. | The paper has an epoch upper bound, DOGI-style workload axes, same-path baselines, exact public baseline sanity runs, component ablation, overhead, and physical replay. | Satisfied for scoped claim. |
| Avoid toy PQC-only claims. | Workload-hardness matrix separates fairness, negative controls, pressure, claim-gate rows, and hostile robustness. | Satisfied. |
| Keep DOGI fair. | Non-PQC controls preserve DOGI/hybrid history-placement behavior; hybrid keeps DOGI-style payload placement. | Satisfied. |
| Use physical ZNS evidence. | WD ZN540-class actual-ZNS zonefs replay, physical pressure suites, xNVMe latency probe, and destructive sanitize command-path validation. | Satisfied only for scoped actual-ZNS accounting; not production SPDK latency. |
| Address ZNS-vs-FDP interface risk. | Background and Discussion frame QUASAR as lifecycle-placement policy; Evaluation now includes a trace-driven FDP handle-pressure model showing family/intent purity across 8--128 handles. | Satisfied as a deployment model; no physical FDP hardware result. |
| Give concrete hint plumbing. | Design has a hint-delivery table covering replay/user-space, SPDK/xNVMe-style request metadata, xattr/ioctl, io_uring, and FDP placement handles. | Satisfied for design; kernel implementation remains future work. |
| Scope stored-secret threat model. | Background clarifies QUASAR targets persisted PQC lifecycle state such as KMS envelopes, key-wrap records, audit logs, recovery records, and spill paths, not universal TLS session-key persistence. | Satisfied. |
| Include exact public baselines. | Exact DOGI, MiDAS, and SepBIT sanity runs are included but not unit-mixed with same-path replay; the public-DOGI parity audit records five direct checks and the remaining full-parity gaps. | Satisfied with explicit caveat. |
| Include component ablation. | Evaluation explains lifecycle hints, DOGI payload fallback, admission, and residual migration. | Satisfied. |
| Include robustness/sensitivity. | Missing hints, wrong epochs, tenant pressure, stragglers, residual strict mode, and open-zone pressure are covered. | Satisfied. |
| Include space-amplification defense. | Component Ablation now reports an Exchange p2000 WAF/space sensitivity: QUASAR pays a small lifetime-utilization cost but keeps closed-zone fill high and stale secrets at zero. | Satisfied for scoped claim. |
| Include variability evidence. | A three-seed DOGI-family ratio sweep reports 54 comparisons and shows the break-even behavior: low PQC ratios are exposure evidence, while 20% overlays produce WAF/GC gains. | Satisfied for scoped claim. |
| Define security metric. | `stale_secret_blocks` and stale-secret block-seconds are defined; E4 exposure timeline is cited. | Satisfied. |
| Avoid physical erase overclaim. | Paper says zone reset alone is not physical NAND erasure, cites NIST SP 800-88 Rev. 2, and now states shared-namespace sanitize is destructive device/namespace-scoped command-path evidence, not per-zone epoch cleanup. | Tightened; strong erase requires matching erase scope. |
| Reproducibility. | `acceptance_check.py` reports 42/42 gates; current tests pass; PDFs build cleanly. | Satisfied. |
| Avoid false completion. | `actual-zns-goal-completion-audit.json` reports `scoped_claim_ready=true`, `full_goal_complete=false`, and six FAST R2 production blockers. | Satisfied as an anti-overclaim gate. |
| Final `HowToWritePaper.md` audit. | `LINE_BY_LINE_FAST_AUDIT.md` now checks the guide's pre-submission questions, DOGI figure-role translation, and the design-choice rule directly. Figure 5 uses subfloats; the later sensitivity, FDP, and overhead figures are compact one-column figures with no embedded numeric labels. | Satisfied. |

## Current Format And Test Evidence

| Check | Result |
| --- | --- |
| `make all` | Passed. |
| `Paper/0.Main.pdf` | Single FAST/USENIX-format main PDF; 14 pages, letter. |
| LaTeX unresolved references/citations/errors grep | Clean. |
| `python3 -m unittest discover -s code -p 'test*.py'` | 122 tests passed in the latest run. |
| `python3 code/sim/acceptance_check.py --out artifacts/results/acceptance-report.json` | 42/42 gates passed. |
| `python3 code/sim/report_goal_completion_audit.py` | Scoped claim ready, full goal incomplete, six FAST R2 production blockers recorded. |
| `git diff --check` | Clean for edited paper/plan files. |

## What Is Still Not "Perfect"

| Gap | Why It Matters | Status |
| --- | --- | --- |
| Figure polish | FAST reviewers read plots before prose. Motivation has a one-column semantic-gap diagnostic; Evaluation now has component ablation, open-zone/config sensitivity, FDP handle pressure, and prototype overhead figures. Numeric graph labels were removed to avoid table/figure duplication. | Checked after current rebuild. |
| Table-heavy Evaluation | The paper still carries exact measured matrices in tables, but the main reviewer attacks now have figure paths: pressure, component attribution, open-zone sensitivity, and overhead. | Intentional auditability tradeoff. |
| Full production SPDK path | Zonefs helper replay validates actual-ZNS append/reset behavior, but not final production p99 latency. | Required before claiming production-grade FAST latency; requires SPDK/ZenFS or equivalent app-level path. |
| Real YCSB/JDBC block traces | Would strengthen external validity beyond DOGI-shaped YCSB pressure generation. | Optional strengthening for the scoped claim; not represented as completed. |
| FDP implementation | The paper now has a trace-driven FDP placement-handle model and figure, but there is no real FDP device result. | Required before positioning FDP as solved; physical FDP/emulator replay remains open. |
| End-to-end app p99 | Sysbench/MySQL is an execution gate, not full QUASAR-integrated DB block tracing. | Explicitly scoped. |
| More device diversity | One WD ZN540-class device plus emulator/exact-baseline artifacts is not a wear-leveling study. | Explicit limitation. |
| Final prose pass | Evaluation was consolidated into five FAST-style subsections with `\textbf{}` run-in leads while preserving the evidence and claim boundaries. | Checked for current build. |
| Final figure/caption inspection | Current pass includes the newly added compact FDP handle-pressure figure plus the open-zone and prototype figures. | Checked after current rebuild. |

## FAST Reviewer Attack Readiness

| Attack | Paper Response |
| --- | --- |
| "This only wins on easy PQC traces." | The paper uses DOGI/FAST-shaped workload axes, pressure rows, negative controls, and workload-hardness gates; pure PQC traces are not headline WAF evidence. |
| "DOGI is a strawman." | Same-path DOGI-style is used for apples-to-apples physical replay; exact public DOGI runs are included separately with unit caveats, and the public-DOGI parity audit states this is substantial direct evidence but not full end-to-end parity. |
| "WAF gains are small." | The paper does not claim universal WAF dominance. Easy rows prove exposure reduction; pressure rows prove GC/WAF gains. |
| "Is this cherry-picked?" | The paper includes a three-seed ratio sweep over DOGI-style families and states that 5% PQC overlays can be WAF-negative while 20% overlays show positive WAF/GC gains. |
| "Did QUASAR buy WAF by wasting zones?" | Open-zone/config sensitivity shows exact cohort placement can exceed the device limit, binning fits the budget, and strict cleanup has explicit WAF cost. |
| "Hints are unrealistic or abusable." | The paper defines a trust boundary, privileged hint emitters, opaque cohort IDs, per-tenant quotas, and overflow fallback. |
| "How does the 32-byte hint cross the stack?" | The paper gives concrete attachment points and states that POSIX write alone does not carry the hint. |
| "Why not FDP instead of ZNS?" | The paper maps QUASAR families to FDP handles, reports handle-count collision/purity pressure, and explains why ZNS is used first for measurable append/reset accounting. |
| "Zone reset is not secure erase." | The paper says this directly and claims reset eligibility/exposure reduction by default; sanitize/crypto-erase is destructive device/namespace-scoped command-path evidence, not per-zone epoch cleanup on shared media. |
| "Why are these PQC artifacts stored?" | The paper scopes to deployments that already persist bounded lifecycle state and does not require universal TLS key persistence. |
| "Strict exposure costs too much." | The paper shows residual migration can be expensive and treats strict zero-wait as an opt-in mode. |
| "The device evidence is narrow." | The paper scopes the physical claim to one WD ZN540-class device and avoids device-internal wear claims. |

## Line-By-Line Following Assessment

The draft follows the role grammar of the previous papers, not their wording.
That is the correct boundary. Copying prose line-by-line would be plagiarism;
matching the argument mechanics is the goal.

| Required Role | QUASAR Draft Counterpart | Quality |
| --- | --- | --- |
| Abstract: problem, gap, approach, result. | PQC storage pressure, DOGI/MiDAS/SepBIT gap, QUASAR death-cohort hints, actual-ZNS numbers. | Good. |
| Introduction: pressure by paragraph 3. | PQC service writes, ZNS placement, death cohort mismatch. | Good. |
| First evidence figures. | PQC lifecycle characterization appears immediately after the opening gap; Motivation adds a WAF-vs-stale-secret diagnostic; metric-bearing YCSB pressure follows in Evaluation. | Good. |
| Capability/prior-work table. | Table 1 maps SepBIT/MiDAS/DOGI/QUASAR by signal and blind spot. | Good. |
| Design map. | Architecture figure plus hint schema, trust boundary, families, admission, reclaim, recovery. | Good. |
| Evaluation setup. | Platform, baselines, workloads, metrics, caveats. | Good. |
| Main result. | Same-path actual-ZNS fairness and pressure rows. | Good. |
| Ablation. | Component ablation uses subfloats for WAF, GC, and expired PQC secrets, with the table kept as qualitative checkpoint support. | Good. |
| Sensitivity/robustness. | Open-zone budget, missing/wrong hints, stragglers, binning, and residual cleanup cost are figure-backed. | Good. |
| Cost and limitation. | Prototype overhead figure separates actual-ZNS zonefs accounting from C-level decision cost; FDP handle-pressure figure separates deployment modeling from physical FDP claims; text keeps the xNVMe/SPDK caveat. | Good. |

## Bottom Line

This is no longer "too easy" or "just a simulator" for the scoped death-cohort
claim, but it is still not strong-accept ready.  A real submission should treat
full SPDK/ZenFS-style replay, real YCSB/JDBC or RocksDB block traces, physical
FDP/emulator replay, and additional devices as major risk reducers rather than
cosmetic extras.  The current paper answers the scoped FAST reviewer question:

```text
What signal is missing from current ZNS placement,
how does QUASAR expose it,
what does the actual device show,
and where does the claim stop?
```
