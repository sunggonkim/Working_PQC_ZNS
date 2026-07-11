#!/usr/bin/env python3
"""Generate synthetic PQC storage traces for ZNS placement experiments.

The JSONL trace preserves PQC-specific intent and epoch metadata for simulator
experiments. The optional DOGI trace emits DOGI's write-only input shape:

    <timestamp> 1 <lba_4k> <length_bytes>

DOGI invalidates old physical versions through overwrites. To approximate object
expiry in that interface, use --dogi-delete-markers to emit a tombstone write to
the same LBA when a PQC object expires.
"""

from __future__ import annotations

import argparse
import heapq
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


INTENTS = (
    "EPHEMERAL_SECRET",
    "KEM_ARTIFACT",
    "SIGNATURE_LOG",
    "CERT_METADATA",
    "PAYLOAD",
)


def expire_class_for(intent: str) -> str:
    if intent in {"EPHEMERAL_SECRET", "KEM_ARTIFACT"}:
        return "EPOCH"
    if intent == "CERT_METADATA":
        return "ROTATION"
    if intent == "SIGNATURE_LOG":
        return "APPEND_ONLY"
    if intent == "PAYLOAD":
        return "UNKNOWN"
    return "UNKNOWN"


def security_class_for(intent: str) -> str:
    if intent in {"EPHEMERAL_SECRET", "KEM_ARTIFACT"}:
        return "SECRET"
    if intent in {"SIGNATURE_LOG", "CERT_METADATA"}:
        return "PUBLIC_METADATA"
    return "PAYLOAD"


@dataclass(order=True)
class PendingExpire:
    ts: int
    object_id: int


def choose_object(
    rng: random.Random,
    payload_ratio: float,
    *,
    kem_weight: float,
    secret_weight: float,
    sig_weight: float,
    cert_weight: float,
) -> tuple[str, int]:
    """Return (intent, size_blocks)."""
    x = rng.random()
    if x < payload_ratio:
        return "PAYLOAD", rng.randint(4, 32)
    total = kem_weight + secret_weight + sig_weight + cert_weight
    if total <= 0:
        raise ValueError("non-payload intent weights must sum to a positive value")
    x = rng.random()
    kem_cut = kem_weight / total
    secret_cut = kem_cut + secret_weight / total
    sig_cut = secret_cut + sig_weight / total
    if x < kem_cut:
        return "KEM_ARTIFACT", rng.randint(1, 3)
    if x < secret_cut:
        return "EPHEMERAL_SECRET", 1
    if x < sig_cut:
        return "SIGNATURE_LOG", rng.randint(1, 4)
    return "CERT_METADATA", rng.randint(2, 8)


def expiry_for(
    *,
    intent: str,
    ts: int,
    epoch_len: int,
    rng: random.Random,
    long_lived_epochs: int,
    session_jitter: int,
) -> Optional[int]:
    epoch = ts // epoch_len
    next_epoch = (epoch + 1) * epoch_len

    if intent in {"EPHEMERAL_SECRET", "KEM_ARTIFACT"}:
        jitter = rng.randint(0, session_jitter) if session_jitter > 0 else 0
        return next_epoch + jitter
    if intent == "CERT_METADATA":
        return ((epoch // long_lived_epochs) + 1) * long_lived_epochs * epoch_len
    if intent == "SIGNATURE_LOG":
        return None
    if intent == "PAYLOAD":
        return None
    return None


def make_lba(
    *,
    rng: random.Random,
    object_id: int,
    lba_space: int,
    lba_mode: str,
    epoch_id: int,
    intent: str,
) -> int:
    if lba_mode == "random":
        return rng.randrange(lba_space)
    if lba_mode == "sequential":
        return object_id % lba_space
    if lba_mode == "epoch-clustered":
        intent_id = INTENTS.index(intent)
        base = ((epoch_id * len(INTENTS) + intent_id) * 100_003) % lba_space
        return (base + rng.randrange(8192)) % lba_space
    raise ValueError(f"unknown lba mode: {lba_mode}")


def emit_event(out, event: dict) -> None:
    out.write(json.dumps(event, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=80_000)
    parser.add_argument("--epoch-len", type=int, default=2_000)
    parser.add_argument("--payload-ratio", type=float, default=0.35)
    parser.add_argument("--kem-weight", type=float, default=0.40)
    parser.add_argument("--secret-weight", type=float, default=0.32)
    parser.add_argument("--signature-weight", type=float, default=0.18)
    parser.add_argument("--cert-weight", type=float, default=0.10)
    parser.add_argument("--lba-space", type=int, default=2_000_000)
    parser.add_argument("--lba-mode", choices=["random", "sequential", "epoch-clustered"], default="random")
    parser.add_argument("--long-lived-epochs", type=int, default=12)
    parser.add_argument("--session-jitter", type=int, default=64)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--dogi-trace", type=Path)
    parser.add_argument("--dogi-delete-markers", action="store_true")
    args = parser.parse_args()

    if not 0.0 <= args.payload_ratio <= 1.0:
        raise SystemExit("--payload-ratio must be in [0, 1]")

    args.jsonl.parent.mkdir(parents=True, exist_ok=True)
    if args.dogi_trace:
        args.dogi_trace.parent.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    expires: list[PendingExpire] = []
    object_meta: dict[int, tuple[int, int]] = {}
    intent_counts = {intent: 0 for intent in INTENTS}
    write_blocks = 0
    expire_blocks = 0

    dogi = args.dogi_trace.open("w", encoding="utf-8") if args.dogi_trace else None
    try:
        with args.jsonl.open("w", encoding="utf-8") as out:
            for ts in range(args.events):
                while expires and expires[0].ts <= ts:
                    item = heapq.heappop(expires)
                    if item.object_id not in object_meta:
                        continue
                    lba, size_blocks = object_meta.pop(item.object_id)
                    expire_blocks += size_blocks
                    emit_event(
                        out,
                        {
                            "op": "expire",
                            "ts": ts,
                            "object_id": item.object_id,
                            "lba": lba,
                            "size_blocks": size_blocks,
                        },
                    )
                    if dogi and args.dogi_delete_markers:
                        dogi.write(f"{ts} 1 {lba} 4096\n")

                intent, size_blocks = choose_object(
                    rng,
                    args.payload_ratio,
                    kem_weight=args.kem_weight,
                    secret_weight=args.secret_weight,
                    sig_weight=args.signature_weight,
                    cert_weight=args.cert_weight,
                )
                epoch_id = ts // args.epoch_len
                object_id = ts
                lba = make_lba(
                    rng=rng,
                    object_id=object_id,
                    lba_space=args.lba_space,
                    lba_mode=args.lba_mode,
                    epoch_id=epoch_id,
                    intent=intent,
                )
                expire_ts = expiry_for(
                    intent=intent,
                    ts=ts,
                    epoch_len=args.epoch_len,
                    rng=rng,
                    long_lived_epochs=args.long_lived_epochs,
                    session_jitter=args.session_jitter,
                )
                intent_counts[intent] += 1
                write_blocks += size_blocks

                event = {
                    "op": "write",
                    "ts": ts,
                    "object_id": object_id,
                    "lba": lba,
                    "size_blocks": size_blocks,
                    "intent": intent,
                    "epoch_id": epoch_id,
                    "expire_class": expire_class_for(intent),
                    "security_class": security_class_for(intent),
                    "cohort_id": f"{intent}:{epoch_id}",
                    "tenant_id": "tenant0",
                    "confidence": "exact",
                    "expire_ts": expire_ts,
                }
                emit_event(out, event)
                if dogi:
                    dogi.write(f"{ts} 1 {lba} {size_blocks * 4096}\n")
                if expire_ts is not None:
                    object_meta[object_id] = (lba, size_blocks)
                    heapq.heappush(expires, PendingExpire(expire_ts, object_id))

            drain_ts = args.events
            while expires:
                item = heapq.heappop(expires)
                if item.object_id not in object_meta:
                    continue
                lba, size_blocks = object_meta.pop(item.object_id)
                expire_blocks += size_blocks
                emit_event(
                    out,
                    {
                        "op": "expire",
                        "ts": max(drain_ts, item.ts),
                        "object_id": item.object_id,
                        "lba": lba,
                        "size_blocks": size_blocks,
                    },
                )
                if dogi and args.dogi_delete_markers:
                    dogi.write(f"{max(drain_ts, item.ts)} 1 {lba} 4096\n")
    finally:
        if dogi:
            dogi.close()

    print(f"wrote jsonl={args.jsonl}")
    if args.dogi_trace:
        print(f"wrote dogi_trace={args.dogi_trace}")
    print(f"writes={args.events} write_blocks={write_blocks} expire_blocks={expire_blocks}")
    print("intent_counts=" + json.dumps(intent_counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
