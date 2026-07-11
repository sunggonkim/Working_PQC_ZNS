#!/usr/bin/env python3
"""Generate the synthetic PQC workload suite named in plan.md."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workload:
    name: str
    payload_ratio: float
    epoch_len: int
    session_jitter: int
    long_lived_epochs: int
    kem_weight: float
    secret_weight: float
    signature_weight: float
    cert_weight: float
    lba_mode: str = "random"


WORKLOADS = [
    Workload(
        name="pqc-tls",
        payload_ratio=0.10,
        epoch_len=1_000,
        session_jitter=32,
        long_lived_epochs=12,
        kem_weight=0.55,
        secret_weight=0.35,
        signature_weight=0.05,
        cert_weight=0.05,
    ),
    Workload(
        name="pqc-kms",
        payload_ratio=0.05,
        epoch_len=2_500,
        session_jitter=16,
        long_lived_epochs=2,
        kem_weight=0.30,
        secret_weight=0.40,
        signature_weight=0.05,
        cert_weight=0.25,
    ),
    Workload(
        name="pqc-log",
        payload_ratio=0.15,
        epoch_len=4_000,
        session_jitter=32,
        long_lived_epochs=4,
        kem_weight=0.10,
        secret_weight=0.05,
        signature_weight=0.65,
        cert_weight=0.20,
    ),
    Workload(
        name="mixed-web",
        payload_ratio=0.65,
        epoch_len=2_000,
        session_jitter=64,
        long_lived_epochs=12,
        kem_weight=0.45,
        secret_weight=0.30,
        signature_weight=0.15,
        cert_weight=0.10,
    ),
    Workload(
        name="stress-rekey",
        payload_ratio=0.25,
        epoch_len=500,
        session_jitter=0,
        long_lived_epochs=8,
        kem_weight=0.45,
        secret_weight=0.45,
        signature_weight=0.05,
        cert_weight=0.05,
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=25_000)
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/traces/workloads"))
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    generator = Path(__file__).with_name("pqc_tracegen.py")
    for idx, workload in enumerate(WORKLOADS):
        jsonl = args.out_dir / f"{workload.name}.jsonl"
        dogi = args.out_dir / f"{workload.name}.dogi"
        cmd = [
            sys.executable,
            str(generator),
            "--events",
            str(args.events),
            "--epoch-len",
            str(workload.epoch_len),
            "--payload-ratio",
            str(workload.payload_ratio),
            "--kem-weight",
            str(workload.kem_weight),
            "--secret-weight",
            str(workload.secret_weight),
            "--signature-weight",
            str(workload.signature_weight),
            "--cert-weight",
            str(workload.cert_weight),
            "--long-lived-epochs",
            str(workload.long_lived_epochs),
            "--session-jitter",
            str(workload.session_jitter),
            "--lba-mode",
            workload.lba_mode,
            "--seed",
            str(args.seed + idx),
            "--jsonl",
            str(jsonl),
            "--dogi-trace",
            str(dogi),
            "--dogi-delete-markers",
        ]
        print(" ".join(cmd))
        subprocess.run(cmd, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
