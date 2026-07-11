#!/usr/bin/env python3
"""Trace-driven QUASAR-to-FDP placement-handle mapping model."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

try:
    import replay
except ModuleNotFoundError:  # pragma: no cover
    from quasar import replay


def stable_handle(family: str, handles: int) -> int:
    digest = hashlib.blake2b(family.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "little") % handles


def analyze_trace(
    trace: Path,
    *,
    handles: int,
    bin_width: int,
    cert_epochs: int,
    min_epoch_fill_blocks: int,
) -> dict:
    if handles <= 0:
        raise ValueError("handles must be positive")

    epoch_seen_blocks: Counter[tuple[str, int]] = Counter()
    family_blocks: Counter[str] = Counter()
    family_writes: Counter[str] = Counter()
    family_intents: dict[str, Counter[str]] = defaultdict(Counter)
    handle_blocks: dict[int, Counter[str]] = defaultdict(Counter)
    handle_intents: dict[int, Counter[str]] = defaultdict(Counter)
    total_blocks = 0
    writes = 0

    for row in replay.iter_trace(trace):
        if row.get("op") != "write":
            continue
        family = replay.family_for(
            row,
            bin_width=bin_width,
            cert_epochs=cert_epochs,
            epoch_seen_blocks=epoch_seen_blocks,
            min_epoch_fill_blocks=min_epoch_fill_blocks,
        )
        blocks = int(row.get("size_blocks", 1))
        intent = row.get("intent", "UNKNOWN")
        handle = stable_handle(family, handles)
        family_blocks[family] += blocks
        family_writes[family] += 1
        family_intents[family][intent] += blocks
        handle_blocks[handle][family] += blocks
        handle_intents[handle][intent] += blocks
        total_blocks += blocks
        writes += 1

    occupied_handles = sorted(handle_blocks)
    collision_handles = {
        handle: families
        for handle, families in handle_blocks.items()
        if len(families) > 1
    }
    dominant_family_blocks = 0
    dominant_intent_blocks = 0
    for handle in occupied_handles:
        dominant_family_blocks += max(handle_blocks[handle].values())
        dominant_intent_blocks += max(handle_intents[handle].values())

    family_to_handle = {
        family: stable_handle(family, handles)
        for family in sorted(family_blocks)
    }
    return {
        "trace": str(trace),
        "handles": handles,
        "bin_width": bin_width,
        "cert_epochs": cert_epochs,
        "min_epoch_fill_blocks": min_epoch_fill_blocks,
        "writes": writes,
        "total_blocks": total_blocks,
        "family_count": len(family_blocks),
        "occupied_handles": len(occupied_handles),
        "empty_handles": handles - len(occupied_handles),
        "collision_handles": len(collision_handles),
        "collision_handle_fraction": len(collision_handles) / len(occupied_handles) if occupied_handles else 0.0,
        "family_purity": dominant_family_blocks / total_blocks if total_blocks else 0.0,
        "intent_purity": dominant_intent_blocks / total_blocks if total_blocks else 0.0,
        "avg_families_per_occupied_handle": (
            sum(len(families) for families in handle_blocks.values()) / len(occupied_handles)
            if occupied_handles
            else 0.0
        ),
        "max_families_per_handle": max((len(families) for families in handle_blocks.values()), default=0),
        "family_to_handle": family_to_handle,
        "handle_summary": {
            str(handle): {
                "families": len(families),
                "blocks": sum(families.values()),
                "dominant_family": families.most_common(1)[0][0],
                "dominant_family_blocks": families.most_common(1)[0][1],
                "dominant_intent": handle_intents[handle].most_common(1)[0][0],
                "dominant_intent_blocks": handle_intents[handle].most_common(1)[0][1],
            }
            for handle, families in sorted(handle_blocks.items())
        },
        "collisions_top": {
            str(handle): dict(families.most_common(10))
            for handle, families in sorted(
                collision_handles.items(),
                key=lambda item: sum(item[1].values()),
                reverse=True,
            )[:20]
        },
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path, runs: list[dict]) -> None:
    lines = [
        "# QUASAR FDP Mapping Model",
        "",
        "This is a trace-driven deployment model, not a physical FDP measurement.",
        "It maps QUASAR zone families to a fixed number of FDP placement handles and reports collision/purity pressure.",
        "",
        "| Handles | Families | Occupied | Collision Handles | Family Purity | Intent Purity | Avg Families/Handle | Max Families/Handle |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for run in runs:
        lines.append(
            "| {handles} | {families} | {occupied} | {collisions} | {fp:.4f} | {ip:.4f} | {avg:.2f} | {maxf} |".format(
                handles=run["handles"],
                families=run["family_count"],
                occupied=run["occupied_handles"],
                collisions=run["collision_handles"],
                fp=run["family_purity"],
                ip=run["intent_purity"],
                avg=run["avg_families_per_occupied_handle"],
                maxf=run["max_families_per_handle"],
            )
        )
    lines.extend(
        [
            "",
            "Interpretation:",
            "",
            "- High family purity means the FDP handle still mostly represents one QUASAR death cohort.",
            "- Collision handles are expected when the hardware exposes fewer handles than QUASAR families.",
            "- Use this model to decide whether an FDP experiment should use exact epoch families, binned epochs, or tenant/coarse bins.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--handles", nargs="+", type=int, default=[8, 16, 32, 64, 128])
    parser.add_argument("--bin-width", type=int, default=1)
    parser.add_argument("--cert-epochs", type=int, default=12)
    parser.add_argument("--min-epoch-fill-blocks", type=int, default=1)
    parser.add_argument("--out", type=Path, default=Path("artifacts/results/fdp-mapping.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/fdp-mapping.md"))
    args = parser.parse_args()

    runs = [
        analyze_trace(
            args.trace,
            handles=handles,
            bin_width=args.bin_width,
            cert_epochs=args.cert_epochs,
            min_epoch_fill_blocks=args.min_epoch_fill_blocks,
        )
        for handles in args.handles
    ]
    payload = {"trace": str(args.trace), "runs": runs}
    write_json(args.out, payload)
    write_markdown(args.markdown_out, runs)
    print(f"wrote {args.out}")
    print(f"wrote {args.markdown_out}")
    print(json.dumps({"runs": len(runs), "trace": str(args.trace)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
