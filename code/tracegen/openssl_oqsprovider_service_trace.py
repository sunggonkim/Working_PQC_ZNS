#!/usr/bin/env python3
"""Generate QUASAR traces from OpenSSL 3 + oqsprovider C API measurements.

Unlike ``openssl_oqsprovider_workload.py``, this path does not rely on the
OpenSSL CLI for KEM operations. It compiles and runs a tiny C helper that uses
``EVP_PKEY_encapsulate`` and ``EVP_PKEY_decapsulate`` directly. This closes the
local KEM encap/decap measurement gap for hosts whose ``pkeyutl`` lacks
``-encap``/``-decap`` support.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
from pathlib import Path
from statistics import mean

try:
    import oqs_tls_trace as bridge
except ModuleNotFoundError:  # pragma: no cover - package import path
    from tracegen import oqs_tls_trace as bridge


SOURCE = Path(__file__).with_name("openssl_oqs_kem_sig_probe.c")


def run_checked(cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed rc={proc.returncode}: {' '.join(cmd)}\n"
            f"stdout={proc.stdout[:2000]}\nstderr={proc.stderr[:2000]}"
        )
    return proc


def compile_probe(args: argparse.Namespace) -> Path:
    compiler = shutil.which(args.cc)
    if compiler is None:
        raise SystemExit(f"compiler not found: {args.cc}")
    args.probe_bin.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        compiler,
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        f"-I{args.openssl_include_dir}",
        str(SOURCE),
        "-o",
        str(args.probe_bin),
        "-L/lib/x86_64-linux-gnu",
        "-lcrypto",
    ]
    run_checked(cmd)
    return args.probe_bin


def parse_measurements(stdout: str) -> list[dict]:
    rows = []
    for line in stdout.splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def canonical_kem(name: str) -> str:
    return bridge.normalize_algorithm(name, bridge.KEM_SIZES, "ML-KEM-768")


def canonical_sig(name: str) -> str:
    return bridge.normalize_algorithm(name, bridge.SIG_SIZES, "ML-DSA-65")


def event_rows_from_measurements(
    measurements: list[dict],
    *,
    kem: str,
    sig: str,
    tenants: int,
    session_spacing_ms: int,
    session_min_ms: int,
    session_max_ms: int,
    payload_min_bytes: int,
    payload_max_bytes: int,
    seed: int,
    event_type: str,
    provider_module_path: Path,
    probe_bin: Path,
) -> list[dict]:
    rng = random.Random(seed)
    events = []
    for idx, row in enumerate(measurements):
        ts = idx * session_spacing_ms
        session_len = rng.randint(session_min_ms, session_max_ms)
        payload_bytes = rng.randint(payload_min_bytes, payload_max_bytes)
        events.append(
            {
                "ts": ts,
                "event": event_type,
                "session_id": f"osslkem{idx}",
                "tenant_id": f"tenant{idx % tenants}",
                "kem": kem,
                "sig": sig,
                "payload_bytes": payload_bytes,
                "session_end_ts": ts + session_len,
                "provider_module_path": str(provider_module_path),
                "probe_bin": str(probe_bin),
                **row,
            }
        )
    return events


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, sort_keys=True) + "\n")


def summarize(events: list[dict], trace_summary: dict, *, args: argparse.Namespace) -> dict:
    def avg(field: str) -> float:
        return mean(float(row[field]) for row in events) if events else 0.0

    first = events[0] if events else {}
    return {
        "sessions": len(events),
        "provider_module_path": str(args.provider_module_path),
        "probe_bin": str(args.probe_bin),
        "kem": args.kem,
        "sig": args.sig,
        "kem_provider_name": args.kem_alg,
        "sig_provider_name": args.sig_alg,
        "all_kem_ok": all(bool(row.get("kem_ok")) for row in events),
        "all_sig_ok": all(bool(row.get("sig_ok")) for row in events),
        "kem_encap_c_api_supported": bool(events),
        "ciphertext_bytes": first.get("ciphertext_bytes", 0),
        "shared_secret_bytes": first.get("shared_secret_bytes", 0),
        "signature_bytes": first.get("signature_bytes", 0),
        "avg_kem_keygen_ns": avg("kem_keygen_ns"),
        "avg_kem_encap_ns": avg("kem_encap_ns"),
        "avg_kem_decap_ns": avg("kem_decap_ns"),
        "avg_sig_keygen_ns": avg("sig_keygen_ns"),
        "avg_sig_sign_ns": avg("sig_sign_ns"),
        "avg_sig_verify_ns": avg("sig_verify_ns"),
        "trace": trace_summary,
    }


def generate(args: argparse.Namespace) -> dict:
    args.kem = canonical_kem(args.kem_alg)
    args.sig = canonical_sig(args.sig_alg)
    probe_bin = compile_probe(args)
    env = dict(os.environ)
    env["OPENSSL_MODULES"] = str(args.provider_module_path)
    proc = run_checked([str(probe_bin), str(args.sessions), args.kem_alg, args.sig_alg], env=env)
    measurements = parse_measurements(proc.stdout)
    events = event_rows_from_measurements(
        measurements,
        kem=args.kem,
        sig=args.sig,
        tenants=args.tenants,
        session_spacing_ms=args.session_spacing_ms,
        session_min_ms=args.session_min_ms,
        session_max_ms=args.session_max_ms,
        payload_min_bytes=args.payload_min_bytes,
        payload_max_bytes=args.payload_max_bytes,
        seed=args.seed,
        event_type=args.event_type,
        provider_module_path=args.provider_module_path,
        probe_bin=probe_bin,
    )
    write_jsonl(args.event_log, events)

    crypto_events = [bridge.event_from_row(event) for event in events]
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
    summary = summarize(events, trace_summary, args=args)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=120)
    parser.add_argument("--event-type", default="tls_handshake")
    parser.add_argument("--kem-alg", default="mlkem768")
    parser.add_argument("--sig-alg", default="mldsa65")
    parser.add_argument("--tenants", type=int, default=8)
    parser.add_argument("--session-spacing-ms", type=int, default=2)
    parser.add_argument("--session-min-ms", type=int, default=40)
    parser.add_argument("--session-max-ms", type=int, default=200)
    parser.add_argument("--payload-min-bytes", type=int, default=0)
    parser.add_argument("--payload-max-bytes", type=int, default=4096)
    parser.add_argument("--epoch-len-ms", type=int, default=64)
    parser.add_argument("--rotation-epochs", type=int, default=2)
    parser.add_argument("--lba-space", type=int, default=2_000_000)
    parser.add_argument("--seed", type=int, default=1709)
    parser.add_argument("--cc", default="gcc")
    parser.add_argument("--openssl-include-dir", type=Path, default=Path("artifacts/external/openssl3-include"))
    parser.add_argument("--provider-module-path", type=Path, default=Path("artifacts/external/oqs-provider/_build-local/lib").resolve())
    parser.add_argument("--probe-bin", type=Path, default=Path("artifacts/results/openssl-oqsprovider-kem-service/bin/openssl_oqs_kem_sig_probe"))
    parser.add_argument("--event-log", type=Path, default=Path("artifacts/traces/openssl-oqsprovider-kem-service/events.jsonl"))
    parser.add_argument("--jsonl", type=Path, default=Path("artifacts/traces/openssl-oqsprovider-kem-service/trace.jsonl"))
    parser.add_argument("--dogi-trace", type=Path, default=Path("artifacts/traces/openssl-oqsprovider-kem-service/trace.dogi"))
    parser.add_argument("--summary-out", type=Path, default=Path("artifacts/results/openssl-oqsprovider-kem-service/summary.json"))
    args = parser.parse_args()

    summary = generate(args)
    print(f"wrote event_log={args.event_log}")
    print(f"wrote jsonl={args.jsonl}")
    print(f"wrote dogi_trace={args.dogi_trace}")
    print(f"wrote summary={args.summary_out}")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
