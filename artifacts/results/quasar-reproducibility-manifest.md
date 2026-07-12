# QUASAR Reproducibility Manifest

- Scope: reproducibility manifest for actual-ZNS baseline-vs-QUASAR comparison
- Passed: `True`
- Artifacts: `39`
- Missing or empty: `[]`

## Artifacts

| ID | Path | Bytes | SHA256 | Role | Claim |
| --- | --- | ---: | --- | --- | --- |
| `same_path_actual_zns_fairness` | `artifacts/results/packed-physical-zonefs-replay-dogi-paper-pqc2000-z512-secret-group-helper.json` | 310144 | `a2a68a144d0c` | six DOGI/FAST workload-axis actual-ZNS fairness matrix | storage-history baselines miss PQC death cohorts even when WAF is near 1.0 |
| `ycsb_actual_zns_pressure_curve` | `artifacts/results/fast-ycsb-pressure/ycsb-actual-zns-pressure-curve.json` | 16180 | `a4b6b8a29a46` | actual-ZNS YCSB p2000 negative control plus p4000/p6000/p8000/p10000 pressure curve | WAF/GC gains are pressure-dependent while semantic reset gap is broad |
| `ycsb_actual_zns_p2000_raw` | `artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-pqc2000-z512-helper.json` | 61422 | `9505e243ac1a` | raw actual-ZNS packed replay for YCSB p2000 negative WAF control | easy YCSB point keeps WAF near 1.0 while exposing stale-secret reset gap |
| `ycsb_actual_zns_a_p4000_raw` | `artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc4000-z560-helper.json` | 31634 | `af9c9667f1a0` | raw actual-ZNS packed replay for YCSB-A p4000 pressure point | YCSB-A p4000 creates DOGI-style GC while hybrid drains secrets |
| `ycsb_actual_zns_a_p6000_raw` | `artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc6000-z712-helper.json` | 34976 | `f8f6e4fdafb0` | raw actual-ZNS packed replay for YCSB-A p6000 pressure point | YCSB-A p6000 strengthens the intermediate pressure curve |
| `ycsb_actual_zns_a_p8000_raw` | `artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc8000-z863-helper.json` | 33134 | `100bbb6db346` | raw actual-ZNS packed replay for YCSB-A p8000 pressure point | YCSB-A p8000 preserves stale-secret gap under higher PQC density |
| `ycsb_actual_zns_f_p4000_raw` | `artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc4000-z733-helper.json` | 32766 | `a7c9938d4ea7` | raw actual-ZNS packed replay for YCSB-F p4000 easy/stale-secret point | YCSB-F p4000 remains an easy WAF point but exposes stale-secret gap |
| `ycsb_actual_zns_f_p6000_raw` | `artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc6000-z733-helper.json` | 34924 | `30d917927795` | raw actual-ZNS packed replay for YCSB-F p6000 pressure point | YCSB-F p6000 captures the transition from easy WAF to pressure |
| `ycsb_actual_zns_f_p8000_raw` | `artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc8000-z733-helper.json` | 31665 | `a107b694ebf3` | raw actual-ZNS packed replay for YCSB-F p8000 pressure point | YCSB-F p8000 creates strong DOGI-style WAF/GC separation |
| `ycsb_actual_zns_a_p10000_raw` | `artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-a-pqc10000-z1024-helper.json` | 34941 | `5ce08c4851b2` | raw actual-ZNS packed replay for larger YCSB-A p10000 pressure point | YCSB-A p10000 confirms the realistic failure mode is stale-secret exposure plus moderate DOGI-style GC, not a toy WAF explosion |
| `ycsb_actual_zns_f_p10000_raw` | `artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc10000-z900-helper.json` | 35041 | `322531c09f4d` | raw actual-ZNS packed replay for larger YCSB-F p10000 pressure point | YCSB-F p10000 strengthens DOGI-axis pressure while QUASAR/hybrid keeps GC and stale secrets at zero |
| `sysbench_actual_zns_pressure` | `artifacts/results/fast-db-pressure/sysbench-pressure-summary.json` | 7872 | `fa0fe82fb863` | FAST-style DB pressure actual-ZNS replay summary | update-heavy PQC metadata pressure can create large DOGI-style GC copy cost |
| `dynamic_exchange_actual_zns_pressure` | `artifacts/results/fast-dynamic-pressure/dynamic-pressure-summary.json` | 12800 | `30435480f439` | DOGI dynamic-axis Exchange/Varmail/Alibaba pressure actual-ZNS replay summary | dynamic service workloads also expose DOGI-style GC and stale-secret cost under PQC pressure |
| `dynamic_exchange_actual_zns_raw` | `artifacts/results/fast-dynamic-pressure/packed-physical-zonefs-exchange-pqc8000-z768-helper.json` | 35237 | `d2faf27bd1c3` | raw actual-ZNS packed replay for Exchange p8000 dynamic pressure | Exchange p8000 creates DOGI/SepBIT/MiDAS GC while hybrid drains secrets |
| `dynamic_varmail_actual_zns_raw` | `artifacts/results/fast-dynamic-pressure/packed-physical-zonefs-varmail-pqc8000-z768-helper.json` | 35235 | `1097e724e2dc` | raw actual-ZNS packed replay for Varmail p8000 dynamic pressure | Varmail p8000 creates DOGI/SepBIT/MiDAS GC while hybrid drains secrets |
| `dynamic_alibaba_actual_zns_raw` | `artifacts/results/fast-dynamic-pressure/packed-physical-zonefs-alibaba-pqc8000-z768-helper.json` | 35267 | `c1b0d70291fd` | raw actual-ZNS packed replay for Alibaba p8000 dynamic pressure | Alibaba p8000 creates DOGI/SepBIT/MiDAS GC while hybrid drains secrets |
| `dogi_exact_alibaba_pressure` | `artifacts/results/dogi-exact/alibaba-pqc8000-dogi.json` | 499 | `39592d4f23d9` | exact public DOGI prototype run on physical ZNS with Alibaba p8000 compact trace | public DOGI binary completes on the hard dynamic PQC pressure trace and reports high GC/WAF |
| `dogi_exact_alibaba_suite` | `artifacts/results/dogi-exact/alibaba-pqc8000-suite.json` | 2064 | `f0b1425a00ee` | exact public DOGI prototype DOGI/Greedy/CostBenefit suite on physical ZNS | all public DOGI-family placements complete and report high WAF on the hard dynamic PQC pressure trace |
| `dogi_original_lba_adapter` | `artifacts/results/fast-dynamic-pressure/alibaba-pqc8000-original-lba-dogi-adapter.json` | 846 | `63938bb0eea1` | original-LBA DOGI adapter summary for Alibaba p8000 without compacting the LBA span | original-LBA DOGI replay requires a 42GiB logical span instead of the compact 2GiB span |
| `dogi_original_lba_preflight` | `artifacts/results/fast-dynamic-pressure/alibaba-pqc8000-original-lba-dogi-preflight-nvme0n1.json` | 6141 | `9e35230c38ee` | preflight for the original-LBA DOGI run on the physical ZNS device | the original-LBA trace is syntactically runnable by the DOGI prototype and the device/tool chain is visible |
| `dogi_original_lba_completed_run` | `artifacts/results/dogi-exact/alibaba-pqc8000-original-lba-dogi-cwd-app.json` | 527 | `dbfd67fcd497` | completed original-LBA public DOGI physical run summary | the original-LBA DOGI run completes when executed from the prototype app working directory, reporting WAF on the 42GiB Alibaba p8000 span |
| `ycsb_f_straggler_baselines` | `artifacts/results/fast-ycsb-pressure/packed-physical-zonefs-ycsb-f-pqc8000-straggler005-baselines-helper.json` | 23117 | `862b9ff20002` | actual-ZNS hard straggler replay for FIFO/SepBIT/MiDAS/DOGI baselines | history baselines issue no semantic resets under delayed-expiry stragglers |
| `actual_zns_overhead` | `artifacts/results/actual-zns-overhead-summary.json` | 39597 | `c4f59381973a` | actual-ZNS helper-path overhead plus C policy CPU accounting | hybrid pays reset work but policy-decision CPU remains below DOGI-style MLP |
| `xnvme_zns_latency` | `artifacts/results/xnvme-zns-latency/summary.json` | 809 | `cf22d6dac2de` | raw xNVMe/Linux NVMe ioctl ZNS append/reset latency probe | native xNVMe command-path p99 is measured without zonefs helper append overhead |
| `xnvme_zns_latency_source` | `code/quasar/xnvme_zns_latency.c` | 5671 | `0fc74b8d7bb9` | source for the xNVMe native ZNS latency probe | xNVMe replay evidence is backed by an inspectable in-tree tool |
| `physical_zns_security_capability` | `artifacts/results/physical-zns-security-capability.json` | 1083 | `ec57ce25b9bc` | physical ZNS sanitize/security capability and claim-boundary summary | the evaluated device supports sanitize and records whether crypto-erase execution was validated |
| `physical_zns_sanitize_execution` | `artifacts/results/physical-zns-sanitize-exec/summary.json` | 1180 | `81f36dd378cd` | destructive NVMe crypto-erase sanitize execution summary for the physical ZNS SSD | the device crypto-erase sanitize command path completed successfully and zonefs was restored |
| `workload_hardness` | `artifacts/results/workload-hardness-matrix.json` | 13129 | `778373eaa330` | benchmark guardrail for fairness, negative-control, pressure, and hostile tiers | evaluation does not rely on an overly easy PQC-only trace |
| `deployment_selector` | `artifacts/results/quasar-deployment-policy-selector.json` | 3363 | `5effb3c19a59` | deployable policy selector for default, tenant-isolation, strict-residual, and fallback modes | QUASAR improvement is an explicit mode selector, not one universal knob |
| `fdp_handle_pressure` | `artifacts/results/pqc-mixed-fdp-mapping.json` | 91046 | `2c5d3ef64630` | trace-driven QUASAR-to-FDP placement-handle pressure model | FDP can carry QUASAR lifecycle families, but scarce handles collide death cohorts |
| `fdp_handle_pressure_figure` | `artifacts/figures/fast-style/fig8-fdp-handle-pressure.pdf` | 13196 | `7ca6986bd95b` | paper Figure 8 for FDP handle-count purity and collision pressure | FDP handle pressure is reported as deployment modeling, not physical FDP performance |
| `unified_comparison` | `artifacts/results/unified-baseline-comparison.json` | 182750 | `bce11cb4bd54` | single JSON summary separating same-path, pressure, exact external, and boundary evidence | paper-ready comparison summary |
| `claim_matrix` | `artifacts/results/quasar-claim-matrix.json` | 8168 | `f29341185c85` | claim-to-evidence guardrail | supported, qualified, and boundary claims are separated |
| `external_readiness` | `artifacts/results/external-readiness.json` | 33770 | `3e06aae19557` | conservative readiness report for external/system evidence | no current blockers or pending paper-grade evidence gaps for scoped claim |
| `goal_completion_audit` | `artifacts/results/actual-zns-goal-completion-audit.json` | 6484 | `56054ce06ec5` | requirement-by-requirement audit of the actual-ZNS comparison goal | scoped claim is ready while optional strengthening work is separated |
| `acceptance` | `artifacts/results/acceptance-report.json` | 38756 | `84a20e866e51` | local acceptance gate summary | all reproducibility and evidence gates pass |
| `ycsb_pressure_figure` | `artifacts/figures/actual-zns/ycsb-pressure-waf-stale.png` | 100733 | `98973b42e75f` | paper figure for actual-ZNS YCSB WAF/stale-secret curve | visualizes negative control and pressure rows |
| `overhead_figure` | `artifacts/figures/actual-zns/overhead-accounting.png` | 64105 | `d7a58350fd01` | paper figure for actual-ZNS overhead accounting | visualizes throughput, CPU, and semantic reset cost |
| `workload_hardness_figure` | `artifacts/figures/actual-zns/workload-hardness.png` | 55961 | `e49e3cced335` | paper figure for workload hardness tiers | visualizes fairness, pressure, and hostile coverage |

## Regeneration Commands

| Step | Command |
| --- | --- |
| `actual_zns_summary_pipeline` | `python3 code/sim/run_actual_zns_summary_pipeline.py` |
| `workload_hardness` | `python3 code/sim/report_fast_dynamic_pressure.py && python3 code/sim/report_workload_hardness_matrix.py` |
| `deployment_selector` | `python3 code/sim/report_deployment_policy_selector.py` |
| `actual_zns_figures` | `python3 code/sim/plot_actual_zns_comparison.py` |
| `fdp_mapping` | `python3 code/quasar/fdp_mapping.py --trace artifacts/traces/pqc-mixed.jsonl --handles 8 16 32 64 128 --out artifacts/results/pqc-mixed-fdp-mapping.json --markdown-out artifacts/results/pqc-mixed-fdp-mapping.md` |
| `fast_style_figures` | `python3 code/sim/plot_fast_style_quasar_figures.py` |
| `unified_report` | `python3 code/sim/report_unified_comparison.py` |
| `claim_matrix` | `python3 code/sim/report_claim_matrix.py && python3 code/sim/report_unified_comparison.py` |
| `external_readiness` | `python3 code/baselines/external_readiness.py` |
| `goal_completion_audit` | `python3 code/sim/report_goal_completion_audit.py` |
| `acceptance` | `python3 code/sim/acceptance_check.py` |
| `unit_tests` | `python3 -m unittest discover -s code -p 'test*.py'` |

## Readiness Snapshot

```json
{
  "acceptance": {
    "passed": true,
    "passed_gates": 41,
    "total_gates": 41
  },
  "actual_zns_overhead": {},
  "claim_matrix": {
    "by_status": {
      "qualified": 1,
      "supported": 10,
      "supported-boundary": 1
    },
    "claim_count": 12
  },
  "deployment_selector": {
    "passed": true,
    "passed_modes": 4,
    "total_modes": 4
  },
  "dogi_exact_alibaba_pressure": {},
  "dogi_exact_alibaba_suite": {},
  "dogi_original_lba_adapter": {},
  "dogi_original_lba_completed_run": {},
  "dogi_original_lba_preflight": {},
  "dynamic_alibaba_actual_zns_raw": {},
  "dynamic_exchange_actual_zns_pressure": {},
  "dynamic_exchange_actual_zns_raw": {},
  "dynamic_varmail_actual_zns_raw": {},
  "external_readiness": {
    "blockers": [],
    "paper_ready_external": true,
    "pending": []
  },
  "fdp_handle_pressure": {},
  "goal_completion_audit": {},
  "physical_zns_sanitize_execution": {},
  "physical_zns_security_capability": {},
  "same_path_actual_zns_fairness": {},
  "sysbench_actual_zns_pressure": {},
  "unified_comparison": {},
  "workload_hardness": {
    "passed": true
  },
  "xnvme_zns_latency": {},
  "ycsb_actual_zns_a_p10000_raw": {},
  "ycsb_actual_zns_a_p4000_raw": {},
  "ycsb_actual_zns_a_p6000_raw": {},
  "ycsb_actual_zns_a_p8000_raw": {},
  "ycsb_actual_zns_f_p10000_raw": {},
  "ycsb_actual_zns_f_p4000_raw": {},
  "ycsb_actual_zns_f_p6000_raw": {},
  "ycsb_actual_zns_f_p8000_raw": {},
  "ycsb_actual_zns_p2000_raw": {},
  "ycsb_actual_zns_pressure_curve": {},
  "ycsb_f_straggler_baselines": {}
}
```
