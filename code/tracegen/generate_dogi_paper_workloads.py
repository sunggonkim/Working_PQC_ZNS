#!/usr/bin/env python3
"""Generate DOGI-paper-shaped mixed PQC/ZNS workload traces.

This is not a replacement for the original private traces used by DOGI. It is a
reproducible, paper-shaped suite that mirrors the workload axes described in the
DOGI FAST paper:

- S-type/static-skew: FIO Zipf, YCSB-A, YCSB-F.
- D-type/dynamic: Varmail, Alibaba Cloud I/O, Microsoft Exchange.

The suite also includes a FAST-style `sysbench-oltp` stress profile. DOGI does
not use Sysbench in its evaluation, but OLTP/MySQL-style update pressure is
common in storage papers and is useful for testing whether PQC death cohorts
remain visible under database-like overwrite churn.

Each generated trace starts with a prefilled working set, then replays payload
overwrites and overlays PQC metadata writes. This lets us ask whether QUASAR is
only helping on FIO or whether the PQC lifecycle signal helps across the same
families of situations DOGI evaluates.
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


@dataclass(frozen=True)
class WorkloadSpec:
    name: str
    dogi_label: str
    category: str
    description: str
    working_set_blocks: int
    hot_set_blocks: int
    hot_fraction: float
    phase_len: int
    max_payload_blocks: int
    dynamic: bool
    pqc_epoch_len: int
    session_jitter: int
    rotation_epochs: int
    kem_weight: float
    secret_weight: float
    sig_weight: float
    cert_weight: float


WORKLOADS = [
    WorkloadSpec(
        name="fio-zipf",
        dogi_label="FIO",
        category="S-type",
        description="4KiB static Zipf-like skew, matching DOGI's FIO axis.",
        working_set_blocks=48_000,
        hot_set_blocks=6_000,
        hot_fraction=0.92,
        phase_len=50_000,
        max_payload_blocks=1,
        dynamic=False,
        pqc_epoch_len=10_000,
        session_jitter=32,
        rotation_epochs=12,
        kem_weight=0.40,
        secret_weight=0.34,
        sig_weight=0.18,
        cert_weight=0.08,
    ),
    WorkloadSpec(
        name="ycsb-a",
        dogi_label="Y-A",
        category="S-type",
        description="Static hot records with frequent updates, modeling YCSB-A on MySQL.",
        working_set_blocks=56_000,
        hot_set_blocks=8_000,
        hot_fraction=0.86,
        phase_len=50_000,
        max_payload_blocks=2,
        dynamic=False,
        pqc_epoch_len=12_000,
        session_jitter=48,
        rotation_epochs=12,
        kem_weight=0.38,
        secret_weight=0.30,
        sig_weight=0.20,
        cert_weight=0.12,
    ),
    WorkloadSpec(
        name="ycsb-f",
        dogi_label="Y-F",
        category="S-type",
        description="Read-modify-write style static skew, approximated by repeated hot updates.",
        working_set_blocks=52_000,
        hot_set_blocks=7_500,
        hot_fraction=0.90,
        phase_len=50_000,
        max_payload_blocks=2,
        dynamic=False,
        pqc_epoch_len=12_000,
        session_jitter=64,
        rotation_epochs=12,
        kem_weight=0.42,
        secret_weight=0.32,
        sig_weight=0.17,
        cert_weight=0.09,
    ),
    WorkloadSpec(
        name="varmail",
        dogi_label="Var",
        category="D-type",
        description="Filebench Varmail-like changing mail-file hot regions and variable writes.",
        working_set_blocks=44_000,
        hot_set_blocks=5_500,
        hot_fraction=0.74,
        phase_len=8_000,
        max_payload_blocks=8,
        dynamic=True,
        pqc_epoch_len=8_000,
        session_jitter=48,
        rotation_epochs=8,
        kem_weight=0.34,
        secret_weight=0.28,
        sig_weight=0.26,
        cert_weight=0.12,
    ),
    WorkloadSpec(
        name="alibaba",
        dogi_label="Ali",
        category="D-type",
        description="Cloud I/O-like phase changes with shifting hot tenants and broad cold writes.",
        working_set_blocks=64_000,
        hot_set_blocks=9_000,
        hot_fraction=0.68,
        phase_len=6_000,
        max_payload_blocks=16,
        dynamic=True,
        pqc_epoch_len=10_000,
        session_jitter=96,
        rotation_epochs=10,
        kem_weight=0.36,
        secret_weight=0.26,
        sig_weight=0.24,
        cert_weight=0.14,
    ),
    WorkloadSpec(
        name="exchange",
        dogi_label="Ex",
        category="D-type",
        description="Microsoft Exchange-like dynamic mail/database updates with moderate locality.",
        working_set_blocks=42_000,
        hot_set_blocks=7_000,
        hot_fraction=0.70,
        phase_len=7_000,
        max_payload_blocks=8,
        dynamic=True,
        pqc_epoch_len=9_000,
        session_jitter=96,
        rotation_epochs=10,
        kem_weight=0.35,
        secret_weight=0.27,
        sig_weight=0.25,
        cert_weight=0.13,
    ),
    WorkloadSpec(
        name="sysbench-oltp",
        dogi_label="SB",
        category="DB-type",
        description=(
            "FAST-style Sysbench OLTP update pressure: static hot table rows, "
            "periodic hot-range shifts, and short PQC authentication epochs."
        ),
        working_set_blocks=72_000,
        hot_set_blocks=10_000,
        hot_fraction=0.82,
        phase_len=5_000,
        max_payload_blocks=4,
        dynamic=True,
        pqc_epoch_len=4_000,
        session_jitter=24,
        rotation_epochs=8,
        kem_weight=0.43,
        secret_weight=0.35,
        sig_weight=0.14,
        cert_weight=0.08,
    ),
]


@dataclass(order=True)
class PendingExpire:
    ts: int
    object_id: int
    lba: int
    size_blocks: int


def tag_for_ratio(ratio: float) -> str:
    return f"pqc{int(round(ratio * 10000)):04d}"


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


def choose_pqc(spec: WorkloadSpec, rng: random.Random) -> tuple[str, int]:
    total = spec.kem_weight + spec.secret_weight + spec.sig_weight + spec.cert_weight
    x = rng.random() * total
    if x < spec.kem_weight:
        return "KEM_ARTIFACT", rng.randint(1, 3)
    x -= spec.kem_weight
    if x < spec.secret_weight:
        return "EPHEMERAL_SECRET", 1
    x -= spec.secret_weight
    if x < spec.sig_weight:
        return "SIGNATURE_LOG", rng.randint(1, 4)
    return "CERT_METADATA", rng.randint(2, 8)


def pqc_expire_ts(spec: WorkloadSpec, intent: str, ts: int, rng: random.Random) -> int | None:
    epoch = ts // spec.pqc_epoch_len
    if intent in SECRET_INTENTS:
        jitter = rng.randint(0, spec.session_jitter) if spec.session_jitter else 0
        return (epoch + 1) * spec.pqc_epoch_len + jitter
    if intent == "CERT_METADATA":
        return ((epoch // spec.rotation_epochs) + 1) * spec.rotation_epochs * spec.pqc_epoch_len
    return None


def build_zipf_cdf(n: int, theta: float = 1.0) -> list[float]:
    weights = [1.0 / ((idx + 1) ** theta) for idx in range(n)]
    total = sum(weights)
    cdf: list[float] = []
    acc = 0.0
    for weight in weights:
        acc += weight / total
        cdf.append(acc)
    cdf[-1] = 1.0
    return cdf


def sample_rank(cdf: list[float], rng: random.Random) -> int:
    x = rng.random()
    lo = 0
    hi = len(cdf) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cdf[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def payload_lba(spec: WorkloadSpec, ts: int, rng: random.Random, cdf: list[float]) -> int:
    phase = ts // max(1, spec.phase_len)
    if spec.dynamic:
        base = (phase * max(1, spec.hot_set_blocks * 3)) % spec.working_set_blocks
    else:
        base = 0
    if rng.random() < spec.hot_fraction:
        rank = sample_rank(cdf, rng)
        return (base + rank) % spec.working_set_blocks
    return rng.randrange(spec.working_set_blocks)


def payload_size(spec: WorkloadSpec, rng: random.Random) -> int:
    if spec.max_payload_blocks <= 1:
        return 1
    x = rng.random()
    if x < 0.70:
        return 1
    if x < 0.90:
        return min(spec.max_payload_blocks, 4)
    return rng.randint(1, spec.max_payload_blocks)


def maybe_inject_pqc(
    *,
    out,
    spec: WorkloadSpec,
    rng: random.Random,
    ts: int,
    pqc_ratio: float,
    next_object_id: int,
    pqc_lba_base: int,
    expires: list[PendingExpire],
) -> tuple[int, int, int]:
    injected = 0
    injected_blocks = 0
    whole = int(pqc_ratio)
    target = whole + (1 if rng.random() < (pqc_ratio - whole) else 0)
    for _ in range(target):
        intent, size_blocks = choose_pqc(spec, rng)
        epoch_id = ts // spec.pqc_epoch_len
        lba = pqc_lba_base + rng.randrange(max(1, spec.working_set_blocks * 4))
        expire_ts = pqc_expire_ts(spec, intent, ts, rng)
        object_id = next_object_id
        next_object_id += 1
        injected += 1
        injected_blocks += size_blocks
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
        if expire_ts is not None:
            heapq.heappush(expires, PendingExpire(expire_ts, object_id, lba, size_blocks))
    return next_object_id, injected, injected_blocks


def generate_one(
    *,
    spec: WorkloadSpec,
    events: int,
    pqc_ratio: float,
    seed: int,
    out_path: Path,
    summary_path: Path,
) -> None:
    rng = random.Random(seed)
    cdf = build_zipf_cdf(spec.hot_set_blocks)
    expires: list[PendingExpire] = []
    live_by_lba: dict[int, int] = {}
    next_object_id = 1
    payload_writes = 0
    payload_blocks = 0
    payload_expire_blocks = 0
    pqc_writes = 0
    pqc_blocks = 0
    pqc_expire_blocks = 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as out:
        for lba in range(spec.working_set_blocks):
            object_id = next_object_id
            next_object_id += 1
            live_by_lba[lba] = object_id
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
                    "cohort_id": "payload",
                    "tenant_id": "tenant0",
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

            size_blocks = payload_size(spec, rng)
            start_lba = payload_lba(spec, ts, rng, cdf)
            for offset in range(size_blocks):
                lba = (start_lba + offset) % spec.working_set_blocks
                previous = live_by_lba.get(lba)
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
                    payload_expire_blocks += 1
                object_id = next_object_id
                next_object_id += 1
                live_by_lba[lba] = object_id
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
                        "cohort_id": "payload",
                        "tenant_id": "tenant0",
                        "confidence": "exact",
                        "expire_ts": None,
                    },
                )
            payload_writes += 1
            payload_blocks += size_blocks

            next_object_id, injected, injected_blocks = maybe_inject_pqc(
                out=out,
                spec=spec,
                rng=rng,
                ts=ts,
                pqc_ratio=pqc_ratio,
                next_object_id=next_object_id,
                pqc_lba_base=10_000_000 + 10 * spec.working_set_blocks,
                expires=expires,
            )
            pqc_writes += injected
            pqc_blocks += injected_blocks

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
        "workload": spec.name,
        "dogi_label": spec.dogi_label,
        "category": spec.category,
        "description": spec.description,
        "events": events,
        "pqc_ratio": pqc_ratio,
        "payload_write_requests": payload_writes,
        "payload_write_blocks": payload_blocks,
        "payload_expire_blocks": payload_expire_blocks,
        "pqc_writes": pqc_writes,
        "pqc_write_blocks": pqc_blocks,
        "pqc_expire_blocks": pqc_expire_blocks,
        "payload_write_fraction": payload_blocks / max(1, payload_blocks + pqc_blocks),
        "prefill_blocks": spec.working_set_blocks,
        "working_set_blocks": spec.working_set_blocks,
        "hot_set_blocks": spec.hot_set_blocks,
        "hot_fraction": spec.hot_fraction,
        "phase_len": spec.phase_len,
        "dynamic": spec.dynamic,
        "trace": str(out_path),
        "note": (
            "DOGI-paper-shaped synthetic trace; real public DOGI artifact currently provides FIO directly. "
            "The sysbench-oltp profile is FAST-style DB stress, not a DOGI-paper workload."
        ),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


def parse_ratios(raw: str) -> list[float]:
    ratios = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        ratios.append(float(item))
    if not ratios:
        raise argparse.ArgumentTypeError("at least one ratio is required")
    return ratios


def parse_workloads(raw: str) -> list[str]:
    workloads = [item.strip() for item in raw.split(",") if item.strip()]
    if not workloads:
        raise argparse.ArgumentTypeError("at least one workload is required")
    return workloads


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=80_000)
    parser.add_argument("--ratios", type=parse_ratios, default=parse_ratios("0,0.01,0.05,0.20"))
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/traces/dogi-paper-workloads"))
    parser.add_argument("--summary-dir", type=Path, default=Path("artifacts/results/dogi-paper-workloads/summaries"))
    parser.add_argument("--workloads", type=parse_workloads, default=[])
    parser.add_argument("--seed", type=int, default=41)
    args = parser.parse_args()

    if args.events <= 0:
        raise SystemExit("--events must be positive")
    for ratio in args.ratios:
        if ratio < 0:
            raise SystemExit("--ratios must be non-negative")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.summary_dir.mkdir(parents=True, exist_ok=True)
    specs = WORKLOADS
    if args.workloads:
        by_name = {spec.name: spec for spec in WORKLOADS}
        missing = [name for name in args.workloads if name not in by_name]
        if missing:
            raise SystemExit(f"unknown workload(s): {','.join(missing)}")
        specs = [by_name[name] for name in args.workloads]
    for spec_idx, spec in enumerate(specs):
        for ratio_idx, ratio in enumerate(args.ratios):
            tag = tag_for_ratio(ratio)
            generate_one(
                spec=spec,
                events=args.events,
                pqc_ratio=ratio,
                seed=args.seed + spec_idx * 1009 + ratio_idx * 97,
                out_path=args.out_dir / f"{spec.name}-{tag}.jsonl",
                summary_path=args.summary_dir / f"{spec.name}-{tag}-summary.json",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
