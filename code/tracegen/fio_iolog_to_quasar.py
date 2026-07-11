#!/usr/bin/env python3
"""Convert a real FIO iolog into QUASAR JSONL with optional PQC side writes.

FIO's `--write_iolog` records the writes actually issued by the benchmark:

    fio version 2 iolog
    /path/to/file add
    /path/to/file open
    /path/to/file write <offset_bytes> <size_bytes>

This converter keeps those real payload writes as the base workload and adds
protocol-driven PQC lifecycle writes on top.  That gives us a DOGI-friendly
payload trace first, then a PQC-hostile death-cohort overlay second.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path


SECRET_INTENTS = {"KEM_ARTIFACT", "EPHEMERAL_SECRET"}
PQC_INTENTS = ("KEM_ARTIFACT", "EPHEMERAL_SECRET", "SIGNATURE_LOG", "CERT_METADATA")


@dataclass(order=True)
class PendingExpire:
    ts: int
    object_id: int
    lba: int
    size_blocks: int


def emit(out, row: dict) -> None:
    out.write(json.dumps(row, sort_keys=True) + "\n")


def expire_class(intent: str) -> str:
    if intent in SECRET_INTENTS:
        return "EPOCH"
    if intent == "CERT_METADATA":
        return "ROTATION"
    if intent == "SIGNATURE_LOG":
        return "APPEND_ONLY"
    return "UNKNOWN"


def security_class(intent: str) -> str:
    if intent in SECRET_INTENTS:
        return "SECRET"
    if intent in {"CERT_METADATA", "SIGNATURE_LOG"}:
        return "PUBLIC_METADATA"
    return "PAYLOAD"


def choose_pqc(rng: random.Random) -> tuple[str, int]:
    x = rng.random()
    if x < 0.40:
        return "KEM_ARTIFACT", rng.randint(1, 3)
    if x < 0.72:
        return "EPHEMERAL_SECRET", 1
    if x < 0.90:
        return "SIGNATURE_LOG", rng.randint(1, 4)
    return "CERT_METADATA", rng.randint(2, 8)


def pqc_expire_ts(
    *,
    intent: str,
    ts: int,
    epoch_len: int,
    rng: random.Random,
    session_jitter: int,
    rotation_epochs: int,
) -> int | None:
    epoch = ts // epoch_len
    if intent in SECRET_INTENTS:
        jitter = rng.randint(0, session_jitter) if session_jitter else 0
        return (epoch + 1) * epoch_len + jitter
    if intent == "CERT_METADATA":
        return ((epoch // rotation_epochs) + 1) * rotation_epochs * epoch_len
    return None


def parse_fio_iolog_write(line: str) -> tuple[int, int] | None:
    parts = line.split()
    if len(parts) < 4:
        return None
    if parts[-3] != "write":
        return None
    try:
        offset = int(parts[-2])
        size_bytes = int(parts[-1])
    except ValueError:
        return None
    if size_bytes <= 0:
        return None
    first_lba = offset // 4096
    last_lba = (offset + size_bytes - 1) // 4096
    return first_lba, last_lba - first_lba + 1


def payload_write_row(ts: int, object_id: int, lba: int) -> dict:
    return {
        "op": "write",
        "ts": ts,
        "object_id": object_id,
        "lba": lba,
        "size_blocks": 1,
        "intent": "PAYLOAD",
        "epoch_id": 0,
        "expire_class": "UNKNOWN",
        "security_class": "PAYLOAD",
        "cohort_id": "payload",
        "tenant_id": "tenant0",
        "confidence": "exact",
        "expire_ts": None,
    }


def prefill_row(object_id: int, lba: int) -> dict:
    row = payload_write_row(0, object_id, lba)
    row["op"] = "prefill"
    return row


def expire_row(ts: int, object_id: int, lba: int, size_blocks: int = 1) -> dict:
    return {
        "op": "expire",
        "ts": ts,
        "object_id": object_id,
        "lba": lba,
        "size_blocks": size_blocks,
    }


def inject_pqc(
    *,
    out,
    dogi_out,
    rng: random.Random,
    ts: int,
    next_object_id: int,
    pqc_ratio: float,
    epoch_len: int,
    pqc_lba_base: int,
    pqc_lba_span: int,
    session_jitter: int,
    rotation_epochs: int,
    expires: list[PendingExpire],
) -> tuple[int, int, int]:
    whole = int(pqc_ratio)
    target = whole + (1 if rng.random() < pqc_ratio - whole else 0)
    writes = 0
    blocks = 0
    for _ in range(target):
        intent, size_blocks = choose_pqc(rng)
        epoch_id = ts // epoch_len
        lba = pqc_lba_base + rng.randrange(max(1, pqc_lba_span))
        expire_ts = pqc_expire_ts(
            intent=intent,
            ts=ts,
            epoch_len=epoch_len,
            rng=rng,
            session_jitter=session_jitter,
            rotation_epochs=rotation_epochs,
        )
        object_id = next_object_id
        next_object_id += 1
        writes += 1
        blocks += size_blocks
        emit(
            out,
            {
                "op": "write",
                "ts": ts,
                "object_id": object_id,
                "lba": lba,
                "size_blocks": size_blocks,
                "intent": intent,
                "epoch_id": epoch_id,
                "expire_class": expire_class(intent),
                "security_class": security_class(intent),
                "cohort_id": f"{intent}:{epoch_id}",
                "tenant_id": "tenant0",
                "confidence": "exact",
                "expire_ts": expire_ts,
            },
        )
        if dogi_out:
            dogi_out.write(f"{ts} 1 {lba} {size_blocks * 4096}\n")
        if expire_ts is not None:
            heapq.heappush(expires, PendingExpire(expire_ts, object_id, lba, size_blocks))
    return next_object_id, writes, blocks


def collect_prefill_lbas(iolog: Path, max_events: int) -> list[int]:
    lbas: set[int] = set()
    events = 0
    with iolog.open("r", encoding="utf-8", errors="replace") as src:
        for line in src:
            parsed = parse_fio_iolog_write(line)
            if parsed is None:
                continue
            lba, size_blocks = parsed
            for offset in range(size_blocks):
                lbas.add(lba + offset)
            events += 1
            if events >= max_events:
                break
    return sorted(lbas)


def convert(args: argparse.Namespace) -> dict:
    rng = random.Random(args.seed)
    live_by_lba: dict[int, int] = {}
    expires: list[PendingExpire] = []
    next_object_id = 1

    payload_requests = 0
    payload_blocks = 0
    payload_expire_blocks = 0
    pqc_writes = 0
    pqc_blocks = 0
    pqc_expire_blocks = 0
    max_lba = 0
    max_ts = 0

    prefill_lbas = collect_prefill_lbas(args.iolog, args.max_events) if args.prefill_working_set else []

    args.jsonl.parent.mkdir(parents=True, exist_ok=True)
    if args.dogi_out:
        args.dogi_out.parent.mkdir(parents=True, exist_ok=True)
    dogi_out = args.dogi_out.open("w", encoding="utf-8") if args.dogi_out else None
    try:
        with args.iolog.open("r", encoding="utf-8", errors="replace") as src, args.jsonl.open("w", encoding="utf-8") as out:
            for lba in prefill_lbas:
                object_id = next_object_id
                next_object_id += 1
                live_by_lba[lba] = object_id
                max_lba = max(max_lba, lba)
                emit(out, prefill_row(object_id, lba))

            for line in src:
                parsed = parse_fio_iolog_write(line)
                if parsed is None:
                    continue
                first_lba, size_blocks = parsed
                ts = payload_requests + 1
                max_ts = max(max_ts, ts)

                while expires and expires[0].ts <= ts:
                    item = heapq.heappop(expires)
                    emit(out, expire_row(ts, item.object_id, item.lba, item.size_blocks))
                    pqc_expire_blocks += item.size_blocks

                for offset in range(size_blocks):
                    lba = first_lba + offset
                    max_lba = max(max_lba, lba)
                    previous = live_by_lba.get(lba)
                    if previous is not None:
                        emit(out, expire_row(ts, previous, lba))
                        payload_expire_blocks += 1
                    object_id = next_object_id
                    next_object_id += 1
                    live_by_lba[lba] = object_id
                    emit(out, payload_write_row(ts, object_id, lba))
                    if dogi_out:
                        dogi_out.write(f"{ts} 1 {lba} 4096\n")

                payload_requests += 1
                payload_blocks += size_blocks

                next_object_id, writes, blocks = inject_pqc(
                    out=out,
                    dogi_out=dogi_out,
                    rng=rng,
                    ts=ts,
                    next_object_id=next_object_id,
                    pqc_ratio=args.pqc_ratio,
                    epoch_len=args.epoch_len,
                    pqc_lba_base=args.pqc_lba_base,
                    pqc_lba_span=args.pqc_lba_span,
                    session_jitter=args.session_jitter,
                    rotation_epochs=args.rotation_epochs,
                    expires=expires,
                )
                pqc_writes += writes
                pqc_blocks += blocks

                if payload_requests >= args.max_events:
                    break

            drain_ts = max_ts + 1
            while expires:
                item = heapq.heappop(expires)
                ts = max(drain_ts, item.ts)
                emit(out, expire_row(ts, item.object_id, item.lba, item.size_blocks))
                pqc_expire_blocks += item.size_blocks
    finally:
        if dogi_out:
            dogi_out.close()

    summary = {
        "source_iolog": str(args.iolog),
        "jsonl": str(args.jsonl),
        "dogi_out": str(args.dogi_out) if args.dogi_out else None,
        "max_events": args.max_events,
        "prefill_working_set": args.prefill_working_set,
        "prefill_blocks": len(prefill_lbas),
        "payload_requests": payload_requests,
        "payload_blocks": payload_blocks,
        "payload_expire_blocks": payload_expire_blocks,
        "pqc_ratio": args.pqc_ratio,
        "pqc_writes": pqc_writes,
        "pqc_blocks": pqc_blocks,
        "pqc_expire_blocks": pqc_expire_blocks,
        "payload_write_fraction": payload_blocks / max(1, payload_blocks + pqc_blocks),
        "max_lba_seen": max_lba,
        "max_ts": max_ts,
        "epoch_len": args.epoch_len,
        "note": "Real FIO --write_iolog payload writes converted to QUASAR JSONL; PQC lifecycle side writes are overlaid after the benchmark trace.",
    }
    if args.summary_out:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iolog", type=Path, required=True)
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument("--dogi-out", type=Path)
    parser.add_argument("--max-events", type=int, default=200_000)
    parser.add_argument("--prefill-working-set", action="store_true")
    parser.add_argument("--pqc-ratio", type=float, default=0.0)
    parser.add_argument("--epoch-len", type=int, default=10_000)
    parser.add_argument("--pqc-lba-base", type=int, default=10_000_000)
    parser.add_argument("--pqc-lba-span", type=int, default=500_000)
    parser.add_argument("--session-jitter", type=int, default=64)
    parser.add_argument("--rotation-epochs", type=int, default=12)
    parser.add_argument("--seed", type=int, default=101)
    args = parser.parse_args()
    if args.pqc_ratio < 0:
        raise SystemExit("--pqc-ratio must be non-negative")
    summary = convert(args)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
