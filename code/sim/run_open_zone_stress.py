#!/usr/bin/env python3
"""Adversarial open-zone stress for QUASAR-DOGI.

This runner creates a deliberately hostile trace: many tenants, tiny epochs,
small KEM artifacts, and limited open-zone budgets. It complements the
DOGI-paper-shaped space sweep by asking whether QUASAR's epoch placement still
behaves well when exact cohort placement is exhausted.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import random
from argparse import Namespace
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt

try:
    import zns_pqc_verify as sim
except ModuleNotFoundError:  # pragma: no cover - used by root-level unittest discovery
    from sim import zns_pqc_verify as sim


@dataclass(order=True)
class PendingExpire:
    ts: int
    object_id: int
    lba: int
    size_blocks: int


def emit(out, event: dict) -> None:
    out.write(json.dumps(event, sort_keys=True) + "\n")


def secret_expire_ts(ts: int, tenant: int, epoch_len: int, tenant_skew: int, jitter: int, rng: random.Random) -> int:
    local_epoch = ts // epoch_len
    boundary = (local_epoch + 1) * epoch_len
    skew = tenant % max(1, tenant_skew)
    return boundary + skew + (rng.randint(0, jitter) if jitter else 0)


def choose_intent(rng: random.Random) -> tuple[str, int]:
    x = rng.random()
    if x < 0.70:
        return "KEM_ARTIFACT", 1
    if x < 0.90:
        return "EPHEMERAL_SECRET", 1
    if x < 0.96:
        return "CERT_METADATA", rng.randint(1, 2)
    return "SIGNATURE_LOG", rng.randint(1, 3)


def expire_class(intent: str) -> str:
    if intent in {"KEM_ARTIFACT", "EPHEMERAL_SECRET"}:
        return "EPOCH"
    if intent == "CERT_METADATA":
        return "ROTATION"
    if intent == "SIGNATURE_LOG":
        return "APPEND_ONLY"
    return "UNKNOWN"


def security_class(intent: str) -> str:
    if intent in {"KEM_ARTIFACT", "EPHEMERAL_SECRET"}:
        return "SECRET"
    if intent in {"CERT_METADATA", "SIGNATURE_LOG"}:
        return "PUBLIC_METADATA"
    return "PAYLOAD"


def maybe_missing_confidence(rate: float, rng: random.Random) -> str:
    return "UNKNOWN" if rng.random() < rate else "exact"


def generate_trace(args: argparse.Namespace) -> dict:
    rng = random.Random(args.seed)
    trace = args.trace_out
    trace.parent.mkdir(parents=True, exist_ok=True)
    summary_out = args.trace_summary_out
    summary_out.parent.mkdir(parents=True, exist_ok=True)

    expires: list[PendingExpire] = []
    live_payload_by_lba: dict[int, int] = {}
    next_object_id = 1
    counts = defaultdict(int)
    blocks = defaultdict(int)
    max_pending_expires = 0

    with trace.open("w", encoding="utf-8") as out:
        for lba in range(args.payload_working_set):
            object_id = next_object_id
            next_object_id += 1
            live_payload_by_lba[lba] = object_id
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
            blocks["prefill"] += 1

        for ts in range(1, args.events + 1):
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
                counts["pqc_expire_events"] += 1
                blocks["pqc_expire"] += item.size_blocks

            for update in range(args.payload_updates_per_tick):
                if args.payload_working_set <= 0:
                    break
                if rng.random() < args.payload_hot_fraction:
                    lba = rng.randrange(max(1, args.payload_hot_set))
                else:
                    lba = rng.randrange(args.payload_working_set)
                previous = live_payload_by_lba.get(lba)
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
                    counts["payload_expire_events"] += 1
                    blocks["payload_expire"] += 1
                object_id = next_object_id
                next_object_id += 1
                live_payload_by_lba[lba] = object_id
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
                counts["payload_write_events"] += 1
                blocks["payload_write"] += 1

            for item_idx in range(args.pqc_writes_per_tick):
                tenant = (ts * args.pqc_writes_per_tick + item_idx) % args.tenants
                local_epoch = ts // args.epoch_len
                epoch_id = tenant * args.epoch_namespace + local_epoch
                intent, size_blocks = choose_intent(rng)
                lba = args.pqc_lba_base + tenant * args.tenant_lba_stride + local_epoch * 17 + rng.randrange(64)
                if intent in {"KEM_ARTIFACT", "EPHEMERAL_SECRET"}:
                    expire_ts = secret_expire_ts(
                        ts,
                        tenant,
                        args.epoch_len,
                        args.tenant_skew,
                        args.expire_jitter,
                        rng,
                    )
                elif intent == "CERT_METADATA":
                    expire_ts = ((local_epoch // args.rotation_epochs) + 1) * args.rotation_epochs * args.epoch_len
                    expire_ts += tenant % max(1, args.tenant_skew)
                else:
                    expire_ts = None

                object_id = next_object_id
                next_object_id += 1
                confidence = maybe_missing_confidence(args.trace_missing_hint_rate, rng)
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
                        "cohort_id": f"tenant{tenant}:{intent}:{local_epoch}",
                        "tenant_id": f"tenant{tenant}",
                        "confidence": confidence,
                        "expire_ts": expire_ts,
                    },
                )
                counts[f"{intent}_write_events"] += 1
                blocks[f"{intent}_write"] += size_blocks
                if expire_ts is not None:
                    heapq.heappush(expires, PendingExpire(expire_ts, object_id, lba, size_blocks))
                max_pending_expires = max(max_pending_expires, len(expires))

        drain_ts = args.events + 1
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
            counts["pqc_expire_events"] += 1
            blocks["pqc_expire"] += item.size_blocks

    summary = {
        "trace": str(trace),
        "events": args.events,
        "seed": args.seed,
        "tenants": args.tenants,
        "epoch_len": args.epoch_len,
        "epoch_namespace": args.epoch_namespace,
        "pqc_writes_per_tick": args.pqc_writes_per_tick,
        "payload_working_set": args.payload_working_set,
        "payload_updates_per_tick": args.payload_updates_per_tick,
        "trace_missing_hint_rate": args.trace_missing_hint_rate,
        "max_pending_expires": max_pending_expires,
        "counts": dict(sorted(counts.items())),
        "blocks": dict(sorted(blocks.items())),
        "note": "Adversarial open-zone trace: tenant-isolated tiny epochs force exact-zone budget pressure.",
    }
    summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def max_live_blocks(trace: Path) -> int:
    live_by_object: dict[int, int] = {}
    live = 0
    peak = 0
    with trace.open("r", encoding="utf-8") as src:
        for line in src:
            event = json.loads(line)
            object_id = int(event["object_id"])
            size_blocks = int(event["size_blocks"])
            if event["op"] in {"write", "prefill"}:
                old = live_by_object.get(object_id, 0)
                live += size_blocks - old
                live_by_object[object_id] = size_blocks
                peak = max(peak, live)
            elif event["op"] == "expire":
                live -= live_by_object.pop(object_id, 0)
    return peak


def auto_zone_count(args: argparse.Namespace) -> int:
    if args.zones > 0:
        return args.zones
    peak_live = max_live_blocks(args.trace_out)
    usable = math.ceil((peak_live * (1.0 + args.auto_op_ratio)) / args.zone_capacity)
    return max(args.min_free_zones + 1, usable + args.min_free_zones)


def make_sim_args(args: argparse.Namespace, *, zones: int, **overrides) -> Namespace:
    values = {
        "trace": args.trace_out,
        "zones": zones,
        "zone_capacity": args.zone_capacity,
        "min_free_zones": args.min_free_zones,
        "lba_bucket_size": args.lba_bucket_size,
        "quasar_cert_epochs": args.quasar_cert_epochs,
        "quasar_min_epoch_fill": args.quasar_min_epoch_fill,
        "quasar_bin_width": 1,
        "quasar_open_zone_budget": 0,
        "quasar_residual_threshold": -1,
        "quasar_residual_fraction": args.quasar_residual_fraction,
        "quasar_disable_overflow": False,
        "quasar_disable_secret_priority": False,
        "hint_missing_rate": 0.0,
        "wrong_epoch_rate": 0.0,
        "straggler_rate": 0.0,
        "base_write_ns": args.base_write_ns,
        "gc_copy_ns": args.gc_copy_ns,
        "dogi_ml_ns_per_batch": args.dogi_ml_ns_per_batch,
        "dogi_batch_size": args.dogi_batch_size,
        "quasar_hint_ns": args.quasar_hint_ns,
        "seed": args.seed,
    }
    values.update(overrides)
    return Namespace(**values)


def run_policy_with_retry(ns: Namespace, policy: str, max_retries: int) -> dict:
    requested_zones = ns.zones
    attempt = ns
    last_error: Exception | None = None
    for retry in range(max_retries + 1):
        try:
            row = sim.run_policy(attempt, policy)
            row["failed"] = False
            row["requested_zones"] = requested_zones
            row["retry_count"] = retry
            return row
        except RuntimeError as error:
            last_error = error
            attempt = Namespace(**{**vars(attempt), "zones": int(attempt.zones * 1.35) + 1})
    return {
        "policy": policy,
        "trace": str(ns.trace),
        "failed": True,
        "error": str(last_error or RuntimeError("failed")),
        "requested_zones": requested_zones,
        "zones": attempt.zones,
        "retry_count": max_retries,
        "waf": 0.0,
        "gc_write_blocks": 0,
        "lifetime_zone_utilization": 0.0,
        "closed_zone_fill_avg": 0.0,
        "stale_secret_blocks_remaining": 0,
        "stale_secret_block_seconds": 0,
        "max_secret_exposure_time": 0,
    }


def run_experiments(args: argparse.Namespace) -> list[dict]:
    zones = auto_zone_count(args)
    rows: list[dict] = []
    dogi_ns = make_sim_args(args, zones=zones)
    dogi = run_policy_with_retry(dogi_ns, "dogi-history", args.max_retries)
    dogi["experiment"] = "dogi_baseline"
    dogi["secret_priority_mode"] = "n/a"
    dogi["open_zone_budget"] = None
    dogi["bin_width"] = None
    dogi["missing_hint_rate"] = 0.0
    rows.append(dogi)

    for secret_mode in args.secret_priority_modes:
        disable_secret_priority = secret_mode == "strict"
        for missing in args.hint_missing_values:
            for budget in args.open_zone_budget_values:
                for bin_width in args.bin_width_values:
                    ns = make_sim_args(
                        args,
                        zones=zones,
                        quasar_open_zone_budget=budget,
                        quasar_bin_width=bin_width,
                        quasar_disable_secret_priority=disable_secret_priority,
                        hint_missing_rate=missing,
                    )
                    row = run_policy_with_retry(ns, "quasar-dogi-hybrid", args.max_retries)
                    row["experiment"] = "open_zone_stress"
                    row["secret_priority_mode"] = secret_mode
                    row["open_zone_budget"] = budget
                    row["bin_width"] = bin_width
                    row["missing_hint_rate"] = missing
                    rows.append(row)
                    if args.verbose:
                        sim.print_row(row)
    return rows


def summarize(rows: list[dict]) -> dict:
    candidates = [row for row in rows if row["experiment"] == "open_zone_stress" and not row.get("failed")]
    dogi = next((row for row in rows if row["experiment"] == "dogi_baseline"), None)
    budget_summary = []
    by_budget: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in candidates:
        key = (str(row.get("secret_priority_mode", "priority")), int(row["open_zone_budget"]))
        by_budget[key].append(row)
    for (secret_mode, budget), items in sorted(by_budget.items()):
        budget_summary.append(
            {
                "secret_priority_mode": secret_mode,
                "open_zone_budget": budget,
                "runs": len(items),
                "min_waf": min(row["waf"] for row in items),
                "max_waf": max(row["waf"] for row in items),
                "max_stale_secret_block_seconds": max(row["stale_secret_block_seconds"] for row in items),
                "max_secret_exposure_time": max(row["max_secret_exposure_time"] for row in items),
                "avg_exact_epoch_writes": sum(row.get("quasar_exact_epoch_writes", 0) for row in items) / len(items),
                "avg_binned_epoch_writes": sum(row.get("quasar_binned_epoch_writes", 0) for row in items) / len(items),
                "avg_lifetime_utilization": sum(row["lifetime_zone_utilization"] for row in items) / len(items),
            }
        )
    best_waf = sorted(candidates, key=lambda row: (row["waf"], row["stale_secret_block_seconds"]))[:8]
    worst_exposure = sorted(
        candidates,
        key=lambda row: (row["stale_secret_block_seconds"], row["max_secret_exposure_time"]),
        reverse=True,
    )[:8]
    return {
        "dogi_baseline": dogi,
        "budget_summary": budget_summary,
        "best_waf": best_waf,
        "worst_exposure": worst_exposure,
        "failed_runs": sum(1 for row in rows if row.get("failed")),
        "candidate_count": len(candidates),
    }


def fmt_float(value: object, digits: int = 3) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def fmt_int(value: object) -> str:
    if value is None:
        return "N/A"
    return f"{int(value):,}"


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def setting(row: dict) -> str:
    return "secret={}, missing={:.2f}, open={}, bin={}".format(
        row.get("secret_priority_mode", "priority"),
        float(row["missing_hint_rate"]),
        "auto" if int(row["open_zone_budget"]) == 0 else int(row["open_zone_budget"]),
        int(row["bin_width"]),
    )


def write_markdown(rows: list[dict], trace_summary: dict, summary: dict, path: Path) -> None:
    dogi = summary["dogi_baseline"] or {}
    budget_rows = []
    for row in summary["budget_summary"]:
        budget_rows.append(
            [
                row["secret_priority_mode"],
                "auto" if row["open_zone_budget"] == 0 else str(row["open_zone_budget"]),
                fmt_int(row["runs"]),
                fmt_float(row["min_waf"]),
                fmt_float(row["max_waf"]),
                fmt_int(row["max_stale_secret_block_seconds"]),
                fmt_int(row["max_secret_exposure_time"]),
                fmt_float(row["avg_lifetime_utilization"]),
                fmt_float(row["avg_exact_epoch_writes"], 1),
                fmt_float(row["avg_binned_epoch_writes"], 1),
            ]
        )

    def selected_table(selected: list[dict]) -> str:
        return markdown_table(
            [
                "Setting",
                "WAF",
                "GC Blocks",
                "Lifetime Util",
                "Closed Fill",
                "Stale Block-Seconds",
                "Max Exposure",
                "Exact Writes",
                "Binned Writes",
                "Missing",
            ],
            [
                [
                    setting(row),
                    fmt_float(row["waf"]),
                    fmt_int(row["gc_write_blocks"]),
                    fmt_float(row["lifetime_zone_utilization"]),
                    fmt_float(row["closed_zone_fill_avg"]),
                    fmt_int(row["stale_secret_block_seconds"]),
                    fmt_int(row["max_secret_exposure_time"]),
                    fmt_int(row.get("quasar_exact_epoch_writes", 0)),
                    fmt_int(row.get("quasar_binned_epoch_writes", 0)),
                    fmt_int(row.get("hint_missing_injected", 0)),
                ]
                for row in selected
            ],
        )

    lines = [
        "# Adversarial Open-Zone Stress",
        "",
        "## Trace",
        "",
        f"- Trace: `{trace_summary['trace']}`",
        f"- Tenants: {trace_summary['tenants']}",
        f"- Epoch length: {trace_summary['epoch_len']}",
        f"- PQC writes/tick: {trace_summary['pqc_writes_per_tick']}",
        f"- Payload working set: {trace_summary['payload_working_set']}",
        f"- Max pending expirations: {trace_summary['max_pending_expires']}",
        "",
        "## DOGI Baseline",
        "",
        markdown_table(
            ["WAF", "GC Blocks", "Lifetime Util", "Closed Fill", "Stale Secrets", "Stale Block-Seconds"],
            [
                [
                    fmt_float(dogi.get("waf")),
                    fmt_int(dogi.get("gc_write_blocks")),
                    fmt_float(dogi.get("lifetime_zone_utilization")),
                    fmt_float(dogi.get("closed_zone_fill_avg")),
                    fmt_int(dogi.get("stale_secret_blocks_remaining")),
                    fmt_int(dogi.get("stale_secret_block_seconds")),
                ]
            ],
        ),
        "",
        "## By Open-Zone Budget",
        "",
        markdown_table(
            [
                "Secret Mode",
                "Open Budget",
                "Runs",
                "Min WAF",
                "Max WAF",
                "Max Stale Block-Seconds",
                "Max Exposure",
                "Avg Lifetime Util",
                "Avg Exact Writes",
                "Avg Binned Writes",
            ],
            budget_rows,
        ),
        "",
        "## Lowest WAF Settings",
        "",
        selected_table(summary["best_waf"]),
        "",
        "## Worst Exposure Settings",
        "",
        selected_table(summary["worst_exposure"]),
        "",
        "## Interpretation",
        "",
        "- Tight open-zone budgets force KEM epoch data into binned families, which is visible in the exact/binned write counters.",
        "- The `priority` mode preserves exact placement for `EPHEMERAL_SECRET`; it minimizes short-lived secret exposure for narrow bins but can produce extremely low lifetime utilization when tenants have tiny isolated epochs.",
        "- The `strict` mode applies the open-zone budget to all epoch data. With very coarse bins it can recover WAF and space utilization, but it increases stale-secret block-seconds because multiple tenant/epoch cohorts wait for the shared bin to expire.",
        "- Final stale-secret blocks can still be zero after the drain phase, so `stale_secret_block_seconds` and `max_secret_exposure_time` are the important exposure metrics.",
        "- This is an adversarial regime, not the expected-case DOGI-paper-shaped trace. It defines where QUASAR needs admission control, bin sizing, and tenant-aware policy tuning.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_json(rows: list[dict], trace_summary: dict, summary: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"trace_summary": trace_summary, "summary": summary, "rows": rows}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def plot(rows: list[dict], path: Path) -> None:
    candidates = [row for row in rows if row["experiment"] == "open_zone_stress" and not row.get("failed")]
    if not candidates:
        return
    fig, ax = plt.subplots(figsize=(8.4, 5.2))
    colors = [row["stale_secret_block_seconds"] for row in candidates]
    sizes = [45 + 0.03 * row.get("quasar_binned_epoch_writes", 0) for row in candidates]
    scatter = ax.scatter(
        [row["lifetime_zone_utilization"] for row in candidates],
        [row["waf"] for row in candidates],
        c=colors,
        s=sizes,
        cmap="magma_r",
        alpha=0.82,
        edgecolors="black",
        linewidths=0.25,
    )
    ax.set_xlabel("Lifetime zone utilization")
    ax.set_ylabel("WAF")
    ax.set_title("Adversarial open-zone stress")
    ax.grid(alpha=0.25)
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("Stale secret block-seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    print(f"wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-out", type=Path, default=Path("artifacts/traces/open-zone-stress/adversarial.jsonl"))
    parser.add_argument(
        "--trace-summary-out",
        type=Path,
        default=Path("artifacts/results/open-zone-stress/trace-summary.json"),
    )
    parser.add_argument("--json-out", type=Path, default=Path("artifacts/results/open-zone-stress/summary.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("artifacts/results/open-zone-stress/summary.md"))
    parser.add_argument("--figure", type=Path, default=Path("artifacts/figures/open-zone-stress/summary.png"))
    parser.add_argument("--events", type=int, default=6_000)
    parser.add_argument("--tenants", type=int, default=32)
    parser.add_argument("--epoch-len", type=int, default=24)
    parser.add_argument("--epoch-namespace", type=int, default=1_000_000)
    parser.add_argument("--tenant-skew", type=int, default=8)
    parser.add_argument("--expire-jitter", type=int, default=4)
    parser.add_argument("--rotation-epochs", type=int, default=16)
    parser.add_argument("--pqc-writes-per-tick", type=int, default=2)
    parser.add_argument("--pqc-lba-base", type=int, default=20_000_000)
    parser.add_argument("--tenant-lba-stride", type=int, default=100_000)
    parser.add_argument("--payload-working-set", type=int, default=3_072)
    parser.add_argument("--payload-hot-set", type=int, default=384)
    parser.add_argument("--payload-hot-fraction", type=float, default=0.85)
    parser.add_argument("--payload-updates-per-tick", type=int, default=1)
    parser.add_argument("--trace-missing-hint-rate", type=float, default=0.0)
    parser.add_argument("--zones", type=int, default=0)
    parser.add_argument("--auto-op-ratio", type=float, default=0.15)
    parser.add_argument("--zone-capacity", type=int, default=128)
    parser.add_argument("--min-free-zones", type=int, default=8)
    parser.add_argument("--lba-bucket-size", type=int, default=4096)
    parser.add_argument("--quasar-cert-epochs", type=int, default=12)
    parser.add_argument("--quasar-min-epoch-fill", type=float, default=0.0)
    parser.add_argument("--quasar-residual-fraction", type=float, default=0.0)
    parser.add_argument("--open-zone-budget-values", nargs="+", type=int, default=[1, 2, 4, 8, 16, 0])
    parser.add_argument("--bin-width-values", nargs="+", type=int, default=[1, 16, 1_000_000, 32_000_000])
    parser.add_argument(
        "--secret-priority-modes",
        nargs="+",
        choices=["priority", "strict"],
        default=["priority", "strict"],
        help="'priority' lets EPHEMERAL_SECRET bypass the exact-family budget; 'strict' applies the budget to all epoch data.",
    )
    parser.add_argument("--hint-missing-values", nargs="+", type=float, default=[0.0, 0.05])
    parser.add_argument("--base-write-ns", type=int, default=10_000)
    parser.add_argument("--gc-copy-ns", type=int, default=15_000)
    parser.add_argument("--dogi-ml-ns-per-batch", type=int, default=600_000)
    parser.add_argument("--dogi-batch-size", type=int, default=128)
    parser.add_argument("--quasar-hint-ns", type=int, default=200)
    parser.add_argument("--seed", type=int, default=71)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.tenants <= 0:
        raise SystemExit("--tenants must be positive")
    if args.epoch_len <= 0:
        raise SystemExit("--epoch-len must be positive")
    if args.pqc_writes_per_tick <= 0:
        raise SystemExit("--pqc-writes-per-tick must be positive")
    if args.payload_working_set < 0:
        raise SystemExit("--payload-working-set must be non-negative")

    trace_summary = generate_trace(args)
    rows = run_experiments(args)
    summary = summarize(rows)
    write_json(rows, trace_summary, summary, args.json_out)
    write_markdown(rows, trace_summary, summary, args.markdown_out)
    plot(rows, args.figure)
    print(f"wrote {args.trace_out}")
    print(f"wrote {args.trace_summary_out}")
    print(f"wrote {args.json_out}")
    print(f"wrote {args.markdown_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
