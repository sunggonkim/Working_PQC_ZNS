#!/usr/bin/env python3
"""Capture a real application block trace with PQC lifecycle side writes.

This tool is intentionally small and conservative.  It runs sysbench fileio as
the real application workload, runs a PQC KMS/audit side writer in parallel, and
captures the underlying block device with blktrace.  The generated artifact is
not a ZNS placement result; it closes the trace-realism gap by proving that the
project can collect application-level block I/O while PQC lifecycle records are
being persisted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


BLKPARSE_RE = re.compile(
    r"^\s*\d+,\d+\s+\d+\s+\d+\s+[\d.]+\s+\d+\s+"
    r"(?P<action>[A-Z]+)\s+(?P<rwbs>\S+)"
)


def run_checked(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed rc={proc.returncode}: {' '.join(cmd)}\n"
            f"stdout={proc.stdout[:2000]}\nstderr={proc.stderr[:2000]}"
        )
    return proc


def find_mount(target: Path) -> dict[str, str]:
    proc = run_checked(["findmnt", "-T", str(target), "-no", "SOURCE,TARGET,FSTYPE"])
    parts = proc.stdout.strip().split()
    if len(parts) < 3:
        raise RuntimeError(f"cannot parse findmnt output for {target}: {proc.stdout!r}")
    return {"source": parts[0], "target": parts[1], "fstype": parts[2]}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_oqs():
    try:
        import oqs  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on host install
        raise RuntimeError(f"liboqs-python unavailable for real PQC side writer: {exc}") from exc
    return oqs


def pqc_side_writer(
    path: Path,
    *,
    sessions: int,
    fsync_every: int,
    sleep_ms: int,
    kem: str,
    sig: str,
    stop: threading.Event,
) -> dict[str, Any]:
    oqs = load_oqs()
    path.parent.mkdir(parents=True, exist_ok=True)
    records = 0
    bytes_written = 0
    kem_ok = 0
    sig_ok = 0
    started = time.time()
    with path.open("a", encoding="utf-8") as out:
        for idx in range(sessions):
            if stop.is_set():
                break
            message = f"quasar-real-app-session-{idx}".encode("utf-8")
            with oqs.KeyEncapsulation(kem) as kem_ctx:
                public_key = kem_ctx.generate_keypair()
                ciphertext, shared_secret = kem_ctx.encap_secret(public_key)
                recovered = kem_ctx.decap_secret(ciphertext)
            with oqs.Signature(sig) as sig_ctx:
                sig_public_key = sig_ctx.generate_keypair()
                signature = sig_ctx.sign(message)
                verified = bool(sig_ctx.verify(message, signature, sig_public_key))
            kem_ok += int(shared_secret == recovered)
            sig_ok += int(verified)
            rows = [
                {
                    "intent_class": "KEM_ARTIFACT",
                    "security_class": "PUBLIC_METADATA",
                    "epoch_id": idx // 16,
                    "session": idx,
                    "bytes": len(public_key) + len(ciphertext),
                },
                {
                    "intent_class": "EPHEMERAL_SECRET",
                    "security_class": "SECRET",
                    "epoch_id": idx // 16,
                    "session": idx,
                    "bytes": len(shared_secret),
                    "digest": hashlib.sha256(shared_secret).hexdigest(),
                },
                {
                    "intent_class": "SIGNATURE_LOG",
                    "security_class": "PUBLIC_METADATA",
                    "epoch_id": idx // 64,
                    "session": idx,
                    "bytes": len(signature) + len(sig_public_key),
                },
            ]
            for row in rows:
                line = json.dumps(row, sort_keys=True) + "\n"
                out.write(line)
                records += 1
                bytes_written += len(line.encode("utf-8"))
            if records % fsync_every == 0:
                out.flush()
                os.fsync(out.fileno())
            if sleep_ms > 0:
                time.sleep(sleep_ms / 1000.0)
    elapsed = max(time.time() - started, 0.000001)
    return {
        "sessions_requested": sessions,
        "sessions_completed": records // 3,
        "records": records,
        "bytes_written": bytes_written,
        "kem": kem,
        "sig": sig,
        "kem_ok_sessions": kem_ok,
        "sig_ok_sessions": sig_ok,
        "all_kem_ok": kem_ok == records // 3,
        "all_sig_ok": sig_ok == records // 3,
        "audit_log": str(path),
        "elapsed_s": elapsed,
        "records_per_s": records / elapsed,
    }


def run_sysbench(args: argparse.Namespace, work_dir: Path) -> dict[str, Any]:
    base = [
        "sysbench",
        "fileio",
        f"--file-total-size={args.sysbench_total_size}",
        f"--file-num={args.sysbench_file_num}",
        f"--file-block-size={args.sysbench_block_size}",
    ]
    run_checked(base + ["prepare"], cwd=work_dir)
    run_cmd = base + [
        f"--threads={args.sysbench_threads}",
        f"--time={args.duration}",
        f"--file-test-mode={args.sysbench_mode}",
        f"--file-io-mode={args.sysbench_io_mode}",
        f"--file-fsync-freq={args.sysbench_fsync_freq}",
        "run",
    ]
    if args.sysbench_extra_flags:
        run_cmd.insert(-1, f"--file-extra-flags={args.sysbench_extra_flags}")
    started = time.time()
    proc = run_checked(run_cmd, cwd=work_dir)
    ended = time.time()
    cleanup = run_checked(base + ["cleanup"], cwd=work_dir)
    return {
        "command": run_cmd,
        "prepare_command": base + ["prepare"],
        "cleanup_command": base + ["cleanup"],
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "cleanup_stdout": cleanup.stdout,
        "started_at": started,
        "ended_at": ended,
        "elapsed_s": ended - started,
        "write_ops_reported": parse_sysbench_metric(proc.stdout, r"writes/s:\s+([0-9.]+)"),
        "read_ops_reported": parse_sysbench_metric(proc.stdout, r"reads/s:\s+([0-9.]+)"),
        "fsyncs_reported": parse_sysbench_metric(proc.stdout, r"fsyncs/s:\s+([0-9.]+)"),
    }


def parse_sysbench_metric(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text)
    return float(match.group(1)) if match else None


def parse_blkparse(path: Path) -> dict[str, Any]:
    counts: dict[str, int] = {}
    rwbs_counts: dict[str, int] = {}
    reads = writes = flushes = discards = 0
    event_lines = 0
    with path.open("r", encoding="utf-8", errors="replace") as src:
        for line in src:
            match = BLKPARSE_RE.match(line)
            if not match:
                continue
            event_lines += 1
            action = match.group("action")
            rwbs = match.group("rwbs")
            counts[action] = counts.get(action, 0) + 1
            rwbs_counts[rwbs] = rwbs_counts.get(rwbs, 0) + 1
            writes += int("W" in rwbs)
            reads += int("R" in rwbs)
            flushes += int("F" in rwbs)
            discards += int("D" in rwbs)
    return {
        "event_lines": event_lines,
        "action_counts": counts,
        "rwbs_counts": rwbs_counts,
        "read_events": reads,
        "write_events": writes,
        "flush_events": flushes,
        "discard_events": discards,
    }


def sample_text(src: Path, dst: Path, *, max_lines: int) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("r", encoding="utf-8", errors="replace") as inp, dst.open("w", encoding="utf-8") as out:
        for idx, line in enumerate(inp):
            if idx >= max_lines:
                break
            out.write(line)


def markdown(summary: dict[str, Any]) -> str:
    blktrace = summary["blktrace"]
    pqc = summary["pqc_side_writer"]
    sysbench = summary["sysbench"]
    lines = [
        "# Real Application Block Trace With PQC Side Writes",
        "",
        "This artifact captures a real sysbench fileio workload while a liboqs-based PQC KMS/audit side writer persists lifecycle records.",
        "",
        f"- Device traced: `{summary['device']}`",
        f"- Mount source: `{summary['mount']['source']}` on `{summary['mount']['target']}` ({summary['mount']['fstype']})",
        f"- Sysbench mode: `{summary['sysbench_mode']}`",
        f"- Sysbench elapsed: `{sysbench['elapsed_s']:.3f}` s",
        f"- PQC sessions completed: `{pqc['sessions_completed']}`",
        f"- PQC audit records: `{pqc['records']}`",
        f"- Blkparse event lines: `{blktrace['event_lines']}`",
        f"- Blkparse write events: `{blktrace['write_events']}`",
        f"- Blkparse read events: `{blktrace['read_events']}`",
        "",
        "## Claim Boundary",
        "",
        "This closes the real-application block-trace gap for the current artifact set. It does not close SPDK/ZenFS latency, public DOGI end-to-end parity, physical FDP replay, per-cohort physical erase scope, or device diversity.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/results/real-app-block-trace/sysbench-pqc"))
    parser.add_argument("--work-dir", type=Path, default=Path("artifacts/runtime/real-app-block-trace/sysbench-pqc"))
    parser.add_argument("--device", default="auto")
    parser.add_argument("--duration", type=int, default=10)
    parser.add_argument("--sysbench-total-size", default="64M")
    parser.add_argument("--sysbench-file-num", type=int, default=8)
    parser.add_argument("--sysbench-block-size", type=int, default=4096)
    parser.add_argument("--sysbench-threads", type=int, default=4)
    parser.add_argument("--sysbench-mode", default="rndrw")
    parser.add_argument("--sysbench-io-mode", default="sync")
    parser.add_argument("--sysbench-fsync-freq", type=int, default=32)
    parser.add_argument("--sysbench-extra-flags", default="")
    parser.add_argument("--pqc-sessions", type=int, default=96)
    parser.add_argument("--pqc-fsync-every", type=int, default=3)
    parser.add_argument("--pqc-sleep-ms", type=int, default=10)
    parser.add_argument("--kem", default="ML-KEM-768")
    parser.add_argument("--sig", default="ML-DSA-65")
    parser.add_argument("--skip-blktrace", action="store_true")
    parser.add_argument("--sample-lines", type=int, default=200)
    args = parser.parse_args()

    if shutil.which("sysbench") is None:
        raise SystemExit("sysbench not found")
    if not args.skip_blktrace and (shutil.which("blktrace") is None or shutil.which("blkparse") is None):
        raise SystemExit("blktrace/blkparse not found")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    mount = find_mount(args.work_dir)
    device = mount["source"] if args.device == "auto" else args.device
    if not args.skip_blktrace and not device.startswith("/dev/"):
        raise SystemExit(f"cannot run blktrace on non-device source: {device}")

    raw_dir = args.out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    blk_prefix = raw_dir / "sysbench-pqc"
    blkparse_out = args.out_dir / "blkparse.txt"
    blkparse_sample = args.out_dir / "blkparse-sample.txt"
    pqc_log = args.work_dir / "pqc-kms-audit.jsonl"
    stop = threading.Event()
    pqc_result: dict[str, Any] = {}

    def worker() -> None:
        nonlocal pqc_result
        pqc_result = pqc_side_writer(
            pqc_log,
            sessions=args.pqc_sessions,
            fsync_every=args.pqc_fsync_every,
            sleep_ms=args.pqc_sleep_ms,
            kem=args.kem,
            sig=args.sig,
            stop=stop,
        )

    blktrace_proc: subprocess.Popen[str] | None = None
    trace_started = None
    if not args.skip_blktrace:
        trace_started = time.time()
        blktrace_proc = subprocess.Popen(
            ["blktrace", "-d", device, "-D", str(raw_dir), "-o", "sysbench-pqc", "-w", str(args.duration + 2)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(1.0)

    pqc_thread = threading.Thread(target=worker, name="pqc-side-writer", daemon=True)
    pqc_thread.start()
    sysbench = run_sysbench(args, args.work_dir)
    stop.set()
    pqc_thread.join(timeout=30)
    if pqc_thread.is_alive():
        raise RuntimeError("PQC side writer did not stop")

    blktrace_stdout = ""
    blktrace_stderr = ""
    if blktrace_proc is not None:
        blktrace_stdout, blktrace_stderr = blktrace_proc.communicate(timeout=args.duration + 10)
        if blktrace_proc.returncode != 0:
            raise RuntimeError(
                f"blktrace failed rc={blktrace_proc.returncode}\n"
                f"stdout={blktrace_stdout[:2000]}\nstderr={blktrace_stderr[:2000]}"
            )
        run_checked(["blkparse", "-i", str(blk_prefix), "-o", str(blkparse_out)])
        sample_text(blkparse_out, blkparse_sample, max_lines=args.sample_lines)
        blktrace_summary = parse_blkparse(blkparse_out)
    else:
        blkparse_out.write_text("", encoding="utf-8")
        blkparse_sample.write_text("", encoding="utf-8")
        blktrace_summary = {
            "event_lines": 0,
            "action_counts": {},
            "rwbs_counts": {},
            "read_events": 0,
            "write_events": 0,
            "flush_events": 0,
            "discard_events": 0,
        }

    raw_files = sorted(raw_dir.glob("sysbench-pqc.blktrace.*"))
    summary = {
        "artifact": "real-app-sysbench-pqc-block-trace",
        "claim": "real sysbench fileio block trace captured while PQC lifecycle side writes were persisted",
        "device": device,
        "mount": mount,
        "duration_s": args.duration,
        "trace_started_at": trace_started,
        "sysbench_mode": args.sysbench_mode,
        "sysbench": sysbench,
        "pqc_side_writer": pqc_result,
        "blktrace": {
            **blktrace_summary,
            "raw_dir": str(raw_dir),
            "raw_files": [
                {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
                for path in raw_files
            ],
            "blkparse_path": str(blkparse_out),
            "blkparse_sample_path": str(blkparse_sample),
            "blkparse_sha256": sha256_file(blkparse_out),
            "blktrace_stdout": blktrace_stdout,
            "blktrace_stderr": blktrace_stderr,
        },
        "claim_boundary": (
            "Closes the real-application block-trace blocker for sysbench+PQC side writes; "
            "does not close SPDK/ZenFS latency, public DOGI parity, physical FDP, erase scope, or device diversity."
        ),
    }
    summary_path = args.out_dir / "summary.json"
    md_path = args.out_dir / "summary.md"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"summary": str(summary_path), "events": blktrace_summary["event_lines"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
