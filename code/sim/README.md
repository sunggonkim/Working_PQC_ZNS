# PQC/ZNS Verification Simulator

Run a fast pre-check before building the full DOGI/NVMeVirt stack:

```bash
python3 code/sim/zns_pqc_verify.py \
  --trace artifacts/traces/pqc-mixed.jsonl \
  --zones 1100 \
  --zone-capacity 512 \
  --min-free-zones 12 \
  --policies fifo sepbit-style dogi-history quasar quasar-dogi-hybrid epoch-oracle \
  --out artifacts/results/pqc-mixed-verification.json
```

Policies:

- `fifo`: plain append-only ZNS placement.
- `sepbit-style`: invalidation-density grouping from storage-visible LBA history.
- `midas-style`: age/frequency grouping from storage-visible LBA history.
- `dogi-history`: DOGI-style storage-visible lifetime grouping using the six runtime features seen in the DOGI snapshot: LBA, frequency bits, frequency-bit count, interval bucket, segment access count, and previous LBA.
- `quasar`: intent/epoch-aware grouping for PQC death cohorts.
- `quasar-dogi-hybrid`: realistic QUASAR deployment model; PQC lifecycle data uses QUASAR zone families while ordinary payload falls back to `dogi-history`.
- `epoch-oracle`: an upper-bound policy that sees expiry lifetime at write time.

QUASAR-specific controls:

```bash
--quasar-min-epoch-fill 0.40
--quasar-bin-width 4
--quasar-open-zone-budget 64
--quasar-residual-fraction 0.0
--hint-missing-rate 0.05
--wrong-epoch-rate 0.05
--straggler-rate 0.05
```

Run the first experiment bundle:

```bash
python3 code/sim/run_quasar_experiments.py \
  --trace artifacts/traces/pqc-mixed.jsonl \
  --zones 1100 \
  --zone-capacity 512 \
  --min-free-zones 12
```

Generate the workload-suite results and first figures:

```bash
python3 code/tracegen/generate_workload_suite.py \
  --events 15000 \
  --out-dir artifacts/traces/workloads \
  --seed 21

python3 code/sim/run_workload_suite.py \
  --trace-dir artifacts/traces/workloads \
  --auto-zones \
  --auto-op-ratio 0.02 \
  --zone-capacity 512 \
  --min-free-zones 8 \
  --out artifacts/results/e1-workloads.json

python3 code/sim/plot_quasar_results.py \
  --e0 artifacts/results/schema-test-runner/e0-sanity.json \
  --e1 artifacts/results/e1-workloads.json \
  --e2 artifacts/results/schema-test-runner/e2-waf-vs-utilization.json \
  --e5 artifacts/results/schema-test-runner/e5-bad-hints.json \
  --out-dir artifacts/figures
```

Generate the E4 exposure-window timeline:

```bash
python3 code/sim/exposure_timeline.py \
  --trace artifacts/traces/workloads/stress-rekey.jsonl \
  --zones 149 \
  --zone-capacity 512 \
  --min-free-zones 8 \
  --policies fifo dogi-history quasar \
  --sample-interval 500 \
  --out artifacts/results/e4-exposure-timeline.json \
  --figure artifacts/figures/e4-exposure-timeline.png
```

Run the DOGI-paper-shaped PQC ratio sweep plotter after generating
`artifacts/results/dogi-paper-ratio-sweep-50k/summary.json` and `eval.json`:

```bash
python3 code/sim/plot_ratio_sweep.py \
  --summary artifacts/results/dogi-paper-ratio-sweep-50k/summary.json \
  --eval artifacts/results/dogi-paper-ratio-sweep-50k/eval.json \
  --main-figure artifacts/figures/dogi-paper-ratio-sweep-50k/ratio-sweep-main.png \
  --space-figure artifacts/figures/dogi-paper-ratio-sweep-50k/ratio-sweep-space.png
```

Run a smaller multi-seed ratio sweep with mean and 95% CI summaries:

```bash
python3 code/sim/run_ratio_seed_sweep.py \
  --json-out artifacts/results/dogi-paper-seed-sweep/summary.json \
  --markdown-out artifacts/results/dogi-paper-seed-sweep/summary.md
```

Generate and evaluate the real-liboqs profile suite:

```bash
python3 code/sim/run_liboqs_profile_suite.py
```

Generate and evaluate a real-liboqs PQC ratio sweep:

```bash
python3 code/sim/run_liboqs_ratio_sweep.py

python3 code/sim/plot_ratio_sweep.py \
  --summary artifacts/results/liboqs-ratio-sweep/ratio-summary.json \
  --eval artifacts/results/liboqs-ratio-sweep/eval.json \
  --main-figure artifacts/figures/liboqs-ratio-sweep/ratio-sweep-main.png \
  --space-figure artifacts/figures/liboqs-ratio-sweep/ratio-sweep-space.png
```

Generate and evaluate a larger real-liboqs KMS/update stress suite:

```bash
python3 code/sim/run_liboqs_kms_stress.py
```

This creates KMS burst, tenant-churn, and dense-rotation traces that execute
real `ML-KEM-768` and `ML-DSA-65` operations, then evaluates placement under
multiple over-provisioning ratios.

Generate the full 50k DOGI-shaped exposure timeline after the ratio sweep:

```bash
python3 code/sim/exposure_timeline.py \
  --trace artifacts/traces/dogi-paper-ratio-sweep-50k/exchange-pqc2000.jsonl \
  --zones 193 \
  --zone-capacity 512 \
  --min-free-zones 8 \
  --policies fifo dogi-history midas-style quasar-dogi-hybrid \
  --sample-interval 500 \
  --sample-on-expire \
  --out artifacts/results/dogi-paper-ratio-sweep-50k/exposure-exchange-pqc2000.json \
  --figure artifacts/figures/dogi-paper-ratio-sweep-50k/exposure-exchange-pqc2000.png
```

Run the full QUASAR-DOGI space sensitivity sweep:

```bash
python3 code/sim/run_quasar_space_sensitivity.py \
  --json-out artifacts/results/dogi-paper-workloads-smoke/space-sensitivity-full.json \
  --markdown-out artifacts/results/dogi-paper-workloads-smoke/space-sensitivity-full.md \
  --figure artifacts/figures/dogi-paper-workloads-smoke/space-sensitivity-full.png
```

Run a tighter open-zone-budget stress sweep:

```bash
python3 code/sim/run_quasar_space_sensitivity.py \
  --open-zone-budget-values 1 2 4 8 \
  --bin-width-values 1 2 4 8 \
  --min-epoch-fill-values 0.0 0.25 0.5 \
  --json-out artifacts/results/dogi-paper-workloads-smoke/space-sensitivity-tight-open.json \
  --markdown-out artifacts/results/dogi-paper-workloads-smoke/space-sensitivity-tight-open.md \
  --figure artifacts/figures/dogi-paper-workloads-smoke/space-sensitivity-tight-open.png
```

Run an adversarial many-tenant/tiny-epoch open-zone stress test:

```bash
python3 code/sim/run_open_zone_stress.py
```

This generates:

- `artifacts/traces/open-zone-stress/adversarial.jsonl`
- `artifacts/results/open-zone-stress/summary.md`
- `artifacts/results/open-zone-stress/summary.json`
- `artifacts/figures/open-zone-stress/summary.png`

Run the adaptive admission controller comparison:

```bash
python3 code/sim/run_adaptive_admission.py
```

This compares DOGI, fixed priority placement, fixed strict coarse binning, and
`quasar-adaptive-hybrid` on the adversarial open-zone trace.

Run the multi-seed adaptive threshold sweep:

```bash
python3 code/sim/run_adaptive_threshold_sweep.py
```

This is a variance check across seeds, zone sizes, exact-admission thresholds,
family-pressure thresholds, and tenant-bin widths.

Measure Python prototype policy-decision overhead:

```bash
python3 code/sim/measure_policy_overhead.py \
  --traces \
    artifacts/traces/liboqs-profiles/traces/kms-rotation.jsonl \
    artifacts/traces/liboqs-profiles/traces/mixed-service.jsonl \
    artifacts/traces/dogi-paper-workloads-smoke/exchange-pqc2000.jsonl \
  --policies dogi-history quasar quasar-dogi-hybrid \
  --repeats 5 \
  --out artifacts/results/policy-overhead.json \
  --markdown-out artifacts/results/policy-overhead.md
```

Measure C-level policy-decision overhead:

```bash
python3 code/sim/run_c_policy_overhead.py \
  --skip-missing \
  --repeats 9 \
  --out artifacts/results/c-policy-overhead.json \
  --markdown-out artifacts/results/c-policy-overhead.md
```

This compiles `code/sim/c_policy_overhead.c` and measures DOGI-style
feature+MLP inference, QUASAR hint routing, and QUASAR-DOGI hybrid routing.
It is still a decision-path benchmark, not a full physical-device CPU profile.

Run the DOGI/FIO-grounded sanity check after generating overlay traces with
`code/tracegen/dogi_fio_overlay.py`:

```bash
python3 code/sim/zns_pqc_verify.py \
  --trace artifacts/traces/dogi-fio/fio-prefix-pqc0500.jsonl \
  --zones 220 \
  --zone-capacity 512 \
  --min-free-zones 8 \
  --policies fifo sepbit-style midas-style dogi-history quasar quasar-dogi-hybrid epoch-oracle \
  --out artifacts/results/dogi-fio-pqc0500-z220-verification.json
```

Main QUASAR runs use `--quasar-residual-fraction 0.0`: reset only fully expired
epoch zones. Use a positive residual fraction as an ablation for imperfect
hints/stragglers, because residual migration can inflate WAF.

Run the DOGI-paper-shaped sensitivity checks on a representative D-type trace:

```bash
python3 code/sim/run_dogi_sensitivity.py \
  --json-out artifacts/results/dogi-paper-workloads-quick/sensitivity-summary.json \
  --markdown-out artifacts/results/dogi-paper-workloads-quick/sensitivity-summary.md
```

Run the cross-workload hint robustness suite:

```bash
python3 code/sim/run_robustness_suite.py \
  --json-out artifacts/results/robustness-suite/summary.json \
  --markdown-out artifacts/results/robustness-suite/summary.md
```

The default suite covers DOGI-shaped FIO, Varmail, YCSB-F, and the real-liboqs
KMS rotation profile. It reports clean QUASAR-DOGI behavior plus missing-hint,
wrong-epoch, and straggler perturbations.

Check the paper-readiness acceptance gates:

```bash
python3 code/sim/acceptance_check.py \
  --out artifacts/results/acceptance-report.json
```

Generate paper-facing result tables:

```bash
python3 code/sim/report_results.py \
  --json-out artifacts/results/quasar-results-summary.json \
  --markdown-out artifacts/results/quasar-results-summary.md
```

Run simulator tests:

```bash
python3 -m unittest discover -s code -p 'test_*.py'
```

This simulator is for hypothesis testing and figure generation. It does not replace the full DOGI prototype.
