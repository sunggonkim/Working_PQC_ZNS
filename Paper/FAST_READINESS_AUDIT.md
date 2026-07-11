# FAST Readiness Audit For QUASAR Draft

## Verdict

The draft is not perfect, but it is now a credible FAST-shaped systems paper
for the scoped claim it actually makes. It should not claim that QUASAR is a
universal WAF optimizer, a physical-erase mechanism by itself, or a production
SPDK implementation. It can claim that protocol-lifetime hints expose a PQC
death-cohort signal that storage-history placement cannot observe, and that the
actual-ZNS evidence supports that claim under the measured workloads and
fallback modes.

## Current Evidence State

| Requirement | Current Evidence | Status |
| --- | --- | --- |
| Follow `HowToWritePaper.md` contract. | Problem/gap/idea/evidence appear in the abstract, Introduction, Design, Evaluation, and Discussion. | Satisfied for scoped claim. |
| Match DOGI/FAST argument mechanics. | The paper has an epoch upper bound, DOGI-style workload axes, same-path baselines, exact public baseline sanity runs, component ablation, overhead, and physical replay. | Satisfied for scoped claim. |
| Avoid toy PQC-only claims. | Workload-hardness matrix separates fairness, negative controls, pressure, claim-gate rows, and hostile robustness. | Satisfied. |
| Keep DOGI fair. | Non-PQC controls preserve DOGI/hybrid history-placement behavior; hybrid keeps DOGI-style payload placement. | Satisfied. |
| Use physical ZNS evidence. | WD ZN540-class actual-ZNS zonefs replay, physical pressure suites, xNVMe latency probe, and sanitize command-path validation. | Satisfied with zonefs/xNVMe caveat. |
| Include exact public baselines. | Exact DOGI, MiDAS, and SepBIT sanity runs are included but not unit-mixed with same-path replay. | Satisfied with caveat. |
| Include component ablation. | Evaluation explains lifecycle hints, DOGI payload fallback, admission, and residual migration. | Satisfied. |
| Include robustness/sensitivity. | Missing hints, wrong epochs, tenant pressure, stragglers, residual strict mode, and open-zone pressure are covered. | Satisfied. |
| Include space-amplification defense. | Component Ablation now reports an Exchange p2000 WAF/space sensitivity: QUASAR pays a small lifetime-utilization cost but keeps closed-zone fill high and stale secrets at zero. | Satisfied for scoped claim. |
| Include variability evidence. | A three-seed DOGI-family ratio sweep reports 54 comparisons and shows the break-even behavior: low PQC ratios are exposure evidence, while 20% overlays produce WAF/GC gains. | Satisfied for scoped claim. |
| Define security metric. | `stale_secret_blocks` and stale-secret block-seconds are defined; E4 exposure timeline is cited. | Satisfied. |
| Avoid physical erase overclaim. | Paper says zone reset alone is not physical NAND erasure and separates sanitize/crypto-erase evidence. | Satisfied. |
| Reproducibility. | `acceptance_check.py` reports 41/41 gates; current tests pass; PDFs build cleanly. | Satisfied. |
| Final `HowToWritePaper.md` audit. | `LINE_BY_LINE_FAST_AUDIT.md` now checks the guide's pre-submission questions, DOGI figure-role translation, and the design-choice rule directly. Figures 5--7 were rebuilt with subfloats, no embedded numeric labels, and DOGI-style component/sensitivity/overhead roles. | Satisfied. |

## Current Format And Test Evidence

| Check | Result |
| --- | --- |
| `make all` | Passed. |
| `Paper/0.Main.pdf` | Single FAST/USENIX-format main PDF; 13 pages, letter. |
| LaTeX unresolved references/citations/errors grep | Clean. |
| `python3 -m unittest discover -s code -p 'test*.py'` | 117 tests passed. |
| `python3 code/sim/acceptance_check.py --out artifacts/results/acceptance-report.json` | 41/41 gates passed. |
| `git diff --check` | Clean for edited paper/plan files. |

## What Is Still Not "Perfect"

| Gap | Why It Matters | Status |
| --- | --- | --- |
| Figure polish | FAST reviewers read plots before prose. Figure 5 now carries component ablation, Figure 6 carries open-zone/config sensitivity, and Figure 7 carries prototype overhead. Numeric graph labels were removed to avoid table/figure duplication. | Checked for current build. |
| Table-heavy Evaluation | The paper still carries exact measured matrices in tables, but the main reviewer attacks now have figure paths: pressure, component attribution, open-zone sensitivity, and overhead. | Intentional auditability tradeoff. |
| Full production SPDK path | Zonefs helper replay validates actual-ZNS append/reset behavior, but not final production p99 latency. | Explicitly scoped; xNVMe probe partially addresses command path. |
| Real YCSB/JDBC block traces | Would strengthen external validity beyond DOGI-shaped YCSB pressure generation. | Optional strengthening for the scoped claim; not represented as completed. |
| More device diversity | One WD ZN540-class device plus emulator/exact-baseline artifacts is not a wear-leveling study. | Explicit limitation. |
| Final prose pass | Evaluation was compressed from 2,757 to 2,447 words while preserving the evidence and claim boundaries. | Checked for current build. |
| Final figure/caption inspection | Current visual pass checked the redesigned Figure 5--7 pages after label removal and subfloat conversion. Repeat only if figures move or new plots are added. | Checked for current build. |

## FAST Reviewer Attack Readiness

| Attack | Paper Response |
| --- | --- |
| "This only wins on easy PQC traces." | The paper uses DOGI/FAST-shaped workload axes, pressure rows, negative controls, and workload-hardness gates; pure PQC traces are not headline WAF evidence. |
| "DOGI is a strawman." | Same-path DOGI-style is used for apples-to-apples physical replay, and exact public DOGI runs are included separately with unit caveats. |
| "WAF gains are small." | The paper does not claim universal WAF dominance. Easy rows prove exposure reduction; pressure rows prove GC/WAF gains. |
| "Is this cherry-picked?" | The paper includes a three-seed ratio sweep over DOGI-style families and states that 5% PQC overlays can be WAF-negative while 20% overlays show positive WAF/GC gains. |
| "Did QUASAR buy WAF by wasting zones?" | Open-zone/config sensitivity shows exact cohort placement can exceed the device limit, binning fits the budget, and strict cleanup has explicit WAF cost. |
| "Hints are unrealistic or abusable." | The paper defines a trust boundary, privileged hint emitters, opaque cohort IDs, per-tenant quotas, and overflow fallback. |
| "Zone reset is not secure erase." | The paper says this directly and claims reset eligibility/exposure reduction by default; sanitize/crypto-erase is a separate device capability path. |
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
| First evidence figure. | PQC lifecycle characterization appears immediately after the opening gap; metric-bearing YCSB pressure follows in Evaluation. | Good. |
| Capability/prior-work table. | Table 1 maps SepBIT/MiDAS/DOGI/QUASAR by signal and blind spot. | Good. |
| Design map. | Architecture figure plus hint schema, trust boundary, families, admission, reclaim, recovery. | Good. |
| Evaluation setup. | Platform, baselines, workloads, metrics, caveats. | Good. |
| Main result. | Same-path actual-ZNS fairness and pressure rows. | Good. |
| Ablation. | Component ablation uses subfloats for WAF, GC, and expired PQC secrets, with the table kept as qualitative checkpoint support. | Good. |
| Sensitivity/robustness. | Open-zone budget, missing/wrong hints, stragglers, binning, and residual cleanup cost are figure-backed. | Good. |
| Cost and limitation. | Prototype overhead figure separates actual-ZNS zonefs accounting from C-level decision cost; text keeps the xNVMe/SPDK caveat. | Good. |

## Bottom Line

This is no longer "too easy" or "just a simulator". The current draft has a
defensible FAST-style spine and clean scoped claims. It is still not a magical
guarantee of acceptance: full SPDK, real YCSB/JDBC block traces, and more device
diversity would make it stronger. But the paper now answers the
core FAST reviewer question directly:

```text
What signal is missing from current ZNS placement,
how does QUASAR expose it,
what does the actual device show,
and where does the claim stop?
```
