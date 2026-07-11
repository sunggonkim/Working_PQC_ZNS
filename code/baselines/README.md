# Baseline Integration Tools

Convert a rich QUASAR JSONL trace into the public DOGI prototype input format:

```bash
python3 code/baselines/dogi_trace_adapter.py \
  --jsonl artifacts/traces/pqc-mixed.jsonl \
  --dogi-trace artifacts/traces/pqc-mixed-adapted.dogi \
  --delete-markers \
  --summary-out artifacts/results/pqc-mixed-dogi-adapter.json
```

The summary includes the `prototype/app/global.cc` values needed by DOGI:

```text
wk_name
LogicalSizeGb
kZnsDevicePath
kZbdDeviceName
```

Expiry is approximated with one 4 KiB tombstone overwrite at the expired
object's LBA because DOGI's prototype trace parser is write-only.

Fetch the external DOGI repository used for preflight checks:

```bash
python3 code/baselines/fetch_dogi.py \
  --repo artifacts/external/DOGI \
  --summary-out artifacts/results/dogi-fetch.json
```

Check a cloned DOGI repository before a full run:

```bash
python3 code/baselines/dogi_preflight.py \
  --dogi-repo artifacts/external/DOGI \
  --trace artifacts/traces/pqc-mixed-adapted.dogi \
  --summary-out artifacts/results/dogi-preflight.json
```

Pass `--device /dev/<zns-device>` only when a real or emulated ZNS target is
ready. The preflight is read-only; it does not patch DOGI or reset devices.

Check the external MiDAS artifact before attempting an exact run:

```bash
python3 code/baselines/midas_preflight.py \
  --repo artifacts/external/MiDAS \
  --trace artifacts/traces/pqc-mixed-adapted.dogi \
  --out artifacts/results/midas-preflight.json
```

Parse an external MiDAS memory-backed prototype run:

```bash
python3 code/baselines/midas_run_summary.py \
  --log artifacts/results/midas-exact/pqc-pressure-1g.log \
  --returncode-file artifacts/results/midas-exact/pqc-pressure-1g.rc \
  --trace artifacts/traces/midas-exact/pqc-pressure-1g-adapted.dogi \
  --adapter-summary artifacts/results/midas-exact/pqc-pressure-1g-adapter.json \
  --build-gigaunit 1L \
  --pps 128 \
  --out artifacts/results/midas-exact/pqc-pressure-1g.json
```

The current local MiDAS exact path uses the artifact's memory-backed
`posix_memory` target. It is an exact prototype smoke/pressure run, but its
traffic units are MiDAS internal counters, so compare them carefully with
QUASAR simulator block counters.

Convert a QUASAR JSONL trace for the external SepBIT `trace_replay` simulator:

```bash
python3 code/baselines/sepbit_trace_adapter.py \
  --jsonl artifacts/traces/midas-exact/pqc-pressure-1g.jsonl \
  --trace-out artifacts/traces/sepbit-exact/pqc-pressure-1g.csv \
  --group-out artifacts/traces/sepbit-exact/pqc-pressure-1g.group \
  --property-out artifacts/traces/sepbit-exact/pqc-pressure-1g.property \
  --summary-out artifacts/results/sepbit-exact/pqc-pressure-1g-adapter.json \
  --log-id pqc \
  --delete-markers
```

Parse a SepBIT `trace_replay` log:

```bash
python3 code/baselines/sepbit_run_summary.py \
  --log artifacts/results/sepbit-exact/pqc-pressure-1g-sepbit.log \
  --returncode-file artifacts/results/sepbit-exact/pqc-pressure-1g-sepbit.rc \
  --adapter-summary artifacts/results/sepbit-exact/pqc-pressure-1g-adapter.json \
  --method SepBIT \
  --selection Greedy \
  --out artifacts/results/sepbit-exact/pqc-pressure-1g-sepbit.json
```

The current SepBIT exact path uses the public `fallfish/sepbit`
`trace_replay` simulator. It is separate from the compact `sepbit-style`
baseline in `zns_pqc_verify.py`.

Generate the conservative external-readiness report used by `plan.md`:

```bash
python3 code/baselines/external_readiness.py \
  --out artifacts/results/external-readiness.json \
  --markdown-out artifacts/results/external-readiness.md
```

This report can pass local simulator acceptance while still marking
production-like OpenSSL service capture, physical ZNS/FDP replay, or exact
baseline runs as pending.
