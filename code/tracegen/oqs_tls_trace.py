#!/usr/bin/env python3
"""Convert OQS/OpenSSL-style TLS/KMS event logs into QUASAR JSONL traces.

This script is the bridge between a real PQC software stack and the simulator.
It accepts a small event log that can be emitted by an OpenSSL+oqsprovider TLS
terminator, a liboqs microbenchmark wrapper, or a KMS harness, then expands each
cryptographic event into storage objects with QUASAR lifecycle hints.

The script can also probe the local OpenSSL binary and write a capability
manifest. On machines without oqsprovider/OpenSSL 3 provider support, the probe
still records the negative result so experiments can distinguish "not measured"
from "measured with no PQC provider".
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import math
import random
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


BLOCK_SIZE = 4096

KEM_SIZES = {
    "ML-KEM-512": {"public_key": 800, "secret_key": 1632, "ciphertext": 768, "shared_secret": 32},
    "ML-KEM-768": {"public_key": 1184, "secret_key": 2400, "ciphertext": 1088, "shared_secret": 32},
    "ML-KEM-1024": {"public_key": 1568, "secret_key": 3168, "ciphertext": 1568, "shared_secret": 32},
    "KYBER512": {"public_key": 800, "secret_key": 1632, "ciphertext": 768, "shared_secret": 32},
    "KYBER768": {"public_key": 1184, "secret_key": 2400, "ciphertext": 1088, "shared_secret": 32},
    "KYBER1024": {"public_key": 1568, "secret_key": 3168, "ciphertext": 1568, "shared_secret": 32},
}

SIG_SIZES = {
    "ML-DSA-44": {"public_key": 1312, "secret_key": 2560, "signature": 2420},
    "ML-DSA-65": {"public_key": 1952, "secret_key": 4032, "signature": 3309},
    "ML-DSA-87": {"public_key": 2592, "secret_key": 4896, "signature": 4627},
    "DILITHIUM2": {"public_key": 1312, "secret_key": 2560, "signature": 2420},
    "DILITHIUM3": {"public_key": 1952, "secret_key": 4032, "signature": 3309},
    "DILITHIUM5": {"public_key": 2592, "secret_key": 4896, "signature": 4627},
}

SECRET_INTENTS = {"EPHEMERAL_SECRET", "KEM_ARTIFACT"}


@dataclass(frozen=True)
class CryptoEvent:
    ts: int
    event: str
    session_id: str
    tenant_id: str
    kem: str
    sig: str
    payload_bytes: int
    session_end_ts: Optional[int]


@dataclass(order=True)
class PendingExpire:
    ts: int
    object_id: int


def blocks_for(byte_count: int) -> int:
    return max(1, math.ceil(max(1, byte_count) / BLOCK_SIZE))


def stable_lba(*parts: object, lba_space: int) -> int:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    digest = hashlib.blake2b(raw, digest_size=8).digest()
    return int.from_bytes(digest, "little") % lba_space


def normalize_algorithm(name: str, table: dict[str, dict[str, int]], fallback: str) -> str:
    normalized = (name or fallback).strip().upper().replace("_", "-")
    aliases = {
        "MLKEM512": "ML-KEM-512",
        "MLKEM768": "ML-KEM-768",
        "MLKEM1024": "ML-KEM-1024",
        "MLDSA44": "ML-DSA-44",
        "MLDSA65": "ML-DSA-65",
        "MLDSA87": "ML-DSA-87",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in table:
        return normalized
    return fallback


def read_event_log(path: Path) -> list[CryptoEvent]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as src:
            rows = list(csv.DictReader(src))
    else:
        rows = []
        with path.open("r", encoding="utf-8") as src:
            for line in src:
                if line.strip():
                    rows.append(json.loads(line))
    return [event_from_row(row) for row in rows]


def event_from_row(row: dict) -> CryptoEvent:
    ts = int(row.get("ts", row.get("timestamp_ms", row.get("timestamp", 0))))
    event = str(row.get("event", row.get("type", row.get("op", "handshake")))).lower()
    session_id = str(row.get("session_id", row.get("connection_id", row.get("object_id", ts))))
    tenant_id = str(row.get("tenant_id", "tenant0"))
    kem = normalize_algorithm(str(row.get("kem", row.get("kem_alg", "ML-KEM-768"))), KEM_SIZES, "ML-KEM-768")
    sig = normalize_algorithm(str(row.get("sig", row.get("sig_alg", "ML-DSA-65"))), SIG_SIZES, "ML-DSA-65")
    payload_bytes = int(row.get("payload_bytes", row.get("payload", 0)) or 0)
    end_raw = row.get("session_end_ts", row.get("end_ts", row.get("close_ts")))
    session_end_ts = None if end_raw in (None, "", "null") else int(end_raw)
    return CryptoEvent(
        ts=ts,
        event=event,
        session_id=session_id,
        tenant_id=tenant_id,
        kem=kem,
        sig=sig,
        payload_bytes=payload_bytes,
        session_end_ts=session_end_ts,
    )


def expire_class_for(intent: str) -> str:
    if intent in SECRET_INTENTS:
        return "EPOCH"
    if intent == "CERT_METADATA":
        return "ROTATION"
    if intent == "SIGNATURE_LOG":
        return "APPEND_ONLY"
    return "UNKNOWN"


def security_class_for(intent: str) -> str:
    if intent in SECRET_INTENTS:
        return "SECRET"
    if intent in {"CERT_METADATA", "SIGNATURE_LOG"}:
        return "PUBLIC_METADATA"
    return "PAYLOAD"


def epoch_expiry(ts: int, epoch_len_ms: int, jitter_ms: int, rng: random.Random) -> int:
    next_epoch = ((ts // epoch_len_ms) + 1) * epoch_len_ms
    return next_epoch + (rng.randint(0, jitter_ms) if jitter_ms > 0 else 0)


def rotation_expiry(ts: int, epoch_len_ms: int, rotation_epochs: int) -> int:
    epoch = ts // epoch_len_ms
    return ((epoch // rotation_epochs) + 1) * rotation_epochs * epoch_len_ms


def make_write(
    *,
    ts: int,
    object_id: int,
    lba: int,
    size_bytes: int,
    intent: str,
    epoch_id: int,
    tenant_id: str,
    cohort_id: str,
    expire_ts: Optional[int],
    algorithm: str,
) -> dict:
    return {
        "op": "write",
        "ts": ts,
        "object_id": object_id,
        "lba": lba,
        "size_blocks": blocks_for(size_bytes),
        "size_bytes": size_bytes,
        "intent": intent,
        "epoch_id": epoch_id,
        "expire_class": expire_class_for(intent),
        "security_class": security_class_for(intent),
        "cohort_id": cohort_id,
        "tenant_id": tenant_id,
        "confidence": "exact",
        "algorithm": algorithm,
        "expire_ts": expire_ts,
    }


def expand_events(
    events: Iterable[CryptoEvent],
    *,
    epoch_len_ms: int,
    rotation_epochs: int,
    session_jitter_ms: int,
    lba_space: int,
    seed: int,
) -> list[dict]:
    rng = random.Random(seed)
    events = sorted(events, key=lambda event: event.ts)
    session_end: dict[str, int] = {}
    for event in events:
        if event.session_end_ts is not None:
            session_end[event.session_id] = event.session_end_ts
        if event.event in {"session_end", "close", "close_notify"}:
            session_end[event.session_id] = event.ts

    output: list[dict] = []
    pending: list[PendingExpire] = []
    object_meta: dict[int, tuple[int, int]] = {}
    next_object_id = 1

    def add_object(event: CryptoEvent, intent: str, size_bytes: int, expire_ts: Optional[int], algorithm: str) -> None:
        nonlocal next_object_id
        epoch_id = event.ts // epoch_len_ms
        object_id = next_object_id
        next_object_id += 1
        cohort_id = f"{event.tenant_id}:{event.session_id}:{epoch_id}:{intent}"
        lba = stable_lba(event.tenant_id, event.session_id, intent, object_id, lba_space=lba_space)
        write = make_write(
            ts=event.ts,
            object_id=object_id,
            lba=lba,
            size_bytes=size_bytes,
            intent=intent,
            epoch_id=epoch_id,
            tenant_id=event.tenant_id,
            cohort_id=cohort_id,
            expire_ts=expire_ts,
            algorithm=algorithm,
        )
        output.append(write)
        if expire_ts is not None:
            object_meta[object_id] = (lba, write["size_blocks"])
            heapq.heappush(pending, PendingExpire(expire_ts, object_id))

    for event in events:
        while pending and pending[0].ts <= event.ts:
            item = heapq.heappop(pending)
            lba, size_blocks = object_meta.pop(item.object_id)
            output.append(
                {
                    "op": "expire",
                    "ts": item.ts,
                    "object_id": item.object_id,
                    "lba": lba,
                    "size_blocks": size_blocks,
                }
            )
        if event.event in {"session_end", "close", "close_notify"}:
            continue

        kem_sizes = KEM_SIZES[event.kem]
        sig_sizes = SIG_SIZES[event.sig]
        expiry = session_end.get(event.session_id)
        if expiry is None:
            expiry = epoch_expiry(event.ts, epoch_len_ms, session_jitter_ms, rng)

        if event.event in {"handshake", "tls_handshake", "tls_kem", "connect", "rekey", "kms_wrap"}:
            add_object(
                event,
                "KEM_ARTIFACT",
                kem_sizes["public_key"] + kem_sizes["ciphertext"],
                expiry,
                event.kem,
            )
            add_object(
                event,
                "EPHEMERAL_SECRET",
                kem_sizes["secret_key"] + kem_sizes["shared_secret"],
                expiry,
                event.kem,
            )
            if event.event != "tls_kem":
                add_object(
                    event,
                    "CERT_METADATA",
                    sig_sizes["public_key"],
                    rotation_expiry(event.ts, epoch_len_ms, rotation_epochs),
                    event.sig,
                )
        if event.event in {"signature", "sign", "audit_log", "handshake", "tls_handshake"}:
            add_object(event, "SIGNATURE_LOG", sig_sizes["signature"], None, event.sig)
        if event.payload_bytes > 0:
            add_object(event, "PAYLOAD", event.payload_bytes, None, "application")

    while pending:
        item = heapq.heappop(pending)
        lba, size_blocks = object_meta.pop(item.object_id)
        output.append(
            {
                "op": "expire",
                "ts": item.ts,
                "object_id": item.object_id,
                "lba": lba,
                "size_blocks": size_blocks,
            }
        )
    return sorted(output, key=lambda row: (int(row["ts"]), 0 if row["op"] == "write" else 1, int(row["object_id"])))


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, sort_keys=True) + "\n")


def write_dogi(path: Path, rows: Iterable[dict], *, delete_markers: bool) -> dict[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    writes = 0
    tombstones = 0
    max_lba = 0
    with path.open("w", encoding="utf-8") as out:
        for row in rows:
            ts = int(row["ts"])
            lba = int(row["lba"])
            max_lba = max(max_lba, lba)
            if row["op"] == "write":
                out.write(f"{ts} 1 {lba} {int(row['size_blocks']) * BLOCK_SIZE}\n")
                writes += 1
            elif delete_markers:
                out.write(f"{ts} 1 {lba} {BLOCK_SIZE}\n")
                tombstones += 1
    return {"dogi_writes": writes, "dogi_tombstones": tombstones, "dogi_max_lba": max_lba}


def summarize(rows: list[dict], extra: Optional[dict] = None) -> dict:
    writes = [row for row in rows if row["op"] == "write"]
    expires = [row for row in rows if row["op"] == "expire"]
    intent_counts: dict[str, int] = {}
    blocks_by_intent: dict[str, int] = {}
    for row in writes:
        intent = row.get("intent", "UNKNOWN")
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
        blocks_by_intent[intent] = blocks_by_intent.get(intent, 0) + int(row["size_blocks"])
    summary = {
        "writes": len(writes),
        "expires": len(expires),
        "write_blocks": sum(int(row["size_blocks"]) for row in writes),
        "expire_blocks": sum(int(row["size_blocks"]) for row in expires),
        "intent_counts": intent_counts,
        "blocks_by_intent": blocks_by_intent,
        "max_ts": max((int(row["ts"]) for row in rows), default=0),
    }
    if extra:
        summary.update(extra)
    return summary


def run_openssl_command(args: list[str]) -> dict:
    try:
        proc = subprocess.run(args, check=False, text=True, capture_output=True)
    except FileNotFoundError:
        return {"available": False, "command": args, "returncode": None, "stdout": "", "stderr": "not found"}
    return {
        "available": True,
        "command": args,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def probe_openssl(openssl_bin: str) -> dict:
    version = run_openssl_command([openssl_bin, "version", "-a"])
    providers = run_openssl_command([openssl_bin, "list", "-providers"])
    kems = run_openssl_command([openssl_bin, "list", "-kem-algorithms"])
    pqc_names = ("ML-KEM", "KYBER", "ML-DSA", "DILITHIUM", "FALCON", "SPHINCS")
    combined = "\n".join([kems.get("stdout", ""), kems.get("stderr", ""), providers.get("stdout", "")]).upper()
    return {
        "openssl_bin": openssl_bin,
        "version": version,
        "providers": providers,
        "kem_algorithms": kems,
        "pqc_provider_detected": any(name in combined for name in pqc_names) and kems.get("returncode") == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-log", type=Path)
    parser.add_argument("--jsonl", type=Path)
    parser.add_argument("--dogi-trace", type=Path)
    parser.add_argument("--dogi-delete-markers", action="store_true")
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument("--probe-out", type=Path)
    parser.add_argument("--openssl-bin", default="openssl")
    parser.add_argument("--epoch-len-ms", type=int, default=60_000)
    parser.add_argument("--rotation-epochs", type=int, default=24)
    parser.add_argument("--session-jitter-ms", type=int, default=0)
    parser.add_argument("--lba-space", type=int, default=2_000_000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    probe = None
    if args.probe_out:
        probe = probe_openssl(args.openssl_bin)
        args.probe_out.parent.mkdir(parents=True, exist_ok=True)
        args.probe_out.write_text(json.dumps(probe, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote probe={args.probe_out}")

    if not args.event_log:
        return 0
    if not args.jsonl:
        raise SystemExit("--jsonl is required when --event-log is provided")

    crypto_events = read_event_log(args.event_log)
    rows = expand_events(
        crypto_events,
        epoch_len_ms=args.epoch_len_ms,
        rotation_epochs=args.rotation_epochs,
        session_jitter_ms=args.session_jitter_ms,
        lba_space=args.lba_space,
        seed=args.seed,
    )
    write_jsonl(args.jsonl, rows)
    print(f"wrote jsonl={args.jsonl}")

    extra = {"input_events": len(crypto_events)}
    if args.dogi_trace:
        extra.update(write_dogi(args.dogi_trace, rows, delete_markers=args.dogi_delete_markers))
        print(f"wrote dogi_trace={args.dogi_trace}")
    if probe is not None:
        extra["pqc_provider_detected"] = probe["pqc_provider_detected"]
    summary = summarize(rows, extra)
    if args.summary_out:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote summary={args.summary_out}")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
