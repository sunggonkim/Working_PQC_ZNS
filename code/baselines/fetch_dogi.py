#!/usr/bin/env python3
"""Fetch the external DOGI repository used by QUASAR baseline tooling."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


DOGI_URL = "https://github.com/dgist-datalab/DOGI.git"
REQUIRED_FILES = [
    "prototype/app/global.cc",
    "prototype/app/main.cc",
    "prototype/CMakeLists.txt",
]


def repo_ready(path: Path) -> bool:
    return all((path / rel).exists() for rel in REQUIRED_FILES)


def fetch(repo: Path, *, url: str = DOGI_URL) -> dict:
    repo.parent.mkdir(parents=True, exist_ok=True)
    if repo_ready(repo):
        return {"repo": str(repo), "url": url, "action": "already-present", "ready": True}
    if repo.exists() and any(repo.iterdir()):
        return {"repo": str(repo), "url": url, "action": "exists-but-incomplete", "ready": False}
    proc = subprocess.run(["git", "clone", "--depth", "1", url, str(repo)], check=False, text=True, capture_output=True)
    return {
        "repo": str(repo),
        "url": url,
        "action": "cloned",
        "ready": repo_ready(repo),
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("artifacts/external/DOGI"))
    parser.add_argument("--url", default=DOGI_URL)
    parser.add_argument("--summary-out", type=Path, default=Path("artifacts/results/dogi-fetch.json"))
    args = parser.parse_args()

    result = fetch(args.repo, url=args.url)
    write_json(args.summary_out, result)
    print(f"wrote fetch_summary={args.summary_out}")
    print(json.dumps({"action": result["action"], "ready": result["ready"]}, sort_keys=True))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
