#!/usr/bin/env python3
"""Validate that current files still match the reproducibility manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as src:
        return json.load(src)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    rows = []
    for item in manifest.get("artifacts", []):
        path = root / item.get("path", "")
        exists = path.exists()
        current_bytes = path.stat().st_size if exists else 0
        current_sha = sha256(path) if exists and path.is_file() else None
        expected_bytes = item.get("bytes")
        expected_sha = item.get("sha256")
        rows.append(
            {
                "id": item.get("id"),
                "path": item.get("path"),
                "exists": exists,
                "expected_bytes": expected_bytes,
                "current_bytes": current_bytes,
                "bytes_match": current_bytes == expected_bytes,
                "expected_sha256": expected_sha,
                "current_sha256": current_sha,
                "sha256_match": current_sha == expected_sha,
            }
        )
    mismatches = [
        row
        for row in rows
        if not row["exists"] or not row["bytes_match"] or not row["sha256_match"]
    ]
    return {
        "scope": "validation that current artifact files match quasar-reproducibility-manifest hashes",
        "passed": not mismatches and bool(rows),
        "artifact_count": len(rows),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "rows": rows,
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# QUASAR Reproducibility Manifest Validation",
        "",
        f"- Scope: {summary['scope']}",
        f"- Passed: `{summary['passed']}`",
        f"- Artifacts: `{summary['artifact_count']}`",
        f"- Mismatches: `{summary['mismatch_count']}`",
        "",
        "| ID | Exists | Bytes Match | SHA256 Match | Current Bytes |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for row in summary["rows"]:
        lines.append(
            "| `{id}` | `{exists}` | `{bytes_match}` | `{sha_match}` | {current_bytes} |".format(
                id=row["id"],
                exists=row["exists"],
                bytes_match=row["bytes_match"],
                sha_match=row["sha256_match"],
                current_bytes=row["current_bytes"],
            )
        )
    if summary["mismatches"]:
        lines.extend(["", "## Mismatches", "", "```json", json.dumps(summary["mismatches"], indent=2), "```"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("artifacts/results/quasar-reproducibility-manifest.json"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/results/quasar-reproducibility-validation.json"),
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=Path("artifacts/results/quasar-reproducibility-validation.md"),
    )
    args = parser.parse_args()

    summary = validate(load_json(args.manifest), args.root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "passed": summary["passed"]}, sort_keys=True))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
