#!/usr/bin/env python3
"""Generate QUASAR traces by executing real liboqs KEM/signature operations."""

from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    import oqs
except Exception as exc:  # pragma: no cover - exercised only when liboqs is absent
    oqs = None
    OQS_IMPORT_ERROR = exc
else:
    OQS_IMPORT_ERROR = None

try:
    import oqs_tls_trace as bridge
except ModuleNotFoundError:  # pragma: no cover - used by root-level imports
    from tracegen import oqs_tls_trace as bridge


@dataclass
class MeasuredEvent:
    ts: int
    event: str
    session_id: str
    tenant_id: str
    kem: str
    sig: str
    payload_bytes: int
    session_end_ts: int
    kem_public_key_bytes: int
    kem_ciphertext_bytes: int
    kem_shared_secret_bytes: int
    sig_public_key_bytes: int
    signature_bytes: int
    kem_keypair_ns: int
    kem_encap_ns: int
    kem_decap_ns: int
    sig_keypair_ns: int
    sig_sign_ns: int
    sig_verify_ns: int
    kem_ok: bool
    sig_ok: bool


def require_oqs() -> None:
    if oqs is None:
        raise SystemExit(f"liboqs-python is not available: {OQS_IMPORT_ERROR}")


def measure_session(
    session_id: int,
    *,
    ts: int,
    event_type: str = "handshake",
    tenant_id: str,
    kem_name: str,
    sig_name: str,
    payload_bytes: int,
    session_len: int,
) -> MeasuredEvent:
    require_oqs()
    message = f"quasar-session-{session_id}".encode("utf-8")
    with oqs.KeyEncapsulation(kem_name) as kem:
        start = time.perf_counter_ns()
        public_key = kem.generate_keypair()
        kem_keypair_ns = time.perf_counter_ns() - start
        start = time.perf_counter_ns()
        ciphertext, shared_secret = kem.encap_secret(public_key)
        kem_encap_ns = time.perf_counter_ns() - start
        start = time.perf_counter_ns()
        recovered_secret = kem.decap_secret(ciphertext)
        kem_decap_ns = time.perf_counter_ns() - start

    with oqs.Signature(sig_name) as sig:
        start = time.perf_counter_ns()
        sig_public_key = sig.generate_keypair()
        sig_keypair_ns = time.perf_counter_ns() - start
        start = time.perf_counter_ns()
        signature = sig.sign(message)
        sig_sign_ns = time.perf_counter_ns() - start
        start = time.perf_counter_ns()
        sig_ok = bool(sig.verify(message, signature, sig_public_key))
        sig_verify_ns = time.perf_counter_ns() - start

    return MeasuredEvent(
        ts=ts,
        event=event_type,
        session_id=f"s{session_id}",
        tenant_id=tenant_id,
        kem=kem_name,
        sig=sig_name,
        payload_bytes=payload_bytes,
        session_end_ts=ts + session_len,
        kem_public_key_bytes=len(public_key),
        kem_ciphertext_bytes=len(ciphertext),
        kem_shared_secret_bytes=len(shared_secret),
        sig_public_key_bytes=len(sig_public_key),
        signature_bytes=len(signature),
        kem_keypair_ns=kem_keypair_ns,
        kem_encap_ns=kem_encap_ns,
        kem_decap_ns=kem_decap_ns,
        sig_keypair_ns=sig_keypair_ns,
        sig_sign_ns=sig_sign_ns,
        sig_verify_ns=sig_verify_ns,
        kem_ok=shared_secret == recovered_secret,
        sig_ok=sig_ok,
    )


def generate_events(args: argparse.Namespace) -> list[MeasuredEvent]:
    rng = random.Random(args.seed)
    events = []
    for idx in range(args.sessions):
        payload_bytes = rng.randint(args.payload_min_bytes, args.payload_max_bytes)
        session_len = rng.randint(args.session_min_ms, args.session_max_ms)
        events.append(
            measure_session(
                idx,
                ts=idx * args.session_spacing_ms,
                event_type=args.event_type,
                tenant_id=f"tenant{idx % args.tenants}",
                kem_name=args.kem,
                sig_name=args.sig,
                payload_bytes=payload_bytes,
                session_len=session_len,
            )
        )
    return events


def write_event_log(path: Path, events: list[MeasuredEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        for event in events:
            out.write(json.dumps(asdict(event), sort_keys=True) + "\n")


def summarize(events: list[MeasuredEvent], trace_summary: dict | None = None) -> dict:
    if not events:
        return {"sessions": 0}
    summary = {
        "sessions": len(events),
        "kem": events[0].kem,
        "sig": events[0].sig,
        "kem_public_key_bytes": events[0].kem_public_key_bytes,
        "kem_ciphertext_bytes": events[0].kem_ciphertext_bytes,
        "kem_shared_secret_bytes": events[0].kem_shared_secret_bytes,
        "sig_public_key_bytes": events[0].sig_public_key_bytes,
        "signature_bytes": events[0].signature_bytes,
        "all_kem_ok": all(event.kem_ok for event in events),
        "all_sig_ok": all(event.sig_ok for event in events),
        "avg_kem_keypair_ns": sum(event.kem_keypair_ns for event in events) / len(events),
        "avg_kem_encap_ns": sum(event.kem_encap_ns for event in events) / len(events),
        "avg_kem_decap_ns": sum(event.kem_decap_ns for event in events) / len(events),
        "avg_sig_keypair_ns": sum(event.sig_keypair_ns for event in events) / len(events),
        "avg_sig_sign_ns": sum(event.sig_sign_ns for event in events) / len(events),
        "avg_sig_verify_ns": sum(event.sig_verify_ns for event in events) / len(events),
    }
    if trace_summary:
        summary["trace"] = trace_summary
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=100)
    parser.add_argument("--event-type", default="handshake")
    parser.add_argument("--kem", default="ML-KEM-768")
    parser.add_argument("--sig", default="ML-DSA-65")
    parser.add_argument("--tenants", type=int, default=1)
    parser.add_argument("--session-spacing-ms", type=int, default=10)
    parser.add_argument("--session-min-ms", type=int, default=100)
    parser.add_argument("--session-max-ms", type=int, default=1000)
    parser.add_argument("--payload-min-bytes", type=int, default=4096)
    parser.add_argument("--payload-max-bytes", type=int, default=16384)
    parser.add_argument("--epoch-len-ms", type=int, default=1000)
    parser.add_argument("--rotation-epochs", type=int, default=24)
    parser.add_argument("--lba-space", type=int, default=2_000_000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--event-log", type=Path, default=Path("artifacts/traces/liboqs-events.jsonl"))
    parser.add_argument("--jsonl", type=Path, default=Path("artifacts/traces/liboqs-pqc.jsonl"))
    parser.add_argument("--dogi-trace", type=Path, default=Path("artifacts/traces/liboqs-pqc.dogi"))
    parser.add_argument("--summary-out", type=Path, default=Path("artifacts/results/liboqs-pqc-summary.json"))
    args = parser.parse_args()

    require_oqs()
    events = generate_events(args)
    write_event_log(args.event_log, events)
    crypto_events = [bridge.event_from_row(asdict(event)) for event in events]
    rows = bridge.expand_events(
        crypto_events,
        epoch_len_ms=args.epoch_len_ms,
        rotation_epochs=args.rotation_epochs,
        session_jitter_ms=0,
        lba_space=args.lba_space,
        seed=args.seed,
    )
    bridge.write_jsonl(args.jsonl, rows)
    dogi_extra = bridge.write_dogi(args.dogi_trace, rows, delete_markers=True)
    trace_summary = bridge.summarize(rows, dogi_extra)
    summary = summarize(events, trace_summary)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote event_log={args.event_log}")
    print(f"wrote jsonl={args.jsonl}")
    print(f"wrote dogi_trace={args.dogi_trace}")
    print(f"wrote summary={args.summary_out}")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
