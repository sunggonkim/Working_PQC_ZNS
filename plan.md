# QUASAR FAST Review Checkpoint Plan

이 파일은 QUASAR 논문을 쓰고 실험을 관리하기 위한 단일 체크포인트 문서다. 이전에 붙여 넣은 긴 리뷰 원문, 설계 메모, 대화형 작업 로그는 모두 제거하고, FAST 리뷰어가 공격할 질문을 다음 형식으로 정리한다.

```text
reviewer attack -> required answer -> evidence artifact -> paper location -> status
```

목표는 회피가 아니다. 각 우려는 논문 본문, 표, 그림, 실험 결과, 한계 문장 중 하나로 정면 대응해야 한다.

## 1. Current Claim Boundary

QUASAR의 현재 주장:

```text
PQC 서비스는 세션 종료, epoch 전환, key rotation, certificate rotation, erase policy처럼
암호 프로토콜 상태가 수명을 결정하는 객체를 지속적으로 쓴다. 기존 ZNS placement는 LBA,
recency, frequency, invalidation history를 보고 수명을 추론하지만, 이 protocol death event는
block layer 아래에서는 보이지 않는다. QUASAR는 작은 lifecycle hint로 PQC 객체를 death cohort
별 zone family에 배치하고, 일반 payload는 DOGI-style history placement에 맡긴다.
그 결과 actual ZNS replay에서 stale-secret exposure를 제거하고 pressure row에서 GC/WAF를 줄인다.
```

논문에서 금지할 주장:

- QUASAR가 모든 워크로드에서 항상 WAF를 크게 낮춘다.
- QUASAR가 DOGI/MiDAS/SepBIT를 일반 워크로드에서 대체한다.
- Zone reset 자체가 NAND physical erase를 항상 보장한다.
- Pure PQC-only trace가 headline WAF evidence다.
- Zonefs replay가 production SPDK/poll-mode latency를 증명한다.
- External DOGI/MiDAS/SepBIT native run 숫자를 same-path ZNS replay 숫자와 같은 단위로 직접 비교한다.

짧은 논문 문장:

```text
QUASAR is not a universal WAF optimizer. It exposes a protocol-lifetime signal
that storage-history placement cannot observe, and uses that signal only for
PQC lifecycle objects while preserving history-based placement for payload.
```

## 2. Current Evidence Scoreboard

| Evidence Gate | Status | Primary Artifact Or Paper Location |
| --- | --- | --- |
| Actual ZNS device exists and accepts append/reset-style replay | done | WD ZN540-class `/dev/nvme0n1`, `artifacts/results/physical-zns-readiness.md` |
| Same-path baselines include FIFO, SepBIT-style, MiDAS-style, DOGI-style, QUASAR, hybrid | done | `Paper/6.Evaluation.tex`, same-path actual-ZNS tables |
| DOGI/FAST-shaped six-axis fairness matrix | done | `artifacts/results/workload-hardness-matrix.md`, `Paper/6.Evaluation.tex` |
| YCSB-A/F pressure rows | done | `artifacts/results/fast-ycsb-pressure/`, `Paper/6.Evaluation.tex` |
| Multi-seed DOGI-family ratio sweep | done | `artifacts/results/dogi-paper-seed-sweep/summary.md`, `Paper/6.Evaluation.tex` |
| FAST-style DB pressure | done | `artifacts/results/fast-db-pressure/`, `Paper/6.Evaluation.tex` |
| Dynamic service pressure | done | `artifacts/results/fast-dynamic-pressure/`, `Paper/6.Evaluation.tex` |
| Bad/missing hints, tenants, stragglers, residual migration | done | robustness, residual, open-zone stress artifacts; `Paper/6.Evaluation.tex` |
| Space-utilization sensitivity | done | `artifacts/results/dogi-paper-workloads-smoke/space-sensitivity-tight-open.md`, `Paper/6.Evaluation.tex` |
| Exact public DOGI/MiDAS/SepBIT sanity runs | done with unit caveat | `artifacts/results/external-readiness.md`, `Paper/6.Evaluation.tex` |
| Real PQC stack traces | done for local stack | liboqs, OpenSSL oqsprovider CLI/C-API/TLS socket artifacts |
| C-level overhead microbenchmark | done | `artifacts/results/c-policy-overhead.md`, `Paper/6.Evaluation.tex` |
| xNVMe command-path latency probe | done as lower-overhead probe | `artifacts/results/xnvme-zns-latency/summary.md`, `Paper/6.Evaluation.tex` |
| Sanitize/crypto-erase command path | done for capability validation | physical security artifacts, `Paper/6.Evaluation.tex` |
| Reproducibility manifest and acceptance gates | done | `acceptance-report.json`, reproducibility manifest/validation |
| HowToWritePaper final audit matrix | done | `Paper/LINE_BY_LINE_FAST_AUDIT.md` |
| Build and tests | done | single-main `make all`, 117 Python tests, 41/41 acceptance gates |

Current readiness:

```text
Scoped FAST-style claim: supported.
Universal WAF claim: not supported and not allowed.
Production SPDK claim: not supported and not allowed.
Physical erase by reset-only claim: not supported and not allowed.
```

## 3. FAST Reviewer Checkpoint Register

### 3.1 Claim And Novelty

| Checkpoint | Required Answer | Evidence | Paper Location | Status |
| --- | --- | --- | --- | --- |
| Is QUASAR just a better predictor? | No. It does not predict storage history; it exposes protocol lifetime. | `quasar-claim-matrix.md` | Abstract, Introduction, Design | closed |
| Is death cohort a real systems concept? | Yes. It is the set of objects invalidated together by session/epoch/rotation policy. | workload-hardness and exposure artifacts | Introduction, Background, Design | closed |
| Does QUASAR replace DOGI? | No. Hybrid keeps DOGI-style history placement for payload. | `pqc0000` fairness controls | Evaluation fairness matrix | closed |
| Is WAF the only claim? | No. WAF/GC wins are pressure-dependent; stale-secret exposure is the core semantic claim. | YCSB pressure plus exposure rows | Evaluation, Discussion | closed |
| Is the oracle used honestly? | Yes. Epoch oracle is an upper bound, not a deployable baseline. | epoch upper-bound figure | Evaluation | closed |

Paper requirement:

```text
Say "Do not guess what the protocol already knows" once, but do not attack ML
systems generally. DOGI remains strong when lifetime is hidden and history is the
right signal.
```

### 3.2 Workload Fairness And Difficulty

| Checkpoint | Required Answer | Evidence | Paper Location | Status |
| --- | --- | --- | --- | --- |
| Is the workload too easy? | Headline rows are DOGI/FAST-shaped plus PQC overlay, not pure PQC-only streams. | `workload-hardness-matrix.md` | Evaluation Methodology, Workload Hardness | closed |
| Does DOGI get its native signals? | Yes. Hot/cold skew, overwrite locality, segment reuse, and dynamic service phases remain. | FIO/YCSB/Varmail/Alibaba/Exchange axes | Evaluation | closed |
| Are low-pressure rows overclaimed? | No. p2000/easy rows are negative WAF controls and exposure evidence only. | YCSB pressure curve | Evaluation | closed |
| Is the result cherry-picked at one ratio or seed? | No. A three-seed ratio sweep over six DOGI-style families reports 54 comparisons and shows 0% parity, 5% WAF-negative exposure rows, and 20% WAF/GC gains. | `dogi-paper-seed-sweep/summary.md` | Multi-Seed Ratio Sweep | closed for scoped claim |
| Is Sysbench a DOGI workload? | No. It is labeled FAST-style DB pressure, not DOGI reproduction. | `fast-db-pressure/` | Evaluation | closed |
| Is the paper static-YCSB-only? | No. Dynamic Exchange/Varmail/Alibaba-like pressure is included. | `fast-dynamic-pressure/` | Evaluation | closed |
| Are hostile cases tested? | Yes. Multi-tenant pressure, missing hints, wrong hints, and stragglers are tested. | robustness/open-zone/residual artifacts | Evaluation Robustness | closed |

Hardness rule for every trace:

```text
If a workload has no DOGI-visible locality, it is too easy for headline WAF.
If a workload has no GC/copy pressure, it is exposure evidence only.
If a workload has no stale-secret exposure, it does not test the PQC thesis.
```

### 3.3 Baseline Fairness

| Checkpoint | Required Answer | Evidence | Paper Location | Status |
| --- | --- | --- | --- | --- |
| Are FIFO/SepBIT/MiDAS/DOGI/QUASAR compared on the same path? | Yes. Main tables use same trace and same actual-ZNS replay path. | physical replay summaries | Evaluation Methodology, tables | closed |
| Are exact public baselines included? | Yes, but only as native sanity runs with unit caveats. | `external-readiness.md` | Exact Public Baseline Sanity Runs | closed with caveat |
| Is DOGI a strawman? | Same-path DOGI-style gives apples-to-apples comparison; exact DOGI is separately executed. | exact DOGI artifacts | Evaluation | closed with caveat |
| Are public baseline units mixed with QUASAR units? | No. Paper says they are not directly interchangeable. | claim matrix | Evaluation | closed |

Required wording:

```text
The same-path replay is the apples-to-apples comparison. Native DOGI/MiDAS/SepBIT
runs are sanity checks because their internal units and device models differ.
```

### 3.4 Physical ZNS And Device Scope

| Checkpoint | Required Answer | Evidence | Paper Location | Status |
| --- | --- | --- | --- | --- |
| Is this just simulation? | No. Actual WD ZN540-class ZNS replay is used. | physical readiness and replay artifacts | Evaluation Methodology | closed |
| Does zonefs overhead contaminate production latency? | Paper says yes and scopes zonefs latency as overhead accounting, not final p99. | xNVMe probe and zonefs results | Evaluation Overhead | closed with caveat |
| Is full SPDK done? | No. It remains external-validity strengthening. | xNVMe lower-overhead probe exists | Discussion | qualified |
| Are active/open zone limits quantified? | Yes. Device-limited robustness uses 13-zone accounting and fallback modes. | physical robustness and deployment selector | Design, Evaluation Robustness | closed |
| Are wear-leveling claims made? | No. Paper reports host-visible resets/utilization only. | reset/utilization artifacts | Discussion | closed with caveat |

Required wording:

```text
The physical results validate append/reset scheduling on an actual ZNS device.
They do not claim device-internal wear optimality or production SPDK latency.
```

### 3.5 Security And Erase Semantics

| Checkpoint | Required Answer | Evidence | Paper Location | Status |
| --- | --- | --- | --- | --- |
| What is `stale_secret_blocks`? | Expired secret-class logical blocks in a family not yet safely reset/sanitize eligible. | exposure artifacts | Evaluation Metrics | closed |
| Is exposure time-based? | E4 block-second evidence is cited; broad physical tables use final/representative counts for auditability. | E4 exposure timeline | Evaluation Metrics | closed with explanation |
| Does zone reset physically erase NAND? | Not by itself. Strong erasure requires sanitize/crypto-erase support. | security capability and sanitize artifacts | Security Boundary | closed |
| Is sanitize cost hidden? | Paper reports command-path validation and scopes SLO scheduling as deployment policy. | sanitize execution artifacts | Security Boundary, Discussion | closed with caveat |
| Can wrong hints lose data? | No. Epoch reset requires epoch-manager proof or durable close record. | bad-hint and crash/recovery model | Design Invariant, Robustness | closed |

Required wording:

```text
QUASAR reduces stale-secret exposure by aligning secret lifetime with reset
eligibility. When the device provides sanitize or crypto-erase semantics, QUASAR
can trigger those commands at epoch boundaries.
```

Forbidden wording:

```text
Zone reset always physically erases NAND cells.
```

### 3.6 Hint Trust, Tenant Abuse, And Privacy

| Checkpoint | Required Answer | Evidence | Paper Location | Status |
| --- | --- | --- | --- | --- |
| Can any tenant mark all writes as secrets? | No. High-priority hints come from trusted TLS/KMS/logging or privileged policy components. | trust-boundary design | Design | reflected |
| Can hints leak session/key identity? | Raw IDs do not cross the boundary; use opaque or keyed-hash cohort IDs. | hint schema | Design, Discussion | reflected |
| What if hints are missing? | Route to overflow/fallback; correctness preserved, exposure/performance may degrade. | robustness suite | Design, Evaluation | closed |
| What if hints are wrong? | Wrong hints cannot authorize unsafe reset; epoch close proof is separate from placement. | bad-hint and recovery artifacts | Design, Evaluation | closed |
| How is tenant isolation handled? | Tenant-local namespaces, per-tenant exact-family quotas, and admission limits. | multitenant/open-zone artifacts | Design, Robustness | reflected |

Required design invariant:

```text
A zone family is reset only after the epoch manager proves every object in the
family is expired or safely migrated.
```

### 3.7 Allocation, Admission, And Residual Migration

| Checkpoint | Required Answer | Evidence | Paper Location | Status |
| --- | --- | --- | --- | --- |
| Does strict cohort placement waste zones? | Admission, binning, overflow, utilization reporting, and residual fallback expose the tradeoff. | space/utilization and residual artifacts | Design, Evaluation | closed |
| Did QUASAR buy WAF by wasting zones? | No single-point claim. Exchange p2000 sensitivity shows WAF 1.001--1.002, closed-zone fill 0.941--0.961, stale secrets 0, and a disclosed lifetime-utilization cost. | `space-sensitivity-tight-open.md` | Component Ablation | closed for scoped claim |
| Is residual migration free? | No. Strict zero-wait can be expensive and is opt-in. | residual fallback sweep | Component Ablation, Robustness | closed |
| Is adaptive admission always better? | No. Current hybrid wins current single-tenant pressure; adaptive is for pressure/tenant modes. | component ablation | Component Ablation | closed |
| Are parameters specified? | Yes: active-family budget, min fill/bin width, residual threshold, copy budget, hint confidence, tenant mode. | Design parameter table | Design | closed |
| Is payload harmed by semantic grouping? | Hybrid delegates ordinary payload to DOGI-style history placement. | fairness controls and component ablation | Evaluation | closed |

Policy default:

```text
Default = QUASAR-DOGI hybrid.
Secrets/KEM/cert lifecycle objects use death-cohort placement.
Ordinary payload uses DOGI-style history fallback.
Strict zero-wait residual migration is a separate profile.
```

### 3.8 Overhead

| Checkpoint | Required Answer | Evidence | Paper Location | Status |
| --- | --- | --- | --- | --- |
| Is hint routing cheap? | C-level hint routing is 16.8 ns/write; DOGI-style small MLP is 2,397.8 ns/write; hybrid is 1,178.8 ns/write. | `c-policy-overhead.md` | Evaluation Overhead | closed |
| Does QUASAR add reset overhead? | Yes. Semantic resets are counted; paper does not hide them. | actual-ZNS reset counts | Evaluation tables | closed |
| Is xNVMe evidence production-ready? | It is a lower-overhead command-path probe, not a full SPDK service path. | xNVMe summary | Overhead, Discussion | qualified |
| Is adoption friction quantified? | 32-byte hint micro-case and OpenSSL/liboqs trace path show feasible integration. | Implementation | Implementation, Design | reflected |

Required wording:

```text
The decision path is cheap; the full zonefs replay path is not a production
latency claim.
```

### 3.9 Reproducibility

| Checkpoint | Required Answer | Evidence | Paper Location | Status |
| --- | --- | --- | --- | --- |
| Can reviewers audit artifacts? | Manifest lists artifacts, roles, hashes, and regeneration commands. | reproducibility manifest/validation | Evaluation Reproducibility | closed |
| Are tests current? | Python unit tests pass; acceptance checker passes 41/41. | test and acceptance outputs | audit docs | closed |
| Does the PDF build cleanly? | Single-main `make all` passes; unresolved refs/citations/errors grep clean. | Paper build log | audit docs | closed |
| Are raw external runs documented? | External readiness file records exact baselines and caveats. | `external-readiness.md` | Evaluation | closed |

Final validation commands:

```bash
python3 -m unittest discover -s code -p 'test*.py'
python3 code/sim/acceptance_check.py --out artifacts/results/acceptance-report.json
(cd Paper && make all)
grep -E "(undefined references|Citation .* undefined|Reference .* undefined|Fatal|Emergency|LaTeX Error|Package .* Error)" \
  Paper/0.Main.log
git diff --check -- plan.md Paper/6.Evaluation.tex Paper/FAST_READINESS_AUDIT.md Paper/LINE_BY_LINE_FAST_AUDIT.md
```

### 3.10 Writing And Presentation

| Checkpoint | Required Answer | Evidence | Paper Location | Status |
| --- | --- | --- | --- | --- |
| Does the paper follow the systems-paper spine? | Yes: problem, gap, bound, mechanism, physical evidence, ablation, cost, scope. | `LINE_BY_LINE_FAST_AUDIT.md` | whole paper | closed for scoped draft |
| Does it pass the `HowToWritePaper.md` final audit? | Yes for the scoped claim; figure labels/captions have been visually checked, Evaluation prose was compressed, and WAF-vs-utilization now visualizes the space tradeoff. | `LINE_BY_LINE_FAST_AUDIT.md` final audit matrix | whole paper | closed |
| Is the abstract compact? | Yes. It now follows a four-sentence problem/gap/approach/result shape. | `0.Main.tex` | Abstract | closed |
| Are captions reviewer-readable? | Main captions now state the lesson, not only the content. | Introduction/Design/Evaluation captions | figures/tables | improved |
| Is Evaluation too table-heavy? | The exact numbers remain in tables for auditability, but the final WAF-vs-utilization figure now gives reviewers a visual path through the space-amplification tradeoff. | `FAST_READINESS_AUDIT.md`, Figure `fig:space-sensitivity` | packaging | closed |
| Is prose too defensive? | A final compression pass cut Evaluation from 2,757 to 2,447 words while preserving numbers, caveats, and claim boundaries. | `Paper/6.Evaluation.tex` | final polish | closed |

Polish target:

```text
Keep caveats, but phrase them as claim boundaries rather than apologies.
```

## 4. Paper Reflection Map

Every checkpoint above must be visible in the paper. Current mapping:

| Paper Section | Must Carry | Current Status |
| --- | --- | --- |
| Abstract | PQC pressure, storage-history gap, QUASAR hint/hybrid idea, actual-ZNS result and scope | reflected |
| Introduction | Early pressure evidence, Table 1 prior-work gap, death-cohort thesis | reflected |
| Background | PQC object classes and lifetime sources; why ZNS placement matters | reflected |
| Motivation | Why storage-visible history misses protocol death events | reflected |
| Design | Hint schema, trust boundary, zone families, admission, reclaim invariant, crash/recovery, FDP/ZNS modes | reflected |
| Implementation | Trace/replay path, same-path baselines, actual-ZNS path, 32-byte hint micro-case | reflected |
| Evaluation Methodology | Platform, baselines, workloads, metrics, caveats | reflected |
| Workload Hardness | Prevent toy PQC-only overclaim | reflected |
| Fairness Matrix | DOGI/hybrid not crippled on easy DOGI axes; exposure gap remains | reflected |
| YCSB Pressure | DOGI/FAST-shaped pressure produces GC/WAF separation plus stale-secret gap | reflected |
| DB/Dynamic Pressure | Not YCSB-only; Sysbench labeled FAST-style DB pressure | reflected |
| Component Ablation | Lifecycle hints vs payload fallback vs admission vs residual cost | reflected |
| Exact Baselines | Native DOGI/MiDAS/SepBIT sanity with unit caveats | reflected |
| Overhead | Decision overhead, reset counts, zonefs caveat, xNVMe probe | reflected |
| Robustness | Missing/wrong hints, tenants, stragglers, strict mode cost | reflected |
| Security Boundary | Reset eligibility vs sanitize/crypto-erase semantics | reflected |
| Related Work | Learned placement, ZNS/FDP, secure deletion, PQC systems | reflected |
| Discussion | Non-universal WAF, single-device, SPDK/YCSB optional strengthening, no wear claim | reflected |

## 5. Experiment Inventory

### 5.1 Completed Core Experiments

| Experiment | Why It Exists | Required Result | Status |
| --- | --- | --- | --- |
| DOGI six-axis `pqc0000` control | Show history placement is not crippled without PQC | DOGI-style/hybrid competitive on ordinary WAF | done |
| DOGI six-axis `pqc2000` fairness | Show easy rows are exposure evidence | WAF near 1.0 allowed; stale-secret gap visible | done |
| YCSB-A/F pressure | Turn PQC lifecycle gap into GC/WAF pressure | Hybrid reduces GC and removes stale secrets | done |
| Multi-seed ratio sweep | Defend against cherry-picked workload ratio or random seed | Low ratios can be WAF-negative; 20% overlays show positive WAF/GC gains and stale-secret avoidance | done |
| Sysbench-OLTP pressure | Add FAST-style DB external validity | Hybrid reduces GC and removes stale secrets | done |
| Dynamic Exchange/Varmail/Alibaba pressure | Avoid static-YCSB-only story | Hybrid reduces GC and removes stale secrets | done |
| Hostile robustness | Attack QUASAR assumptions | Correctness preserved; cost exposed | done |
| Component ablation | Explain which mechanism matters | Hints remove stale secrets; DOGI fallback removes payload GC; residual has cost | done |
| Space-utilization sensitivity | Defend against space amplification attack | QUASAR lowers WAF/stale secrets without catastrophically underfilled closed zones, while exposing lifetime-utilization cost | done |
| Exact public baseline sanity | Avoid reimplementation-only criticism | Native runs complete, not unit-mixed | done |
| Real liboqs/OpenSSL traces | Show real PQC stack feasibility | Trace events and verification exist | done |
| Actual ZNS replay | Avoid simulator-only story | Device accepts append/reset schedule | done |
| xNVMe probe | Lower-overhead command-path sanity | Probe results reported as bound | done |
| Sanitize capability | Avoid erase overclaim | Capability/command path validated | done |

### 5.2 Optional Strengthening Experiments

These are valuable but not blockers for the scoped claim.

| Experiment | Why It Would Help | Current Treatment |
| --- | --- | --- |
| Full SPDK/poll-mode replay | Stronger production latency and host-stack realism | explicit limitation |
| Real YCSB/JDBC block trace capture | Stronger external validity than generated DOGI-shaped YCSB pressure | optional strengthening |
| More physical ZNS/FDP devices | Avoid single-device concern and test device-specific reset/sanitize behavior | explicit limitation |
| Repeated physical pressure runs | Stronger run-to-run stability beyond the three-seed simulator sweep | optional strengthening |
| Final WAF-vs-utilization figure | Replace some tables with easier visual reviewer path; current figure-label polish is already done | done |
| Per-epoch sanitize scheduling benchmark | Stronger secure erase SLO story | only needed for stronger erase claim |

## 6. Metric Interpretation Rules

| Metric | How To Use | What Not To Say |
| --- | --- | --- |
| WAF | Use for pressure rows where DOGI-style pays positive GC/copy cost. | Do not use low-pressure rows as WAF victory. |
| GC blocks | Main performance pressure metric. | Do not hide that some rows have small GC gap. |
| Stale secret blocks | Main semantic exposure metric across PQC overlays. | Do not equate it with physical erasure by itself. |
| Stale block-seconds | Time-based exposure evidence. | Do not replace all physical tables with block-seconds if auditability suffers. |
| Reset count | Shows QUASAR creates reset/sanitize opportunities. | Do not claim resets are free. |
| Zone utilization | Defends against space amplification. | Do not optimize WAF alone. |
| Live physical zones | Defends against active/open-zone budget attacks. | Do not ignore device limits. |
| Decision latency | Shows hint routing overhead. | Do not claim zonefs replay p99 is production latency. |

Interpretation rule:

```text
If WAF is modest but stale secrets drop to zero, the row supports the semantic
gap claim. If WAF/GC also drops under pressure, the row supports the performance
claim. Do not merge these into one exaggerated claim.
```

## 7. Final Paper Invariants

The paper must keep these invariants through the final editing pass:

1. Death cohort is the core idea.
2. Hybrid is the default deployable policy.
3. Payload placement remains history-based.
4. Exact epoch oracle is diagnostic only.
5. Same-path replay is the apples-to-apples baseline.
6. Exact public baselines are sanity evidence with caveats.
7. Zone reset is reset eligibility, not guaranteed physical erasure.
8. Sanitize/crypto-erase is a separate device capability path.
9. Bad hints cannot authorize unsafe reset.
10. Strict zero-wait mode has explicit residual-copy cost.
11. Low-pressure WAF rows are negative controls or exposure evidence.
12. Single-device and zonefs limitations are stated.

## 8. Final Pre-Submission Checklist

Required before freezing the paper:

- [x] Abstract has problem/gap/approach/result and no universal WAF overclaim.
- [x] Introduction shows early evidence and the prior-work capability gap.
- [x] Design includes trust boundary, hint schema, admission, reset invariant, and recovery.
- [x] Evaluation separates fairness, pressure, negative controls, dynamic rows, and hostile robustness.
- [x] Same-path baselines and exact external baselines are not unit-mixed.
- [x] Security section separates reset eligibility from sanitize/crypto-erase.
- [x] Overhead section separates decision overhead from zonefs helper overhead.
- [x] Reproducibility section cites manifest, validation, and acceptance gates.
- [x] `HowToWritePaper.md` final audit matrix is checked item by item.
- [x] Build and tests pass.
- [x] Final figure-label/caption polish on current PDF build.
- [x] Final prose compression pass to reduce defensive density.

## 9. Current Bottom Line

QUASAR is not "인류 최고의 모든 워크로드 placement scheme" and the paper should never say that. The defensible FAST claim is narrower and stronger:

```text
For PQC lifecycle objects, the missing signal is not another history feature.
It is protocol death time. QUASAR exposes that signal through a small hint,
uses it to form reset-eligible death cohorts, and keeps learned/history placement
for ordinary payload. The actual-ZNS evidence supports this claim under
DOGI/FAST-shaped pressure, dynamic service pressure, and hostile robustness cases.
```

This is the line the paper should hold.

## 10. Reference Links

- DOGI FAST '26: https://www.usenix.org/conference/fast26/presentation/kim-jeeyun
- DOGI paper PDF: https://www.usenix.org/system/files/fast26-kim-jeeyun.pdf
- NIST FIPS 203 ML-KEM: https://csrc.nist.gov/pubs/fips/203/final
- NVM Express FDP overview: https://nvmexpress.org/wp-content/uploads/FMS-2023-Flexible-Data-Placement-FDP-Overview.pdf
- Samsung FDP white paper: https://download.semiconductor.samsung.com/resources/white-paper/getting-started-with-fdp-v4.pdf
- xNVMe FDP tutorial: https://xnvme.io/tutorial/fdp/index.html
- Samsung PM1763 official page: https://semiconductor.samsung.com/ssd/enterprise-ssd/pm1763/
