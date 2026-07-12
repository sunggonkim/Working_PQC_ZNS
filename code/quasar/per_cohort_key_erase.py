#!/usr/bin/env python3
"""Demonstrate cohort-scoped crypto erase with per-cohort DEKs.

NVMe sanitize is too broad for one PQC epoch on a shared namespace.  This
artifact demonstrates the alternative deployment path used by QUASAR's security
boundary: isolate each death cohort under its own data-encryption key (DEK), and
destroy only that cohort's DEK at epoch close.  The encrypted bytes can remain on
media, but the blast radius of crypto erase is the cohort key domain rather than
the entire SSD namespace.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def ub64(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def aad_for(record: dict[str, Any]) -> bytes:
    return json.dumps(
        {
            "cohort_id": record["cohort_id"],
            "intent_class": record["intent_class"],
            "record_id": record["record_id"],
            "tenant_id": record["tenant_id"],
        },
        sort_keys=True,
    ).encode("utf-8")


def make_plaintext(record_id: int, cohort_id: str, intent: str, tenant: str, size: int) -> bytes:
    seed = hashlib.sha256(f"{record_id}:{cohort_id}:{intent}:{tenant}".encode("utf-8")).digest()
    out = bytearray()
    while len(out) < size:
        seed = hashlib.sha256(seed).digest()
        out.extend(seed)
    return bytes(out[:size])


def generate_records(args: argparse.Namespace) -> tuple[dict[str, bytes], list[dict[str, Any]], dict[int, bytes]]:
    keys = {f"epoch-{idx}": AESGCM.generate_key(bit_length=256) for idx in range(args.cohorts)}
    records: list[dict[str, Any]] = []
    plaintexts: dict[int, bytes] = {}
    intents = ["EPHEMERAL_SECRET", "KEM_ARTIFACT", "CERT_METADATA", "SIGNATURE_LOG"]
    record_id = 0
    for cohort_idx in range(args.cohorts):
        cohort_id = f"epoch-{cohort_idx}"
        aes = AESGCM(keys[cohort_id])
        for idx in range(args.records_per_cohort):
            intent = intents[idx % len(intents)]
            tenant = f"tenant-{idx % args.tenants}"
            plaintext = make_plaintext(record_id, cohort_id, intent, tenant, args.payload_bytes)
            nonce = os.urandom(12)
            meta = {
                "record_id": record_id,
                "cohort_id": cohort_id,
                "intent_class": intent,
                "tenant_id": tenant,
                "security_class": "SECRET" if intent == "EPHEMERAL_SECRET" else "PUBLIC_METADATA",
                "expire_class": "EPOCH" if intent != "SIGNATURE_LOG" else "APPEND_ONLY",
                "payload_sha256": hashlib.sha256(plaintext).hexdigest(),
            }
            ciphertext = aes.encrypt(nonce, plaintext, aad_for(meta))
            records.append({**meta, "nonce": b64(nonce), "ciphertext": b64(ciphertext)})
            plaintexts[record_id] = plaintext
            record_id += 1
    return keys, records, plaintexts


def write_store(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        for record in records:
            out.write(json.dumps(record, sort_keys=True) + "\n")


def verify_records(
    keys: dict[str, bytes],
    records: list[dict[str, Any]],
    plaintexts: dict[int, bytes],
) -> dict[str, Any]:
    ok = 0
    missing_key = 0
    invalid_tag = 0
    wrong_plaintext = 0
    by_cohort: dict[str, dict[str, int]] = {}
    start = time.perf_counter_ns()
    for record in records:
        cohort_id = record["cohort_id"]
        stats = by_cohort.setdefault(cohort_id, {"ok": 0, "missing_key": 0, "invalid_tag": 0, "wrong_plaintext": 0})
        key = keys.get(cohort_id)
        if key is None:
            missing_key += 1
            stats["missing_key"] += 1
            continue
        aes = AESGCM(key)
        try:
            plaintext = aes.decrypt(ub64(record["nonce"]), ub64(record["ciphertext"]), aad_for(record))
        except InvalidTag:
            invalid_tag += 1
            stats["invalid_tag"] += 1
            continue
        if plaintext == plaintexts[record["record_id"]]:
            ok += 1
            stats["ok"] += 1
        else:
            wrong_plaintext += 1
            stats["wrong_plaintext"] += 1
    elapsed_ns = time.perf_counter_ns() - start
    return {
        "ok": ok,
        "missing_key": missing_key,
        "invalid_tag": invalid_tag,
        "wrong_plaintext": wrong_plaintext,
        "elapsed_ns": elapsed_ns,
        "ns_per_record": elapsed_ns / max(len(records), 1),
        "by_cohort": by_cohort,
    }


def verify_wrong_key_rejection(records: list[dict[str, Any]], target_cohort: str) -> dict[str, Any]:
    wrong = AESGCM(AESGCM.generate_key(bit_length=256))
    attempted = 0
    rejected = 0
    for record in records:
        if record["cohort_id"] != target_cohort:
            continue
        attempted += 1
        try:
            wrong.decrypt(ub64(record["nonce"]), ub64(record["ciphertext"]), aad_for(record))
        except InvalidTag:
            rejected += 1
    return {"attempted": attempted, "rejected": rejected, "all_rejected": attempted > 0 and attempted == rejected}


def markdown(summary: dict[str, Any]) -> str:
    before = summary["before_destroy"]
    after = summary["after_destroy"]
    lines = [
        "# Per-Cohort Key-Isolated Crypto Erase",
        "",
        "This artifact demonstrates a cohort-scoped erase path that does not call shared-namespace NVMe sanitize.",
        "",
        f"- Cohorts: `{summary['cohorts']}`",
        f"- Records: `{summary['records']}`",
        f"- Target destroyed cohort: `{summary['destroyed_cohort']}`",
        f"- Store bytes: `{summary['store_bytes']}`",
        f"- Before destroy decrypt OK: `{before['ok']}`",
        f"- After destroy decrypt OK: `{after['ok']}`",
        f"- After destroy missing-key records: `{after['missing_key']}`",
        f"- Wrong-key rejection: `{summary['wrong_key_rejection']['rejected']}/{summary['wrong_key_rejection']['attempted']}`",
        f"- Unrelated cohorts preserved: `{summary['unrelated_cohorts_preserved']}`",
        "",
        "## Claim Boundary",
        "",
        summary["claim_boundary"],
    ]
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> dict[str, Any]:
    keys, records, plaintexts = generate_records(args)
    write_store(args.store_out, records)
    before = verify_records(keys, records, plaintexts)
    target = args.destroy_cohort or f"epoch-{args.cohorts // 2}"
    start_destroy = time.perf_counter_ns()
    destroyed_key_sha256 = hashlib.sha256(keys[target]).hexdigest()
    del keys[target]
    destroy_ns = time.perf_counter_ns() - start_destroy
    after = verify_records(keys, records, plaintexts)
    wrong_key = verify_wrong_key_rejection(records, target)
    target_records = [record for record in records if record["cohort_id"] == target]
    unrelated_records = [record for record in records if record["cohort_id"] != target]
    unrelated_ok = sum(
        stats["ok"] for cohort, stats in after["by_cohort"].items() if cohort != target
    )
    target_missing = after["by_cohort"].get(target, {}).get("missing_key", 0)
    summary = {
        "artifact": "per-cohort-key-isolated-crypto-erase",
        "cohorts": args.cohorts,
        "records": len(records),
        "records_per_cohort": args.records_per_cohort,
        "tenants": args.tenants,
        "payload_bytes": args.payload_bytes,
        "destroyed_cohort": target,
        "destroyed_key_sha256": destroyed_key_sha256,
        "store_path": str(args.store_out),
        "store_bytes": args.store_out.stat().st_size,
        "store_sha256": sha256_file(args.store_out),
        "before_destroy": before,
        "after_destroy": after,
        "destroy_key_ns": destroy_ns,
        "target_records": len(target_records),
        "target_records_inaccessible_after_destroy": target_missing == len(target_records),
        "unrelated_records": len(unrelated_records),
        "unrelated_cohorts_preserved": unrelated_ok == len(unrelated_records),
        "wrong_key_rejection": wrong_key,
        "sanitize_called": False,
        "zone_reset_physical_erase_claimed": False,
        "blast_radius": "single death cohort key domain",
        "claim": (
            "Per-cohort DEK destruction makes the destroyed cohort cryptographically inaccessible "
            "while preserving other cohorts, avoiding shared-namespace sanitize blast radius."
        ),
        "claim_boundary": (
            "This is a cohort-scoped crypto-erase deployment path, not proof that zone reset physically erases NAND. "
            "It closes the erase blast-radius issue by moving the destructive primitive from device-wide sanitize "
            "to per-cohort encryption-key destruction; chip-off physical remanence still depends on the secrecy and "
            "destruction of the cohort DEK."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohorts", type=int, default=8)
    parser.add_argument("--records-per-cohort", type=int, default=32)
    parser.add_argument("--payload-bytes", type=int, default=4096)
    parser.add_argument("--tenants", type=int, default=4)
    parser.add_argument("--destroy-cohort", default="")
    parser.add_argument("--store-out", type=Path, default=Path("artifacts/results/per-cohort-key-erase/encrypted-store.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/per-cohort-key-erase/summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/per-cohort-key-erase/summary.md"))
    args = parser.parse_args()
    if args.cohorts < 2:
        raise SystemExit("--cohorts must be >= 2")
    if args.records_per_cohort < 1:
        raise SystemExit("--records-per-cohort must be >= 1")
    summary = run(args)
    print(
        json.dumps(
            {
                "out": str(args.out),
                "destroyed_cohort": summary["destroyed_cohort"],
                "target_inaccessible": summary["target_records_inaccessible_after_destroy"],
                "unrelated_preserved": summary["unrelated_cohorts_preserved"],
            },
            sort_keys=True,
        )
    )
    return 0 if summary["target_records_inaccessible_after_destroy"] and summary["unrelated_cohorts_preserved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
