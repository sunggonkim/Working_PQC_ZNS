# Working_PQC_ZNS

Working repository for a new ZNS storage research direction centered on post-quantum cryptography (PQC) workloads.

## Direction

The current working concept is **QUASAR**: QUantum-safe Append-only Storage ARchitecture for ZNS.

QUASAR targets the mismatch between state-of-the-art ZNS data placement algorithms and PQC workload behavior. Instead of predicting data lifetime from age, access history, or LBA-level features, QUASAR exposes cryptographic intent and epoch metadata from the PQC software stack to the ZNS allocator.

## Core Ideas

- Cryptographic intent-aware zone allocation
- Epoch-based zero-GC reclaim
- Shorter stale-secret exposure windows through epoch-aligned reset eligibility
- Optional hardware crypto-erase or sanitize integration when the device provides those semantics
- Evaluation against FIFO ZNS, SepBIT, MiDAS, and DOGI-style placement

## Repository Layout

- `artifacts/`: generated figures, traces, and experiment artifacts
- `build/`: local build directory
- `code/`: prototype implementation and experiments
- `Paper/`: paper drafts and submission materials
- `HowToWritePaper.md`: working research and writing notes
- `plan.md`: single source of truth for QUASAR design, experiments, and implementation status

## Reproduce Current Results

Run the current acceptance check:

```bash
python3 code/run_pipeline.py --only acceptance
```

Regenerate the full non-destructive artifact set:

```bash
python3 code/run_pipeline.py
```

The full pipeline generates synthetic traces, a real-liboqs trace, simulator
results, DOGI adapter/preflight artifacts, QUASAR dry-run and file-backed ZNS
replay artifacts, existing external DOGI run summaries, figures, crash-model
results, the final acceptance report, and paper-facing result tables.

Current acceptance status:

```text
13/13 gates passed
```

If the host has no physical ZNS device, generate the root-only setup plan for a
virtual zoned null_blk target:

```bash
python3 code/quasar/nullblk_zoned.py --action plan --name nullb_quasar
```

When `/dev/nullb_quasar` is available, the guarded real zoned-block replay path
is:

```bash
sudo python3 code/quasar/replay.py \
  --trace artifacts/traces/pqc-mixed.jsonl \
  --backend blkzone-zns \
  --device /dev/nullb_quasar \
  --execute \
  --emulator-state artifacts/results/pqc-mixed-nullblk-state.json \
  --summary-out artifacts/results/pqc-mixed-nullblk-summary.json
```

For the external DOGI prototype, use a memory-backed null_blk target. ZenFS must
read back its superblock after format, so a `memory_backed=0` null_blk device is
not sufficient for DOGI even though it is enough for append/reset smoke tests.
The current external DOGI full-trace artifact is:

```text
artifacts/results/dogi-nullblk-full-run.json
```

It records `UserWrite=2.500 GiB`, `GCWrite=1.702 GiB`, and `WAF=1.681` on the
PQC-adapted DOGI trace.

Run unit tests:

```bash
python3 -m unittest discover -s code -p 'test_*.py'
```
