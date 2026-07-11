# PQC Trace Generator

Generate synthetic PQC object-lifecycle traces:

```bash
python3 code/tracegen/pqc_tracegen.py \
  --events 80000 \
  --jsonl artifacts/traces/pqc-mixed.jsonl \
  --dogi-trace artifacts/traces/pqc-mixed.dogi \
  --dogi-delete-markers
```

Generate the named workload suite used by the plan:

```bash
python3 code/tracegen/generate_workload_suite.py \
  --events 15000 \
  --out-dir artifacts/traces/workloads \
  --seed 21
```

Convert an OQS/OpenSSL-style event log into the rich QUASAR trace schema:

```bash
python3 code/tracegen/oqs_tls_trace.py \
  --event-log code/tracegen/sample_oqs_events.jsonl \
  --jsonl artifacts/traces/oqs-sample.jsonl \
  --dogi-trace artifacts/traces/oqs-sample.dogi \
  --dogi-delete-markers \
  --summary-out artifacts/results/oqs-sample-summary.json \
  --probe-out artifacts/results/openssl-pqc-capability.json \
  --epoch-len-ms 1000 \
  --rotation-epochs 4
```

The event log can be JSONL or CSV. Expected columns/fields are:

```text
ts,event,session_id,tenant_id,kem,sig,payload_bytes,session_end_ts
```

The local OpenSSL probe is recorded separately so the results can say whether a
real oqsprovider/OpenSSL PQC stack was available on the test machine.

Generate a trace by executing real liboqs KEM/signature operations:

```bash
python3 code/tracegen/liboqs_workload.py \
  --sessions 200 \
  --kem ML-KEM-768 \
  --sig ML-DSA-65 \
  --event-log artifacts/traces/liboqs-events.jsonl \
  --jsonl artifacts/traces/liboqs-pqc.jsonl \
  --dogi-trace artifacts/traces/liboqs-pqc.dogi \
  --summary-out artifacts/results/liboqs-pqc-summary.json \
  --epoch-len-ms 1000 \
  --rotation-epochs 12 \
  --seed 17
```

This path validates that KEM encapsulation/decapsulation and signature
sign/verify succeed before converting the measured events into the QUASAR trace
schema.

Generate a trace through OpenSSL 3 + oqsprovider:

```bash
python3 code/tracegen/openssl_oqsprovider_workload.py \
  --sessions 60 \
  --openssl-bin /usr/bin/openssl \
  --provider-module-path artifacts/external/oqs-provider/_build-local/lib \
  --kem-alg mlkem768 \
  --sig-alg mldsa65 \
  --event-log artifacts/traces/openssl-oqsprovider/events.jsonl \
  --jsonl artifacts/traces/openssl-oqsprovider/trace.jsonl \
  --dogi-trace artifacts/traces/openssl-oqsprovider/trace.dogi \
  --summary-out artifacts/results/openssl-oqsprovider/summary.json
```

This path loads the local oqsprovider module through OpenSSL's provider
interface, performs provider-backed ML-KEM key generation/public export and
ML-DSA signing/verification, then converts the measured event log into the
QUASAR trace schema. In the current OpenSSL 3.0.2 CLI setup, KEM encap/decap is
not exposed through `pkeyutl`, so this is a provider-backed sanity trace rather
than a full TLS/KEM service trace.

Generate a stronger OpenSSL oqsprovider trace through the C EVP KEM API:

```bash
python3 code/tracegen/openssl_oqsprovider_service_trace.py \
  --sessions 120 \
  --provider-module-path artifacts/external/oqs-provider/_build-local/lib \
  --kem-alg mlkem768 \
  --sig-alg mldsa65 \
  --event-log artifacts/traces/openssl-oqsprovider-kem-service/events.jsonl \
  --jsonl artifacts/traces/openssl-oqsprovider-kem-service/trace.jsonl \
  --dogi-trace artifacts/traces/openssl-oqsprovider-kem-service/trace.dogi \
  --summary-out artifacts/results/openssl-oqsprovider-kem-service/summary.json
```

This wrapper compiles `openssl_oqs_kem_sig_probe.c`, loads oqsprovider, and uses
`EVP_PKEY_encapsulate`/`EVP_PKEY_decapsulate` directly. It is still not a full
TLS server trace, but it does measure provider-backed ML-KEM encap/decap and
ML-DSA sign/verify through OpenSSL's C API.

Generate a socket-level OpenSSL oqsprovider TLS trace:

```bash
python3 code/tracegen/openssl_oqsprovider_tls_socket_trace.py \
  --sessions 60 \
  --openssl-bin /usr/bin/openssl \
  --provider-module-path artifacts/external/oqs-provider/_build-local/lib \
  --group mlkem768 \
  --cert artifacts/external/oqs-provider/test/servercert.pem \
  --key artifacts/external/oqs-provider/test/serverkey.pem \
  --event-log artifacts/traces/openssl-oqsprovider-tls-socket/events.jsonl \
  --jsonl artifacts/traces/openssl-oqsprovider-tls-socket/trace.jsonl \
  --dogi-trace artifacts/traces/openssl-oqsprovider-tls-socket/trace.dogi \
  --summary-out artifacts/results/openssl-oqsprovider-tls-socket/summary.json \
  --raw-out artifacts/results/openssl-oqsprovider-tls-socket/raw.json
```

This wrapper starts `s_server` and repeatedly runs `s_client` with oqsprovider
loaded and `mlkem768` forced as the TLS 1.3 KEM group. The bundled oqsprovider
test certificate is RSA, so this trace validates the PQC KEM path and TLS
socket boundary, not a PQC certificate chain.

The JSONL trace keeps `intent`, `epoch_id`, and `expire_ts`. The DOGI trace keeps only write-like records in DOGI's prototype input shape:

```text
<timestamp> 1 <lba_4k> <length_bytes>
```

Because DOGI's prototype invalidates old data on overwrite, `--dogi-delete-markers` emits a one-block tombstone write at object expiry. This is an approximation for feeding PQC expiry into a write-only block trace.

Generate a DOGI/FIO-grounded mixed trace by overlaying PQC metadata on DOGI's
public FIO trace format:

```bash
python3 code/tracegen/dogi_fio_overlay.py \
  --dogi-trace artifacts/traces/dogi-fio/test-fio-small-range120m-132m \
  --jsonl artifacts/traces/dogi-fio/fio-prefix-pqc0500.jsonl \
  --summary-out artifacts/results/dogi-fio-pqc0500-summary.json \
  --max-fio-writes 200000 \
  --prefill-working-set \
  --pqc-ratio 0.05 \
  --epoch-len 10000 \
  --seed 23
```

This converter preserves the DOGI/FIO overwrite stream as `PAYLOAD`, emits a
measured prefill working set, and injects PQC lifecycle writes as
`KEM_ARTIFACT`, `EPHEMERAL_SECRET`, `SIGNATURE_LOG`, and `CERT_METADATA`.
Use it to check that QUASAR does not claim unrealistic wins on ordinary FIO:
`quasar-dogi-hybrid` should match DOGI-style behavior at 0% PQC and improve
only as PQC metadata becomes nontrivial or security-critical.

Generate a DOGI-paper-shaped coverage suite for the workload axes in the DOGI
FAST paper:

```bash
python3 code/tracegen/generate_dogi_paper_workloads.py \
  --events 50000 \
  --ratios 0,0.05,0.20 \
  --out-dir artifacts/traces/dogi-paper-workloads-quick \
  --summary-dir artifacts/results/dogi-paper-workloads-quick/summaries \
  --seed 43
```

This suite covers FIO Zipf, YCSB-A, YCSB-F, Varmail, Alibaba, and Exchange
shapes. The public DOGI/MiDAS artifacts expose FIO directly; the other paper
traces are represented as category-matched synthetic traces rather than claimed
as exact reproductions.
