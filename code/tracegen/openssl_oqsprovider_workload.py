#!/usr/bin/env python3
"""Generate QUASAR traces from OpenSSL 3 + oqsprovider CLI measurements."""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    import oqs_tls_trace as bridge
except ModuleNotFoundError:  # pragma: no cover - package import path
    from tracegen import oqs_tls_trace as bridge


@dataclass
class OpenSslMeasuredEvent:
    ts: int
    event: str
    session_id: str
    tenant_id: str
    kem: str
    sig: str
    payload_bytes: int
    session_end_ts: int
    openssl_bin: str
    provider_module_path: str
    kem_provider_name: str
    sig_provider_name: str
    kem_private_pem_bytes: int
    kem_public_pem_bytes: int
    sig_private_pem_bytes: int
    sig_public_pem_bytes: int
    signature_bytes: int
    kem_keypair_ns: int
    kem_pubout_ns: int
    sig_keypair_ns: int
    sig_pubout_ns: int
    sig_sign_ns: int
    sig_verify_ns: int
    sig_ok: bool


def run_cmd(cmd: list[str], *, env: dict[str, str], input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=input_bytes, capture_output=True, check=False, env=env)


def run_checked(cmd: list[str], *, env: dict[str, str], input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    proc = run_cmd(cmd, env=env, input_bytes=input_bytes)
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed rc={proc.returncode}: {' '.join(cmd)}\n"
            f"stdout={proc.stdout[:1000]!r}\nstderr={proc.stderr[:1000]!r}"
        )
    return proc


def time_checked(cmd: list[str], *, env: dict[str, str], input_bytes: bytes | None = None) -> tuple[int, subprocess.CompletedProcess]:
    started = time.perf_counter_ns()
    proc = run_checked(cmd, env=env, input_bytes=input_bytes)
    return time.perf_counter_ns() - started, proc


def normalize_provider_alg(name: str) -> str:
    return name.lower().replace("-", "")


def canonical_kem(name: str) -> str:
    normalized = normalize_provider_alg(name)
    if normalized == "mlkem512":
        return "ML-KEM-512"
    if normalized == "mlkem768":
        return "ML-KEM-768"
    if normalized == "mlkem1024":
        return "ML-KEM-1024"
    return name


def canonical_sig(name: str) -> str:
    normalized = normalize_provider_alg(name)
    if normalized == "mldsa44":
        return "ML-DSA-44"
    if normalized == "mldsa65":
        return "ML-DSA-65"
    if normalized == "mldsa87":
        return "ML-DSA-87"
    return name


def provider_env(module_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["OPENSSL_MODULES"] = str(module_path)
    return env


def probe_openssl(openssl_bin: str, module_path: Path, kem_alg: str, sig_alg: str) -> dict:
    env = provider_env(module_path)
    providers = run_cmd([openssl_bin, "list", "-providers", "-provider", "oqsprovider", "-provider", "default"], env=env)
    kems = run_cmd([openssl_bin, "list", "-kem-algorithms", "-provider", "oqsprovider", "-provider", "default"], env=env)
    sigs = run_cmd([openssl_bin, "list", "-signature-algorithms", "-provider", "oqsprovider", "-provider", "default"], env=env)
    kem_token = normalize_provider_alg(kem_alg)
    sig_token = normalize_provider_alg(sig_alg)
    return {
        "openssl_bin": openssl_bin,
        "provider_module_path": str(module_path),
        "providers_returncode": providers.returncode,
        "providers_stdout": providers.stdout.decode("utf-8", errors="replace"),
        "providers_stderr": providers.stderr.decode("utf-8", errors="replace"),
        "kem_returncode": kems.returncode,
        "signature_returncode": sigs.returncode,
        "kem_provider_detected": kem_token in kems.stdout.decode("utf-8", errors="ignore").lower().replace("-", ""),
        "sig_provider_detected": sig_token in sigs.stdout.decode("utf-8", errors="ignore").lower().replace("-", ""),
    }


def measure_event(
    idx: int,
    *,
    args: argparse.Namespace,
    env: dict[str, str],
    work_dir: Path,
    rng: random.Random,
) -> OpenSslMeasuredEvent:
    session_id = f"ossl{idx}"
    tenant_id = f"tenant{idx % args.tenants}"
    ts = idx * args.session_spacing_ms
    payload_bytes = rng.randint(args.payload_min_bytes, args.payload_max_bytes)
    session_len = rng.randint(args.session_min_ms, args.session_max_ms)
    msg = f"quasar-oqsprovider-session-{idx}".encode("utf-8")

    kem_key = work_dir / f"{session_id}-{args.kem_alg}.key"
    kem_pub = work_dir / f"{session_id}-{args.kem_alg}.pub"
    sig_key = work_dir / f"{session_id}-{args.sig_alg}.key"
    sig_pub = work_dir / f"{session_id}-{args.sig_alg}.pub"
    msg_path = work_dir / f"{session_id}.msg"
    sig_path = work_dir / f"{session_id}.sig"
    msg_path.write_bytes(msg)

    kem_keypair_ns, _ = time_checked(
        [
            args.openssl_bin,
            "genpkey",
            "-provider",
            "oqsprovider",
            "-provider",
            "default",
            "-algorithm",
            args.kem_alg,
            "-out",
            str(kem_key),
        ],
        env=env,
    )
    kem_pubout_ns, _ = time_checked(
        [
            args.openssl_bin,
            "pkey",
            "-provider",
            "oqsprovider",
            "-provider",
            "default",
            "-in",
            str(kem_key),
            "-pubout",
            "-out",
            str(kem_pub),
        ],
        env=env,
    )
    sig_keypair_ns, _ = time_checked(
        [
            args.openssl_bin,
            "genpkey",
            "-provider",
            "oqsprovider",
            "-provider",
            "default",
            "-algorithm",
            args.sig_alg,
            "-out",
            str(sig_key),
        ],
        env=env,
    )
    sig_pubout_ns, _ = time_checked(
        [
            args.openssl_bin,
            "pkey",
            "-provider",
            "oqsprovider",
            "-provider",
            "default",
            "-in",
            str(sig_key),
            "-pubout",
            "-out",
            str(sig_pub),
        ],
        env=env,
    )
    sig_sign_ns, _ = time_checked(
        [
            args.openssl_bin,
            "pkeyutl",
            "-provider",
            "oqsprovider",
            "-provider",
            "default",
            "-sign",
            "-inkey",
            str(sig_key),
            "-in",
            str(msg_path),
            "-out",
            str(sig_path),
        ],
        env=env,
    )
    sig_verify_ns, verify_proc = time_checked(
        [
            args.openssl_bin,
            "pkeyutl",
            "-provider",
            "oqsprovider",
            "-provider",
            "default",
            "-verify",
            "-pubin",
            "-inkey",
            str(sig_pub),
            "-in",
            str(msg_path),
            "-sigfile",
            str(sig_path),
        ],
        env=env,
    )

    return OpenSslMeasuredEvent(
        ts=ts,
        event=args.event_type,
        session_id=session_id,
        tenant_id=tenant_id,
        kem=canonical_kem(args.kem_alg),
        sig=canonical_sig(args.sig_alg),
        payload_bytes=payload_bytes,
        session_end_ts=ts + session_len,
        openssl_bin=args.openssl_bin,
        provider_module_path=str(args.provider_module_path),
        kem_provider_name=args.kem_alg,
        sig_provider_name=args.sig_alg,
        kem_private_pem_bytes=kem_key.stat().st_size,
        kem_public_pem_bytes=kem_pub.stat().st_size,
        sig_private_pem_bytes=sig_key.stat().st_size,
        sig_public_pem_bytes=sig_pub.stat().st_size,
        signature_bytes=sig_path.stat().st_size,
        kem_keypair_ns=kem_keypair_ns,
        kem_pubout_ns=kem_pubout_ns,
        sig_keypair_ns=sig_keypair_ns,
        sig_pubout_ns=sig_pubout_ns,
        sig_sign_ns=sig_sign_ns,
        sig_verify_ns=sig_verify_ns,
        sig_ok=b"Signature Verified Successfully" in verify_proc.stdout,
    )


def write_event_log(path: Path, events: list[OpenSslMeasuredEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        for event in events:
            out.write(json.dumps(asdict(event), sort_keys=True) + "\n")


def summarize(events: list[OpenSslMeasuredEvent], probe: dict, trace_summary: dict) -> dict:
    if not events:
        return {"sessions": 0, "probe": probe, "trace": trace_summary}

    def avg(field: str) -> float:
        return sum(getattr(event, field) for event in events) / len(events)

    first = events[0]
    return {
        "sessions": len(events),
        "openssl_bin": first.openssl_bin,
        "provider_module_path": first.provider_module_path,
        "kem": first.kem,
        "sig": first.sig,
        "kem_provider_name": first.kem_provider_name,
        "sig_provider_name": first.sig_provider_name,
        "all_sig_ok": all(event.sig_ok for event in events),
        "avg_kem_keypair_ns": avg("kem_keypair_ns"),
        "avg_kem_pubout_ns": avg("kem_pubout_ns"),
        "avg_sig_keypair_ns": avg("sig_keypair_ns"),
        "avg_sig_pubout_ns": avg("sig_pubout_ns"),
        "avg_sig_sign_ns": avg("sig_sign_ns"),
        "avg_sig_verify_ns": avg("sig_verify_ns"),
        "kem_private_pem_bytes": first.kem_private_pem_bytes,
        "kem_public_pem_bytes": first.kem_public_pem_bytes,
        "sig_private_pem_bytes": first.sig_private_pem_bytes,
        "sig_public_pem_bytes": first.sig_public_pem_bytes,
        "signature_bytes": first.signature_bytes,
        "kem_encap_cli_supported": False,
        "probe": probe,
        "trace": trace_summary,
    }


def generate(args: argparse.Namespace) -> dict:
    env = provider_env(args.provider_module_path)
    probe = probe_openssl(args.openssl_bin, args.provider_module_path, args.kem_alg, args.sig_alg)
    if not probe["kem_provider_detected"] or not probe["sig_provider_detected"]:
        raise SystemExit("oqsprovider did not expose the requested KEM/signature algorithms")
    rng = random.Random(args.seed)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    if args.keep_keys:
        work_cm = None
        work_dir = args.work_dir
    else:
        work_cm = tempfile.TemporaryDirectory(dir=args.work_dir)
        work_dir = Path(work_cm.name)
    try:
        events = [
            measure_event(idx, args=args, env=env, work_dir=work_dir, rng=rng)
            for idx in range(args.sessions)
        ]
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
        summary = summarize(events, probe, trace_summary)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return summary
    finally:
        if work_cm is not None:
            work_cm.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=60)
    parser.add_argument("--event-type", default="kms_wrap")
    parser.add_argument("--openssl-bin", default="/usr/bin/openssl")
    parser.add_argument("--provider-module-path", type=Path, default=Path("artifacts/external/oqs-provider/_build-local/lib").resolve())
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
    parser.add_argument("--seed", type=int, default=1701)
    parser.add_argument("--work-dir", type=Path, default=Path("artifacts/results/openssl-oqsprovider/work"))
    parser.add_argument("--keep-keys", action="store_true")
    parser.add_argument("--event-log", type=Path, default=Path("artifacts/traces/openssl-oqsprovider/events.jsonl"))
    parser.add_argument("--jsonl", type=Path, default=Path("artifacts/traces/openssl-oqsprovider/trace.jsonl"))
    parser.add_argument("--dogi-trace", type=Path, default=Path("artifacts/traces/openssl-oqsprovider/trace.dogi"))
    parser.add_argument("--summary-out", type=Path, default=Path("artifacts/results/openssl-oqsprovider/summary.json"))
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
