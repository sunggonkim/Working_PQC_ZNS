#!/usr/bin/env python3
"""Generate multi-tenant PQC pressure traces for QUASAR admission control.

The DOGI/YCSB/Sysbench pressure traces are single-tenant. That makes adaptive
tenant binning look useless. This generator creates a different stress regime:
many tenants share global cryptographic epochs, but each write still carries a
tenant label. A policy that keys only on epoch can get good WAF while mixing
tenants inside the same zone family.
"""

from __future__ import annotations

import argparse
import heapq
import json
import random
from dataclasses import dataclass
from pathlib import Path


SECRET_INTENTS = {"KEM_ARTIFACT", "EPHEMERAL_SECRET"}


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
    if x < 0.42:
        return "KEM_ARTIFACT", rng.randint(1, 3)
    if x < 0.78:
        return "EPHEMERAL_SECRET", 1
    if x < 0.92:
        return "SIGNATURE_LOG", rng.randint(1, 4)
    return "CERT_METADATA", rng.randint(2, 8)


def payload_size(rng: random.Random) -> int:
    x = rng.random()
    if x < 0.75:
        return 1
    if x < 0.95:
        return 2
    return 4


def generate_one(
    *,
    out_path: Path,
    summary_path: Path,
    events: int,
    tenants: int,
    pqc_ratio: float,
    tenant_payload_blocks: int,
    tenant_hot_blocks: int,
    epoch_len: int,
    seed: int,
) -> None:
    rng = random.Random(seed)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    expires: list[PendingExpire] = []
    live_payload: dict[tuple[int, int], int] = {}
    next_object_id = 1
    payload_blocks = 0
    pqc_blocks = 0
    pqc_writes = 0
    pqc_expire_blocks = 0

    payload_lba_base = 0
    pqc_lba_base = 100_000_000
    tenant_payload_span = tenant_payload_blocks
    tenant_pqc_span = max(tenant_payload_blocks * 4, events // max(1, tenants))

    with out_path.open("w", encoding="utf-8") as out:
        for tenant in range(tenants):
            tenant_id = f"tenant{tenant:03d}"
            base = payload_lba_base + tenant * tenant_payload_span
            for local_lba in range(tenant_payload_blocks):
                object_id = next_object_id
                next_object_id += 1
                lba = base + local_lba
                live_payload[(tenant, local_lba)] = object_id
                emit(
                    out,
                    {
                        "op": "prefill",
                        "ts": 0,
                        "object_id": object_id,
                        "lba": lba,
                        "size_blocks": 1,
                        "intent": "PAYLOAD",
                        "epoch_id": 0,
                        "expire_class": "UNKNOWN",
                        "security_class": "PAYLOAD",
                        "cohort_id": f"{tenant_id}:payload",
                        "tenant_id": tenant_id,
                        "confidence": "exact",
                        "expire_ts": None,
                    },
                )

        for ts in range(1, events + 1):
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

            tenant = rng.randrange(tenants)
            tenant_id = f"tenant{tenant:03d}"
            hot = rng.random() < 0.88
            local_lba = rng.randrange(tenant_hot_blocks if hot else tenant_payload_blocks)
            size = payload_size(rng)
            base = payload_lba_base + tenant * tenant_payload_span
            for offset in range(size):
                local = (local_lba + offset) % tenant_payload_blocks
                lba = base + local
                previous = live_payload.get((tenant, local))
                if previous is not None:
                    emit(
                        out,
                        {
                            "op": "expire",
                            "ts": ts,
                            "object_id": previous,
                            "lba": lba,
                            "size_blocks": 1,
                        },
                    )
                object_id = next_object_id
                next_object_id += 1
                live_payload[(tenant, local)] = object_id
                emit(
                    out,
                    {
                        "op": "write",
                        "ts": ts,
                        "object_id": object_id,
                        "lba": lba,
                        "size_blocks": 1,
                        "intent": "PAYLOAD",
                        "epoch_id": 0,
                        "expire_class": "UNKNOWN",
                        "security_class": "PAYLOAD",
                        "cohort_id": f"{tenant_id}:payload",
                        "tenant_id": tenant_id,
                        "confidence": "exact",
                        "expire_ts": None,
                    },
                )
                payload_blocks += 1

            whole = int(pqc_ratio)
            target = whole + (1 if rng.random() < (pqc_ratio - whole) else 0)
            for _ in range(target):
                intent, size_blocks = choose_pqc(rng)
                epoch_id = ts // epoch_len
                object_id = next_object_id
                next_object_id += 1
                lba = pqc_lba_base + tenant * tenant_pqc_span + rng.randrange(tenant_pqc_span)
                if intent in SECRET_INTENTS:
                    expire_ts = (epoch_id + 1) * epoch_len + rng.randint(0, 16)
                elif intent == "CERT_METADATA":
                    expire_ts = ((epoch_id // 8) + 1) * 8 * epoch_len
                else:
                    expire_ts = None
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
                        "cohort_id": f"{tenant_id}:{intent}:{epoch_id}",
                        "tenant_id": tenant_id,
                        "confidence": "exact",
                        "expire_ts": expire_ts,
                    },
                )
                pqc_writes += 1
                pqc_blocks += size_blocks
                if expire_ts is not None:
                    heapq.heappush(expires, PendingExpire(expire_ts, object_id, lba, size_blocks))

        drain_ts = events + 1
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

    summary = {
        "workload": out_path.stem,
        "events": events,
        "tenants": tenants,
        "pqc_ratio": pqc_ratio,
        "tenant_payload_blocks": tenant_payload_blocks,
        "tenant_hot_blocks": tenant_hot_blocks,
        "epoch_len": epoch_len,
        "payload_write_blocks": payload_blocks,
        "pqc_writes": pqc_writes,
        "pqc_write_blocks": pqc_blocks,
        "pqc_expire_blocks": pqc_expire_blocks,
        "prefill_blocks": tenants * tenant_payload_blocks,
        "trace": str(out_path),
        "note": (
            "Multi-tenant synthetic pressure trace. It is designed for QUASAR admission-control "
            "and tenant-isolation stress, not as a DOGI paper workload."
        ),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


def tag_ratio(value: float) -> str:
    return f"pqc{int(round(value * 10000)):04d}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=80_000)
    parser.add_argument("--tenants", type=int, default=32)
    parser.add_argument("--ratios", default="0.40,0.80")
    parser.add_argument("--tenant-payload-blocks", type=int, default=2048)
    parser.add_argument("--tenant-hot-blocks", type=int, default=256)
    parser.add_argument("--epoch-len", type=int, default=4000)
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/traces/multitenant-pressure"))
    parser.add_argument("--summary-dir", type=Path, default=Path("artifacts/results/multitenant-pressure/summaries"))
    parser.add_argument("--seed", type=int, default=101)
    args = parser.parse_args()

    ratios = [float(item.strip()) for item in args.ratios.split(",") if item.strip()]
    for idx, ratio in enumerate(ratios):
        stem = f"multitenant-t{args.tenants:03d}-{tag_ratio(ratio)}"
        generate_one(
            out_path=args.out_dir / f"{stem}.jsonl",
            summary_path=args.summary_dir / f"{stem}-summary.json",
            events=args.events,
            tenants=args.tenants,
            pqc_ratio=ratio,
            tenant_payload_blocks=args.tenant_payload_blocks,
            tenant_hot_blocks=args.tenant_hot_blocks,
            epoch_len=args.epoch_len,
            seed=args.seed + idx * 97,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
