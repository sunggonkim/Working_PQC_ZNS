#!/usr/bin/env python3
"""Convert DOGI/MiDAS FIO traces into QUASAR JSONL, optionally overlaying PQC.

DOGI's public FIO trace is an overwrite workload:

    <timestamp> <request_type> <lba_4k> <request_size_bytes> [stream]

The QUASAR simulator models explicit object expiration, so this converter turns
each rewritten 4 KiB LBA into:

    expire(previous_version_of_lba), write(new_version_of_lba)

When --pqc-ratio is non-zero, the converter injects PQC metadata writes on top
of the same FIO timeline. This creates a more realistic payload-dominant
workload: QUASAR should not magically improve the normal FIO payload; any win
should come from isolating the PQC death cohorts.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path


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
    if intent in {"KEM_ARTIFACT", "EPHEMERAL_SECRET"}:
        return "EPOCH"
    if intent == "CERT_METADATA":
        return "ROTATION"
    if intent == "SIGNATURE_LOG":
        return "APPEND_ONLY"
    return "UNKNOWN"


def security_class(intent: str) -> str:
    if intent in {"KEM_ARTIFACT", "EPHEMERAL_SECRET"}:
        return "SECRET"
    if intent in {"SIGNATURE_LOG", "CERT_METADATA"}:
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


def pqc_expire_ts(intent: str, ts: int, epoch_len: int, rng: random.Random, session_jitter: int, rotation_epochs: int) -> int | None:
    epoch = ts // epoch_len
    if intent in {"KEM_ARTIFACT", "EPHEMERAL_SECRET"}:
        return (epoch + 1) * epoch_len + (rng.randint(0, session_jitter) if session_jitter else 0)
    if intent == "CERT_METADATA":
        return ((epoch // rotation_epochs) + 1) * rotation_epochs * epoch_len
    return None


def parse_trace_line(line: str) -> tuple[int, int, int, int] | None:
    parts = line.split()
    if len(parts) < 4:
        return None
    ts = int(float(parts[0]))
    req_type = int(parts[1])
    lba = int(parts[2])
    size_bytes = int(parts[3])
    return ts, req_type, lba, size_bytes


def maybe_inject_pqc(
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
    injected = 0
    whole = int(pqc_ratio)
    fractional = pqc_ratio - whole
    target = whole + (1 if rng.random() < fractional else 0)
    for _ in range(target):
        intent, size_blocks = choose_pqc(rng)
        epoch_id = ts // epoch_len
        lba = pqc_lba_base + rng.randrange(max(1, pqc_lba_span))
        expire_ts = pqc_expire_ts(intent, ts, epoch_len, rng, session_jitter, rotation_epochs)
        object_id = next_object_id
        next_object_id += 1
        injected += 1
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
    return next_object_id, injected, sum(1 for _ in range(target))


def convert(args: argparse.Namespace) -> dict:
    rng = random.Random(args.seed)
    live_by_lba: dict[int, int] = {}
    expires: list[PendingExpire] = []
    next_object_id = 1
    fio_writes = 0
    fio_write_blocks = 0
    fio_expire_blocks = 0
    pqc_writes = 0
    pqc_write_blocks = 0
    pqc_expire_blocks = 0
    prefill_blocks = 0
    max_lba = 0
    max_ts = 0

    args.jsonl.parent.mkdir(parents=True, exist_ok=True)
    if args.dogi_out:
        args.dogi_out.parent.mkdir(parents=True, exist_ok=True)

    prefill_lbas: list[int] = []
    if args.prefill_working_set:
        working_set: set[int] = set()
        seen_writes = 0
        with args.dogi_trace.open("r", encoding="utf-8", errors="replace") as src:
            for line in src:
                parsed = parse_trace_line(line)
                if parsed is None:
                    continue
                _, req_type, lba, size_bytes = parsed
                if req_type != 1:
                    continue
                size_blocks = max(1, math.ceil(size_bytes / 4096))
                for offset in range(size_blocks):
                    working_set.add(lba + offset)
                seen_writes += 1
                if seen_writes >= args.max_fio_writes:
                    break
        prefill_lbas = sorted(working_set)

    dogi_out = args.dogi_out.open("w", encoding="utf-8") if args.dogi_out else None
    try:
        with args.dogi_trace.open("r", encoding="utf-8", errors="replace") as src, args.jsonl.open("w", encoding="utf-8") as out:
            for block_lba in prefill_lbas:
                object_id = next_object_id
                next_object_id += 1
                live_by_lba[block_lba] = object_id
                max_lba = max(max_lba, block_lba)
                prefill_blocks += 1
                emit(
                    out,
                    {
                        "op": "prefill",
                        "ts": 0,
                        "object_id": object_id,
                        "lba": block_lba,
                        "size_blocks": 1,
                        "intent": "PAYLOAD",
                        "epoch_id": 0,
                        "expire_class": "UNKNOWN",
                        "security_class": "PAYLOAD",
                        "cohort_id": "payload",
                        "tenant_id": "tenant0",
                        "confidence": "exact",
                        "expire_ts": None,
                    },
                )

            for line in src:
                parsed = parse_trace_line(line)
                if parsed is None:
                    continue
                trace_ts, req_type, lba, size_bytes = parsed
                if req_type != 1:
                    continue
                ts = fio_writes + (1 if prefill_lbas else 0) if args.logical_time else trace_ts
                max_ts = max(max_ts, ts)
                size_blocks = max(1, math.ceil(size_bytes / 4096))

                while expires and expires[0].ts <= ts:
                    item = heapq.heappop(expires)
                    emit(
                        out,
                        {
                            "op": "expire",
                            "ts": ts,
                            "object_id": item.object_id,
                            "lba": item.lba,
                            "size_blocks": item.size_blocks,
                        },
                    )
                    pqc_expire_blocks += item.size_blocks
                    if dogi_out and args.dogi_delete_markers:
                        dogi_out.write(f"{ts} 1 {item.lba} 4096\n")

                for offset in range(size_blocks):
                    block_lba = lba + offset
                    max_lba = max(max_lba, block_lba)
                    previous = live_by_lba.get(block_lba)
                    if previous is not None:
                        emit(
                            out,
                            {
                                "op": "expire",
                                "ts": ts,
                                "object_id": previous,
                                "lba": block_lba,
                                "size_blocks": 1,
                            },
                        )
                        fio_expire_blocks += 1
                    object_id = next_object_id
                    next_object_id += 1
                    live_by_lba[block_lba] = object_id
                    emit(
                        out,
                        {
                            "op": "write",
                            "ts": ts,
                            "object_id": object_id,
                            "lba": block_lba,
                            "size_blocks": 1,
                            "intent": "PAYLOAD",
                            "epoch_id": 0,
                            "expire_class": "UNKNOWN",
                            "security_class": "PAYLOAD",
                            "cohort_id": "payload",
                            "tenant_id": "tenant0",
                            "confidence": "exact",
                            "expire_ts": None,
                        },
                    )
                    if dogi_out:
                        dogi_out.write(f"{ts} 1 {block_lba} 4096\n")

                fio_writes += 1
                fio_write_blocks += size_blocks

                next_object_id, injected, _ = maybe_inject_pqc(
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
                pqc_writes += injected
                # Count blocks from the emitted write rows by reconstructing the deterministic mix is messy;
                # update from output size during injection by scanning the pending/new rows is overkill, so
                # approximate with object metadata below in a second pass is avoided. This field is not used
                # for simulator correctness.

                if fio_writes >= args.max_fio_writes:
                    break

            drain_ts = max_ts + 1
            while expires:
                item = heapq.heappop(expires)
                ts = max(drain_ts, item.ts)
                emit(
                    out,
                    {
                        "op": "expire",
                        "ts": ts,
                        "object_id": item.object_id,
                        "lba": item.lba,
                        "size_blocks": item.size_blocks,
                    },
                )
                pqc_expire_blocks += item.size_blocks
                if dogi_out and args.dogi_delete_markers:
                    dogi_out.write(f"{ts} 1 {item.lba} 4096\n")
    finally:
        if dogi_out:
            dogi_out.close()

    # Compute PQC write blocks from the generated JSONL once for an exact summary.
    with args.jsonl.open("r", encoding="utf-8") as src:
        for line in src:
            row = json.loads(line)
            if row.get("op") == "write" and row.get("intent") != "PAYLOAD":
                pqc_write_blocks += int(row["size_blocks"])

    return {
        "source_dogi_trace": str(args.dogi_trace),
        "jsonl": str(args.jsonl),
        "dogi_out": str(args.dogi_out) if args.dogi_out else None,
        "max_fio_writes": args.max_fio_writes,
        "prefill_working_set": args.prefill_working_set,
        "prefill_blocks": prefill_blocks,
        "fio_writes": fio_writes,
        "fio_write_blocks": fio_write_blocks,
        "fio_expire_blocks": fio_expire_blocks,
        "pqc_ratio": args.pqc_ratio,
        "pqc_writes": pqc_writes,
        "pqc_write_blocks": pqc_write_blocks,
        "pqc_expire_blocks": pqc_expire_blocks,
        "payload_write_fraction": fio_write_blocks / max(1, fio_write_blocks + pqc_write_blocks),
        "max_lba_seen": max_lba,
        "max_ts": max_ts,
        "epoch_len": args.epoch_len,
        "note": "FIO overwrites are converted to explicit expire+write events; PQC is overlaid as hinted metadata.",
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dogi-trace", type=Path, required=True)
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--dogi-out", type=Path)
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument("--max-fio-writes", type=int, default=200_000)
    parser.add_argument("--prefill-working-set", action="store_true")
    parser.add_argument("--pqc-ratio", type=float, default=0.0, help="Expected PQC metadata writes per FIO write.")
    parser.add_argument("--epoch-len", type=int, default=10_000)
    parser.add_argument("--pqc-lba-base", type=int, default=2_000_000)
    parser.add_argument("--pqc-lba-span", type=int, default=500_000)
    parser.add_argument("--session-jitter", type=int, default=64)
    parser.add_argument("--rotation-epochs", type=int, default=12)
    parser.add_argument("--seed", type=int, default=23)
    parser.add_argument("--logical-time", action="store_true", default=True)
    parser.add_argument("--dogi-delete-markers", action="store_true")
    args = parser.parse_args()
    if args.pqc_ratio < 0:
        raise SystemExit("--pqc-ratio must be non-negative")
    summary = convert(args)
    if args.summary_out:
        write_json(args.summary_out, summary)
        print(f"wrote summary={args.summary_out}")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
