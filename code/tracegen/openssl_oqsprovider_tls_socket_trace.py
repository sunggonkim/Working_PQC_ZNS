#!/usr/bin/env python3
"""Generate QUASAR traces from OpenSSL s_server/s_client oqsprovider handshakes."""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
import subprocess
import time
from pathlib import Path
from statistics import mean

try:
    import oqs_tls_trace as bridge
except ModuleNotFoundError:  # pragma: no cover - package import path
    from tracegen import oqs_tls_trace as bridge


def pick_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def provider_env(module_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["OPENSSL_MODULES"] = str(module_path)
    return env


def run_client(args: argparse.Namespace, port: int, env: dict[str, str]) -> tuple[int, str, str, int]:
    cmd = [
        args.openssl_bin,
        "s_client",
        "-provider",
        "oqsprovider",
        "-provider",
        "default",
        "-groups",
        args.group,
        "-connect",
        f"127.0.0.1:{port}",
        "-tls1_3",
        "-brief",
    ]
    started = time.perf_counter_ns()
    proc = subprocess.run(cmd, input="Q\n", capture_output=True, text=True, env=env, check=False)
    elapsed = time.perf_counter_ns() - started
    return proc.returncode, proc.stdout, proc.stderr, elapsed


def parse_client_success(stdout: str, stderr: str) -> bool:
    text = stdout + "\n" + stderr
    return "CONNECTION ESTABLISHED" in text and "Protocol version: TLSv1.3" in text


def start_server(args: argparse.Namespace, port: int, env: dict[str, str]) -> subprocess.Popen:
    cmd = [
        args.openssl_bin,
        "s_server",
        "-provider",
        "oqsprovider",
        "-provider",
        "default",
        "-cert",
        str(args.cert),
        "-key",
        str(args.key),
        "-tls1_3",
        "-groups",
        args.group,
        "-accept",
        str(port),
        "-naccept",
        str(args.sessions),
        "-quiet",
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)


def event_rows_from_handshakes(args: argparse.Namespace, handshakes: list[dict]) -> list[dict]:
    rng = random.Random(args.seed)
    events = []
    kem = bridge.normalize_algorithm(args.group, bridge.KEM_SIZES, "ML-KEM-768")
    for idx, row in enumerate(handshakes):
        ts = idx * args.session_spacing_ms
        session_len = rng.randint(args.session_min_ms, args.session_max_ms)
        payload_bytes = rng.randint(args.payload_min_bytes, args.payload_max_bytes)
        events.append(
            {
                "ts": ts,
                "event": "tls_kem",
                "session_id": f"tlssock{idx}",
                "tenant_id": f"tenant{idx % args.tenants}",
                "kem": kem,
                "sig": "ML-DSA-65",
                "payload_bytes": payload_bytes,
                "session_end_ts": ts + session_len,
                "tls_group": args.group,
                "tls_ok": row["ok"],
                "client_returncode": row["returncode"],
                "client_elapsed_ns": row["elapsed_ns"],
            }
        )
    return events


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, sort_keys=True) + "\n")


def summarize(events: list[dict], handshakes: list[dict], trace_summary: dict, args: argparse.Namespace) -> dict:
    elapsed = [row["elapsed_ns"] for row in handshakes]
    return {
        "sessions": len(events),
        "openssl_bin": args.openssl_bin,
        "provider_module_path": str(args.provider_module_path),
        "group": args.group,
        "kem": bridge.normalize_algorithm(args.group, bridge.KEM_SIZES, "ML-KEM-768"),
        "all_tls_ok": all(row["tls_ok"] for row in events),
        "avg_client_handshake_ns": mean(elapsed) if elapsed else 0.0,
        "min_client_handshake_ns": min(elapsed) if elapsed else 0,
        "max_client_handshake_ns": max(elapsed) if elapsed else 0,
        "cert": str(args.cert),
        "key": str(args.key),
        "trace": trace_summary,
    }


def generate(args: argparse.Namespace) -> dict:
    env = provider_env(args.provider_module_path)
    port = pick_port()
    server = start_server(args, port, env)
    time.sleep(args.server_start_wait_ms / 1000.0)
    handshakes = []
    try:
        for _ in range(args.sessions):
            returncode, stdout, stderr, elapsed_ns = run_client(args, port, env)
            ok = returncode == 0 and parse_client_success(stdout, stderr)
            handshakes.append(
                {
                    "returncode": returncode,
                    "ok": ok,
                    "stdout": stdout,
                    "stderr": stderr,
                    "elapsed_ns": elapsed_ns,
                }
            )
            if not ok:
                raise RuntimeError(f"TLS client handshake failed: rc={returncode}\nstdout={stdout}\nstderr={stderr}")
        try:
            server_stdout, server_stderr = server.communicate(timeout=args.server_stop_timeout_s)
        except subprocess.TimeoutExpired:
            server.kill()
            server_stdout, server_stderr = server.communicate()
    finally:
        if server.poll() is None:
            server.kill()
            server.communicate()

    events = event_rows_from_handshakes(args, handshakes)
    write_jsonl(args.event_log, events)
    args.raw_out.parent.mkdir(parents=True, exist_ok=True)
    args.raw_out.write_text(
        json.dumps(
            {
                "server_returncode": server.returncode,
                "server_stdout": server_stdout,
                "server_stderr": server_stderr,
                "handshakes": handshakes,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

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
    summary = summarize(events, handshakes, trace_summary, args)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=60)
    parser.add_argument("--openssl-bin", default="/usr/bin/openssl")
    parser.add_argument("--provider-module-path", type=Path, default=Path("artifacts/external/oqs-provider/_build-local/lib").resolve())
    parser.add_argument("--group", default="mlkem768")
    parser.add_argument("--cert", type=Path, default=Path("artifacts/external/oqs-provider/test/servercert.pem"))
    parser.add_argument("--key", type=Path, default=Path("artifacts/external/oqs-provider/test/serverkey.pem"))
    parser.add_argument("--tenants", type=int, default=8)
    parser.add_argument("--session-spacing-ms", type=int, default=2)
    parser.add_argument("--session-min-ms", type=int, default=40)
    parser.add_argument("--session-max-ms", type=int, default=200)
    parser.add_argument("--payload-min-bytes", type=int, default=0)
    parser.add_argument("--payload-max-bytes", type=int, default=4096)
    parser.add_argument("--epoch-len-ms", type=int, default=64)
    parser.add_argument("--rotation-epochs", type=int, default=2)
    parser.add_argument("--lba-space", type=int, default=2_000_000)
    parser.add_argument("--seed", type=int, default=1717)
    parser.add_argument("--server-start-wait-ms", type=int, default=700)
    parser.add_argument("--server-stop-timeout-s", type=float, default=5.0)
    parser.add_argument("--event-log", type=Path, default=Path("artifacts/traces/openssl-oqsprovider-tls-socket/events.jsonl"))
    parser.add_argument("--raw-out", type=Path, default=Path("artifacts/results/openssl-oqsprovider-tls-socket/raw.json"))
    parser.add_argument("--jsonl", type=Path, default=Path("artifacts/traces/openssl-oqsprovider-tls-socket/trace.jsonl"))
    parser.add_argument("--dogi-trace", type=Path, default=Path("artifacts/traces/openssl-oqsprovider-tls-socket/trace.dogi"))
    parser.add_argument("--summary-out", type=Path, default=Path("artifacts/results/openssl-oqsprovider-tls-socket/summary.json"))
    args = parser.parse_args()

    summary = generate(args)
    print(f"wrote event_log={args.event_log}")
    print(f"wrote raw={args.raw_out}")
    print(f"wrote jsonl={args.jsonl}")
    print(f"wrote dogi_trace={args.dogi_trace}")
    print(f"wrote summary={args.summary_out}")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
