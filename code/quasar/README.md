# QUASAR Replay Scaffold

Build a dry-run ZNS/FDP replay plan from a rich QUASAR JSONL trace:

```bash
python3 code/quasar/replay.py \
  --trace artifacts/traces/pqc-mixed.jsonl \
  --backend dry-run \
  --plan-out artifacts/results/pqc-mixed-replay-plan.json \
  --summary-out artifacts/results/pqc-mixed-replay-summary.json \
  --min-epoch-fill-blocks 1
```

Backends:

- `dry-run`: always available; creates append/reset-family commands without touching a device.
- `file-zns`: executes append/reset-family commands against a JSON-backed ZNS emulator.
- `blkzone-zns`: executes sequential writes and zone resets on a real zoned block device using `blkzone`; guarded to `/dev/nullb*` unless `--allow-non-nullblk-device` is passed.
- `nvme-zns`: checks for the `nvme` CLI and requires `--device` for future execution.
- `xnvme`: checks for `xnvme`.
- `spdk`: checks for `spdk_nvme_perf`.

Real-device execution is intentionally guarded. Use the dry-run plan first,
then bind a backend-specific executor only when the target device and reset
semantics are verified.

Run the file-backed ZNS emulator:

```bash
python3 code/quasar/replay.py \
  --trace artifacts/traces/pqc-mixed.jsonl \
  --backend file-zns \
  --execute \
  --zone-capacity 512 \
  --emulator-zones 1400 \
  --emulator-state artifacts/results/pqc-mixed-file-zns-state.json \
  --plan-out artifacts/results/pqc-mixed-file-zns-plan.json \
  --summary-out artifacts/results/pqc-mixed-file-zns-summary.json \
  --min-epoch-fill-blocks 1
```

Run the replay-level latency/throughput suite on representative traces:

```bash
python3 code/quasar/run_replay_latency_suite.py
```

This writes:

- `artifacts/results/replay-latency/summary.md`
- `artifacts/results/replay-latency/summary.json`
- per-trace `*-file-zns-summary.json` and `*-file-zns-state.json`

These are file-ZNS emulator numbers. They measure replay-path CPU/emulator
latency and throughput; physical SSD append/reset latency still requires the
guarded `blkzone-zns` path or a real SPDK/xNVMe backend.

Check whether the host has a usable ZNS target:

```bash
python3 code/quasar/zns_preflight.py \
  --out artifacts/results/zns-preflight.json
```

Pass `--device /dev/<zns-device>` to check one device. The preflight is
read-only and does not reset or write to any block device.

Prepare a virtual zoned null_blk target when no physical ZNS SSD is available:

```bash
python3 code/quasar/nullblk_zoned.py \
  --action plan \
  --name nullb_quasar \
  --size-mib 4096 \
  --zone-size-mib 64 \
  --zone-capacity-mib 64 \
  --zone-max-open 128
```

The `plan` action is read-only and prints the root commands. The `create` and
`destroy` actions intentionally require root because they write to configfs.
After creating the target, rerun:

```bash
python3 code/quasar/zns_preflight.py \
  --device /dev/nullb_quasar \
  --out artifacts/results/zns-preflight-nullblk.json
```

Then run a guarded real zoned-block replay:

```bash
sudo python3 code/quasar/replay.py \
  --trace artifacts/traces/pqc-mixed.jsonl \
  --backend blkzone-zns \
  --device /dev/nullb_quasar \
  --execute \
  --emulator-state artifacts/results/pqc-mixed-nullblk-state.json \
  --summary-out artifacts/results/pqc-mixed-nullblk-summary.json \
  --min-epoch-fill-blocks 1
```

Run the crash-consistency safety model:

```bash
python3 code/quasar/crash_model.py \
  --trace artifacts/traces/pqc-mixed.jsonl \
  --out artifacts/results/pqc-mixed-crash-model.json \
  --markdown-out artifacts/results/pqc-mixed-crash-model.md
```

The model checks the crash points from `plan.md` and fails if recovery would
attempt an unsafe reset or lose live objects.

Run the FDP placement-handle mapping model:

```bash
python3 code/quasar/fdp_mapping.py \
  --trace artifacts/traces/pqc-mixed.jsonl \
  --handles 8 16 32 64 128 \
  --out artifacts/results/pqc-mixed-fdp-mapping.json \
  --markdown-out artifacts/results/pqc-mixed-fdp-mapping.md
```

This maps QUASAR zone families to a fixed number of FDP placement handles and
reports family/intent purity plus handle collision pressure. It is a deployment
model, not a physical FDP measurement.
