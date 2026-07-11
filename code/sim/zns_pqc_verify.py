#!/usr/bin/env python3
"""Trace-driven ZNS simulator for PQC/DOGI/QUASAR verification.

This simulator is intentionally compact, but it now models the mechanisms named
in plan.md:

- DOGI-style lifetime grouping from storage-visible history.
- SepBIT/MiDAS-style storage-visible heuristics.
- QUASAR death-cohort grouping from `intent` and `epoch_id`.
- QUASAR admission control, epoch binning, overflow groups, open-zone pressure,
  residual migration, immediate reset eligibility, and stale-secret exposure.

It is not a replacement for the full DOGI prototype. Its job is to turn the
paper hypothesis into fast, repeatable evidence before building the real ZNS or
FDP replay path.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import random
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


LIFETIME_THRESHOLDS = [128, 512, 2_048, 8_192, 32_768]
FREQUENCY_THRESHOLDS = [1, 4, 16, 64, 256, 1_024]
DOGI_SEGMENT_BLOCKS = 512  # 2 MiB chunks at 4 KiB/block.
DOGI_FREQ_WINDOW = 256
DOGI_RUNTIME_FEATURE_NAMES = [
    "lba",
    "freq_bit",
    "freq_bit2",
    "interval_bit",
    "seg_accessed",
    "prev_lba",
]
SECRET_INTENTS = {"EPHEMERAL_SECRET", "KEM_ARTIFACT"}
RESETTABLE_QUASAR_FAMILIES = {"EPOCH_SECRET", "EPOCH_BIN", "ROTATION"}


@dataclass
class Block:
    object_id: int
    epoch_id: int
    intent: str
    group: int
    tenant_id: str = "tenant0"
    live: bool = True
    expired_ts: Optional[int] = None

    @property
    def is_secret(self) -> bool:
        return self.intent in SECRET_INTENTS


@dataclass
class Zone:
    zone_id: int
    capacity: int
    group: int
    blocks: list[Block] = field(default_factory=list)
    sealed: bool = False
    live_blocks: int = 0
    first_write_ts: Optional[int] = None
    last_write_ts: Optional[int] = None

    @property
    def free(self) -> int:
        return self.capacity - len(self.blocks)

    @property
    def live_count(self) -> int:
        return self.live_blocks

    @property
    def invalid_count(self) -> int:
        return len(self.blocks) - self.live_count

    @property
    def fill(self) -> float:
        return len(self.blocks) / self.capacity if self.capacity else 0.0

    @property
    def invalid_ratio(self) -> float:
        if not self.blocks:
            return 0.0
        return self.invalid_count / len(self.blocks)


@dataclass(frozen=True)
class DogiFeatures:
    lba_bucket: int
    segment_id: int
    freq_bit: int
    freq_bit2: int
    interval_bit: int
    seg_accessed: int
    prev_lba_bucket: int
    prev_group: int

    def runtime_key(self) -> tuple[int, int, int, int, int, int]:
        return (
            self.lba_bucket,
            self.freq_bit,
            self.freq_bit2,
            self.interval_bit,
            self.seg_accessed,
            self.prev_lba_bucket,
        )


class LifetimePredictor:
    def __init__(self, lba_bucket_size: int) -> None:
        self.lba_bucket_size = lba_bucket_size
        self.by_bucket: dict[int, float] = {}
        self.global_avg = 8_192.0
        self.observed = 0
        self.predicted: dict[int, int] = {}
        self.actual: dict[int, int] = {}

    @staticmethod
    def bucket_for_lifetime(lifetime: Optional[int]) -> int:
        if lifetime is None:
            return len(LIFETIME_THRESHOLDS)
        for idx, threshold in enumerate(LIFETIME_THRESHOLDS):
            if lifetime <= threshold:
                return idx
        return len(LIFETIME_THRESHOLDS)

    def _lba_bucket(self, lba: int) -> int:
        return lba // self.lba_bucket_size

    def predict_group(self, object_id: int, lba: int) -> int:
        pred_lifetime = self.by_bucket.get(self._lba_bucket(lba), self.global_avg)
        group = self.bucket_for_lifetime(int(pred_lifetime))
        self.predicted[object_id] = group
        return group

    def observe(self, object_id: int, lba: int, lifetime: int) -> None:
        actual_group = self.bucket_for_lifetime(lifetime)
        self.actual[object_id] = actual_group
        bucket = self._lba_bucket(lba)
        old = self.by_bucket.get(bucket, self.global_avg)
        self.by_bucket[bucket] = 0.85 * old + 0.15 * lifetime
        self.global_avg = (self.global_avg * self.observed + lifetime) / (self.observed + 1)
        self.observed += 1

    def stats(self) -> dict[str, float]:
        common = set(self.predicted).intersection(self.actual)
        if not common:
            return {"prediction_accuracy": 0.0, "off_by_gt1": 0.0, "prediction_samples": 0}
        exact = sum(1 for oid in common if self.predicted[oid] == self.actual[oid])
        off = sum(1 for oid in common if abs(self.predicted[oid] - self.actual[oid]) > 1)
        return {
            "prediction_accuracy": exact / len(common),
            "off_by_gt1": off / len(common),
            "prediction_samples": len(common),
        }


class Policy:
    name = "policy"

    def assign(self, event: dict) -> int:
        raise NotImplementedError

    def observe_expire(self, event: dict, write_event: dict) -> None:
        return

    def family_type(self, group: int) -> str:
        return "GENERIC"

    def is_quasar(self) -> bool:
        return False

    def extra_stats(self) -> dict[str, float]:
        return {}


class FifoPolicy(Policy):
    name = "fifo"

    def assign(self, event: dict) -> int:
        return 0


class DogiHistoryPolicy(Policy):
    name = "dogi-history"

    def __init__(self, lba_bucket_size: int) -> None:
        self.lba_bucket_size = lba_bucket_size
        self.predicted: dict[int, int] = {}
        self.actual: dict[int, int] = {}
        self.write_features: dict[int, DogiFeatures] = {}
        self.avg_by_runtime_feature: dict[tuple[int, int, int, int, int, int], float] = {}
        self.avg_by_lba_bucket: dict[int, float] = {}
        self.avg_by_segment: dict[int, float] = {}
        self.avg_by_prev_group: dict[int, float] = {}
        self.global_avg = 8_192.0
        self.observed = 0

        self.prev_lba: Optional[int] = None
        self.prev_group_by_lba_bucket: dict[int, int] = {}
        self.last_ts_by_lba_bucket: dict[int, int] = {}
        self.last_freq_window_by_lba_bucket: dict[int, int] = {}
        self.freq_bits_by_lba_bucket: dict[int, int] = {}
        self.segment_writes: Counter[int] = Counter()
        self.feature_samples = 0

    def assign(self, event: dict) -> int:
        features = self._features(event)
        pred_lifetime = self._predict_lifetime(features)
        group = LifetimePredictor.bucket_for_lifetime(int(pred_lifetime))
        self.predicted[event["object_id"]] = group
        self.write_features[event["object_id"]] = features
        self._observe_write(event, features, group)
        self.feature_samples += 1
        return group

    def observe_expire(self, event: dict, write_event: dict) -> None:
        lifetime = int(event["ts"]) - int(write_event["ts"])
        actual_group = LifetimePredictor.bucket_for_lifetime(lifetime)
        self.actual[event["object_id"]] = actual_group
        features = self.write_features.get(event["object_id"])
        if features is None:
            return
        self._update_avg(self.avg_by_runtime_feature, features.runtime_key(), lifetime)
        self._update_avg(self.avg_by_lba_bucket, features.lba_bucket, lifetime)
        segment = int(write_event["lba"]) // DOGI_SEGMENT_BLOCKS
        self._update_avg(self.avg_by_segment, segment, lifetime)
        if features.prev_group >= 0:
            self._update_avg(self.avg_by_prev_group, features.prev_group, lifetime)
        self.global_avg = (self.global_avg * self.observed + lifetime) / (self.observed + 1)
        self.observed += 1

    def extra_stats(self) -> dict[str, float]:
        common = set(self.predicted).intersection(self.actual)
        if not common:
            stats = {"prediction_accuracy": 0.0, "off_by_gt1": 0.0, "prediction_samples": 0}
        else:
            exact = sum(1 for oid in common if self.predicted[oid] == self.actual[oid])
            off = sum(1 for oid in common if abs(self.predicted[oid] - self.actual[oid]) > 1)
            stats = {
                "prediction_accuracy": exact / len(common),
                "off_by_gt1": off / len(common),
                "prediction_samples": len(common),
            }
        stats.update(
            {
                "dogi_feature_count": len(DOGI_RUNTIME_FEATURE_NAMES),
                "dogi_uses_lba": 1,
                "dogi_uses_freq_bit": 1,
                "dogi_uses_freq_bit2": 1,
                "dogi_uses_interval_bit": 1,
                "dogi_uses_seg_accessed": 1,
                "dogi_uses_prev_lba": 1,
                "dogi_runtime_feature_keys": len(self.avg_by_runtime_feature),
                "dogi_feature_samples": self.feature_samples,
                "dogi_prev_group_history_keys": len(self.avg_by_prev_group),
            }
        )
        return stats

    def _lba_bucket(self, lba: int) -> int:
        return lba // self.lba_bucket_size

    @staticmethod
    def _freq_bucket(value: int) -> int:
        for idx, threshold in enumerate(FREQUENCY_THRESHOLDS):
            if value <= threshold:
                return idx
        return len(FREQUENCY_THRESHOLDS)

    def _current_freq_bits(self, bucket: int, ts: int) -> int:
        window = ts // DOGI_FREQ_WINDOW
        last_window = self.last_freq_window_by_lba_bucket.get(bucket, window)
        bits = self.freq_bits_by_lba_bucket.get(bucket, 0)
        shift = max(0, min(8, window - last_window))
        if shift >= 8:
            bits = 0
        elif shift:
            bits >>= shift
        self.freq_bits_by_lba_bucket[bucket] = bits
        self.last_freq_window_by_lba_bucket[bucket] = window
        return bits

    def _features(self, event: dict) -> DogiFeatures:
        ts = int(event["ts"])
        lba = int(event["lba"])
        bucket = self._lba_bucket(lba)
        previous_lba_bucket = -1 if self.prev_lba is None else self._lba_bucket(self.prev_lba)
        last_ts = self.last_ts_by_lba_bucket.get(bucket)
        interval = None if last_ts is None else max(1, ts - last_ts)
        bits = self._current_freq_bits(bucket, ts)
        segment = lba // DOGI_SEGMENT_BLOCKS
        return DogiFeatures(
            lba_bucket=bucket,
            segment_id=segment,
            freq_bit=bits,
            freq_bit2=bits.bit_count(),
            interval_bit=LifetimePredictor.bucket_for_lifetime(interval),
            seg_accessed=self._freq_bucket(self.segment_writes[segment]),
            prev_lba_bucket=previous_lba_bucket,
            prev_group=self.prev_group_by_lba_bucket.get(bucket, -1),
        )

    def _predict_lifetime(self, features: DogiFeatures) -> float:
        weighted_sum = 0.0
        weight = 0.0
        candidates = [
            (self.avg_by_runtime_feature.get(features.runtime_key()), 4.0),
            (self.avg_by_lba_bucket.get(features.lba_bucket), 2.0),
            (self.avg_by_segment.get(features.segment_id), 1.0),
            (self.avg_by_prev_group.get(features.prev_group), 1.0 if features.prev_group >= 0 else 0.0),
            (self.global_avg, 0.5),
        ]
        for value, candidate_weight in candidates:
            if value is None or candidate_weight <= 0:
                continue
            weighted_sum += value * candidate_weight
            weight += candidate_weight
        return self.global_avg if weight == 0 else weighted_sum / weight

    def _observe_write(self, event: dict, features: DogiFeatures, group: int) -> None:
        ts = int(event["ts"])
        lba = int(event["lba"])
        bucket = features.lba_bucket
        self.freq_bits_by_lba_bucket[bucket] = self.freq_bits_by_lba_bucket.get(bucket, 0) | 0x80
        self.last_ts_by_lba_bucket[bucket] = ts
        self.segment_writes[lba // DOGI_SEGMENT_BLOCKS] += int(event["size_blocks"])
        self.prev_group_by_lba_bucket[bucket] = group
        self.prev_lba = lba

    @staticmethod
    def _update_avg(table: dict, key, lifetime: int, alpha: float = 0.20) -> None:
        old = table.get(key)
        table[key] = float(lifetime) if old is None else (1.0 - alpha) * old + alpha * lifetime


class SepbitStylePolicy(Policy):
    """Invalidation-density grouping from storage-visible block history.

    This is a compact SepBIT-style baseline, not a paper-faithful
    reimplementation. It groups writes by how frequently an LBA bucket has
    produced invalidations in the past. It intentionally cannot see PQC intent
    or epoch state.
    """

    name = "sepbit-style"

    def __init__(self, lba_bucket_size: int) -> None:
        self.lba_bucket_size = lba_bucket_size
        self.writes_by_bucket: Counter[int] = Counter()
        self.invalids_by_bucket: Counter[int] = Counter()
        self.last_invalid_ts: dict[int, int] = {}
        self.predicted: dict[int, int] = {}
        self.actual: dict[int, int] = {}

    def _lba_bucket(self, lba: int) -> int:
        return lba // self.lba_bucket_size

    def assign(self, event: dict) -> int:
        bucket = self._lba_bucket(event["lba"])
        writes = self.writes_by_bucket[bucket]
        invalids = self.invalids_by_bucket[bucket]
        invalid_density = invalids / max(1, writes)
        last_invalid = self.last_invalid_ts.get(bucket)
        recent_invalid = 0
        if last_invalid is not None and int(event["ts"]) - last_invalid <= 4 * LIFETIME_THRESHOLDS[0]:
            recent_invalid = 1

        if invalid_density >= 0.50:
            group = 0
        elif invalid_density >= 0.25:
            group = 1
        elif invalid_density >= 0.10 or recent_invalid:
            group = 2
        elif writes >= 32:
            group = 3
        else:
            group = 4
        self.predicted[event["object_id"]] = group
        self.writes_by_bucket[bucket] += int(event["size_blocks"])
        return group

    def observe_expire(self, event: dict, write_event: dict) -> None:
        bucket = self._lba_bucket(write_event["lba"])
        self.invalids_by_bucket[bucket] += int(write_event["size_blocks"])
        self.last_invalid_ts[bucket] = int(event["ts"])
        lifetime = int(event["ts"]) - int(write_event["ts"])
        self.actual[event["object_id"]] = min(4, LifetimePredictor.bucket_for_lifetime(lifetime))

    def extra_stats(self) -> dict[str, float]:
        common = set(self.predicted).intersection(self.actual)
        if not common:
            return {"prediction_accuracy": 0.0, "off_by_gt1": 0.0, "prediction_samples": 0}
        exact = sum(1 for oid in common if self.predicted[oid] == self.actual[oid])
        off = sum(1 for oid in common if abs(self.predicted[oid] - self.actual[oid]) > 1)
        return {
            "prediction_accuracy": exact / len(common),
            "off_by_gt1": off / len(common),
            "prediction_samples": len(common),
        }


class MidasStylePolicy(Policy):
    """Age/frequency heuristic grouping from storage-visible history.

    This approximates the MiDAS-style idea that frequently invalidated or
    repeatedly accessed regions should be separated from cold regions. It uses
    only LBA bucket history and cannot observe cryptographic death cohorts.
    """

    name = "midas-style"

    def __init__(self, lba_bucket_size: int) -> None:
        self.lba_bucket_size = lba_bucket_size
        self.avg_lifetime_by_bucket: dict[int, float] = {}
        self.write_count_by_bucket: Counter[int] = Counter()
        self.last_write_ts_by_bucket: dict[int, int] = {}
        self.global_avg = 8_192.0
        self.observed = 0
        self.predicted: dict[int, int] = {}
        self.actual: dict[int, int] = {}

    def _lba_bucket(self, lba: int) -> int:
        return lba // self.lba_bucket_size

    @staticmethod
    def _frequency_bucket(count: int) -> int:
        if count >= 512:
            return 0
        if count >= 128:
            return 1
        if count >= 32:
            return 2
        return 3

    def assign(self, event: dict) -> int:
        bucket = self._lba_bucket(event["lba"])
        ts = int(event["ts"])
        avg_lifetime = self.avg_lifetime_by_bucket.get(bucket, self.global_avg)
        last_write = self.last_write_ts_by_bucket.get(bucket)
        if last_write is not None:
            interval = max(1, ts - last_write)
            if interval <= LIFETIME_THRESHOLDS[0]:
                avg_lifetime *= 0.75
            elif interval >= LIFETIME_THRESHOLDS[2]:
                avg_lifetime *= 1.25
        life_bucket = min(5, LifetimePredictor.bucket_for_lifetime(int(avg_lifetime)))
        freq_bucket = self._frequency_bucket(self.write_count_by_bucket[bucket])
        if freq_bucket == 0:
            life_bucket = max(0, life_bucket - 1)
        elif freq_bucket == 3:
            life_bucket = min(5, life_bucket + 1)
        group = life_bucket
        self.predicted[event["object_id"]] = life_bucket
        self.write_count_by_bucket[bucket] += int(event["size_blocks"])
        self.last_write_ts_by_bucket[bucket] = ts
        return group

    def observe_expire(self, event: dict, write_event: dict) -> None:
        lifetime = int(event["ts"]) - int(write_event["ts"])
        actual_group = LifetimePredictor.bucket_for_lifetime(lifetime)
        self.actual[event["object_id"]] = actual_group
        bucket = self._lba_bucket(write_event["lba"])
        old = self.avg_lifetime_by_bucket.get(bucket, self.global_avg)
        self.avg_lifetime_by_bucket[bucket] = 0.80 * old + 0.20 * lifetime
        self.global_avg = (self.global_avg * self.observed + lifetime) / (self.observed + 1)
        self.observed += 1

    def extra_stats(self) -> dict[str, float]:
        common = set(self.predicted).intersection(self.actual)
        if not common:
            return {"prediction_accuracy": 0.0, "off_by_gt1": 0.0, "prediction_samples": 0}
        exact = sum(1 for oid in common if self.predicted[oid] == self.actual[oid])
        off = sum(1 for oid in common if abs(self.predicted[oid] - self.actual[oid]) > 1)
        return {
            "prediction_accuracy": exact / len(common),
            "off_by_gt1": off / len(common),
            "prediction_samples": len(common),
        }


class EpochOraclePolicy(Policy):
    name = "epoch-oracle"

    def assign(self, event: dict) -> int:
        expire_ts = event.get("expire_ts")
        lifetime = None if expire_ts is None else int(expire_ts) - int(event["ts"])
        return LifetimePredictor.bucket_for_lifetime(lifetime)


class QuasarPolicy(Policy):
    """Intent/epoch-aware death-cohort placement.

    The policy deliberately does not use exact `expire_ts`; it uses lifecycle
    labels that the cryptographic stack can expose cheaply.
    """

    name = "quasar"

    def __init__(
        self,
        *,
        zone_capacity: int,
        cert_epochs: int,
        bin_width: int,
        min_epoch_fill: float,
        open_zone_budget: int,
        overflow_enabled: bool,
        secret_priority: bool,
    ) -> None:
        self.zone_capacity = zone_capacity
        self.cert_epochs = max(1, cert_epochs)
        self.bin_width = max(1, bin_width)
        self.min_epoch_fill = max(0.0, min_epoch_fill)
        self.open_zone_budget = max(1, open_zone_budget)
        self.overflow_enabled = overflow_enabled
        self.secret_priority = secret_priority
        self.family_to_group: dict[tuple, int] = {}
        self.group_to_family: dict[int, tuple] = {}
        self.next_group = 1_000
        self.epoch_seen_blocks: Counter[tuple[str, int]] = Counter()
        self.active_exact_families: set[tuple] = set()
        self.recent_families: deque[tuple] = deque()
        self.exact_epoch_writes = 0
        self.binned_epoch_writes = 0
        self.overflow_writes = 0
        self.payload_writes = 0
        self.append_log_writes = 0
        self.rotation_writes = 0

    def is_quasar(self) -> bool:
        return True

    def _group(self, family: tuple) -> int:
        group = self.family_to_group.get(family)
        if group is not None:
            return group
        group = self.next_group
        self.next_group += 1
        self.family_to_group[family] = group
        self.group_to_family[group] = family
        self.recent_families.append(family)
        return group

    def _exact_budget_available(self, family: tuple, intent: str) -> bool:
        if family in self.active_exact_families:
            return True
        if self.secret_priority and intent == "EPHEMERAL_SECRET":
            return True
        return len(self.active_exact_families) < self.open_zone_budget

    def _epoch_family(self, event: dict, intent: str, epoch_id: int) -> tuple:
        seen_key = (intent, epoch_id)
        self.epoch_seen_blocks[seen_key] += int(event["size_blocks"])
        exact_family = ("EPOCH_SECRET", epoch_id, intent, event.get("security_class", "SECRET"))
        enough_fill = self.epoch_seen_blocks[seen_key] >= self.min_epoch_fill * self.zone_capacity
        if enough_fill and self._exact_budget_available(exact_family, intent):
            self.active_exact_families.add(exact_family)
            self.exact_epoch_writes += 1
            return exact_family
        epoch_bucket = epoch_id // self.bin_width
        self.binned_epoch_writes += 1
        return ("EPOCH_BIN", epoch_bucket, intent, event.get("security_class", "SECRET"))

    def assign(self, event: dict) -> int:
        confidence = event.get("confidence", "exact")
        intent = event.get("intent", "UNKNOWN")
        if confidence == "UNKNOWN" or intent == "UNKNOWN":
            self.overflow_writes += 1
            if self.overflow_enabled:
                return self._group(("OVERFLOW", event.get("expire_class", "UNKNOWN")))
            return self._group(("PAYLOAD",))

        epoch_id = int(event.get("epoch_id", 0))
        if intent in SECRET_INTENTS:
            return self._group(self._epoch_family(event, intent, epoch_id))
        if intent == "CERT_METADATA":
            self.rotation_writes += 1
            rotation_epoch = epoch_id // self.cert_epochs
            return self._group(("ROTATION", rotation_epoch, intent))
        if intent == "SIGNATURE_LOG":
            self.append_log_writes += 1
            return self._group(("APPEND_LOG", intent))
        if intent == "PAYLOAD":
            self.payload_writes += 1
            return self._group(("PAYLOAD",))

        self.overflow_writes += 1
        return self._group(("OVERFLOW", "UNKNOWN"))

    def family_type(self, group: int) -> str:
        family = self.group_to_family.get(group)
        if not family:
            return "GENERIC"
        return str(family[0])

    def extra_stats(self) -> dict[str, float]:
        return {
            "quasar_exact_epoch_writes": self.exact_epoch_writes,
            "quasar_binned_epoch_writes": self.binned_epoch_writes,
            "quasar_overflow_writes": self.overflow_writes,
            "quasar_rotation_writes": self.rotation_writes,
            "quasar_append_log_writes": self.append_log_writes,
            "quasar_payload_writes": self.payload_writes,
            "quasar_family_count": len(self.family_to_group),
        }


class AdaptiveQuasarPolicy(QuasarPolicy):
    """Adaptive admission controller for adversarial open-zone pressure.

    Exact epoch placement is best for exposure but can waste zones when many
    tiny tenant epochs are active. This policy chooses among exact epoch,
    tenant-local bin, and coarse global bin using only lifecycle labels and
    coarse admission knobs.
    """

    name = "quasar-adaptive"

    def __init__(
        self,
        *,
        zone_capacity: int,
        cert_epochs: int,
        bin_width: int,
        min_epoch_fill: float,
        open_zone_budget: int,
        overflow_enabled: bool,
        secret_priority: bool,
        exact_min_blocks: int,
        tenant_bin_width: int,
        coarse_bin_width: int,
        coarse_pressure: float,
        family_pressure: float,
        urgent_lifetime: int,
    ) -> None:
        super().__init__(
            zone_capacity=zone_capacity,
            cert_epochs=cert_epochs,
            bin_width=bin_width,
            min_epoch_fill=min_epoch_fill,
            open_zone_budget=open_zone_budget,
            overflow_enabled=overflow_enabled,
            secret_priority=secret_priority,
        )
        fill_threshold = int(math.ceil(self.min_epoch_fill * self.zone_capacity))
        self.exact_min_blocks = max(1, exact_min_blocks, fill_threshold)
        self.tenant_bin_width = max(1, tenant_bin_width)
        self.coarse_bin_width = max(1, coarse_bin_width)
        self.coarse_pressure = min(1.0, max(0.0, coarse_pressure))
        self.family_pressure = max(1.0, family_pressure)
        self.urgent_lifetime = max(0, urgent_lifetime)
        self.tenant_bin_writes = 0
        self.coarse_bin_writes = 0
        self.pressure_coarse_bin_writes = 0
        self.urgent_tenant_bin_writes = 0
        self.exact_rejected_budget_writes = 0
        self.exact_rejected_size_writes = 0

    def _pressure(self) -> float:
        return len(self.active_exact_families) / max(1, self.open_zone_budget)

    def _family_pressure(self) -> float:
        return len(self.family_to_group) / max(1, self.open_zone_budget)

    @staticmethod
    def _tenant_id(event: dict) -> str:
        return str(event.get("tenant_id", "tenant0"))

    @staticmethod
    def _lifetime_hint(event: dict) -> Optional[int]:
        expire_ts = event.get("expire_ts")
        if expire_ts is None:
            return None
        return max(0, int(expire_ts) - int(event.get("ts", 0)))

    def _tenant_bin_family(self, event: dict, intent: str, epoch_id: int) -> tuple:
        tenant = self._tenant_id(event)
        bucket = epoch_id // self.tenant_bin_width
        self.binned_epoch_writes += 1
        self.tenant_bin_writes += 1
        return ("EPOCH_BIN", "tenant", tenant, bucket, intent, event.get("security_class", "SECRET"))

    def _coarse_bin_family(self, event: dict, intent: str, epoch_id: int) -> tuple:
        bucket = epoch_id // self.coarse_bin_width
        self.binned_epoch_writes += 1
        self.coarse_bin_writes += 1
        return ("EPOCH_BIN", "coarse", bucket, intent, event.get("security_class", "SECRET"))

    def _epoch_family(self, event: dict, intent: str, epoch_id: int) -> tuple:
        seen_key = (intent, epoch_id)
        self.epoch_seen_blocks[seen_key] += int(event["size_blocks"])
        exact_family = ("EPOCH_SECRET", epoch_id, intent, event.get("security_class", "SECRET"))
        enough_fill = self.epoch_seen_blocks[seen_key] >= self.exact_min_blocks
        exact_allowed = self._exact_budget_available(exact_family, intent)
        if enough_fill and exact_allowed:
            self.active_exact_families.add(exact_family)
            self.exact_epoch_writes += 1
            return exact_family

        if not enough_fill:
            self.exact_rejected_size_writes += 1
        elif not exact_allowed:
            self.exact_rejected_budget_writes += 1

        lifetime = self._lifetime_hint(event)
        urgent = lifetime is not None and lifetime <= self.urgent_lifetime
        if self._family_pressure() >= self.family_pressure:
            self.pressure_coarse_bin_writes += 1
            return self._coarse_bin_family(event, intent, epoch_id)
        if intent == "EPHEMERAL_SECRET" and urgent:
            self.urgent_tenant_bin_writes += 1
            return self._tenant_bin_family(event, intent, epoch_id)
        if self._pressure() >= self.coarse_pressure or not exact_allowed:
            self.pressure_coarse_bin_writes += 1
            return self._coarse_bin_family(event, intent, epoch_id)
        return self._tenant_bin_family(event, intent, epoch_id)

    def extra_stats(self) -> dict[str, float]:
        stats = super().extra_stats()
        stats.update(
            {
                "quasar_adaptive_exact_min_blocks": self.exact_min_blocks,
                "quasar_adaptive_tenant_bin_width": self.tenant_bin_width,
                "quasar_adaptive_coarse_bin_width": self.coarse_bin_width,
                "quasar_adaptive_coarse_pressure": self.coarse_pressure,
                "quasar_adaptive_family_pressure": self.family_pressure,
                "quasar_adaptive_urgent_lifetime": self.urgent_lifetime,
                "quasar_tenant_bin_writes": self.tenant_bin_writes,
                "quasar_coarse_bin_writes": self.coarse_bin_writes,
                "quasar_pressure_coarse_bin_writes": self.pressure_coarse_bin_writes,
                "quasar_urgent_tenant_bin_writes": self.urgent_tenant_bin_writes,
                "quasar_exact_rejected_budget_writes": self.exact_rejected_budget_writes,
                "quasar_exact_rejected_size_writes": self.exact_rejected_size_writes,
            }
        )
        return stats


class QuasarDogiHybridPolicy(Policy):
    """QUASAR for PQC lifecycle data, DOGI-style fallback for payload.

    This models the realistic deployment stance: QUASAR should not replace a
    good general-purpose placement policy for ordinary payload blocks. It should
    add the missing cryptographic death-cohort signal for PQC metadata and route
    storage-history-friendly payload traffic to the existing learned/history
    allocator.
    """

    name = "quasar-dogi-hybrid"

    def __init__(
        self,
        *,
        quasar: QuasarPolicy,
        dogi: DogiHistoryPolicy,
    ) -> None:
        self.quasar = quasar
        self.dogi = dogi
        self.payload_fallback_writes = 0
        self.quasar_managed_writes = 0
        self.dogi_managed_objects: set[int] = set()

    def is_quasar(self) -> bool:
        return True

    def _use_quasar(self, event: dict) -> bool:
        intent = event.get("intent", "UNKNOWN")
        confidence = event.get("confidence", "exact")
        if confidence == "UNKNOWN" or intent == "UNKNOWN":
            return False
        return intent in {"EPHEMERAL_SECRET", "KEM_ARTIFACT", "CERT_METADATA", "SIGNATURE_LOG"}

    def assign(self, event: dict) -> int:
        if self._use_quasar(event):
            self.quasar_managed_writes += 1
            return self.quasar.assign(event)
        self.payload_fallback_writes += 1
        self.dogi_managed_objects.add(int(event["object_id"]))
        return self.dogi.assign(event)

    def observe_expire(self, event: dict, write_event: dict) -> None:
        object_id = int(event["object_id"])
        intent = write_event.get("intent", "UNKNOWN")
        if object_id in self.dogi_managed_objects or intent in {"PAYLOAD", "UNKNOWN"}:
            self.dogi.observe_expire(event, write_event)
            self.dogi_managed_objects.discard(object_id)

    def family_type(self, group: int) -> str:
        return self.quasar.family_type(group)

    def extra_stats(self) -> dict[str, float]:
        stats = self.quasar.extra_stats()
        stats.update(
            {
                "hybrid_payload_fallback_writes": self.payload_fallback_writes,
                "hybrid_quasar_managed_writes": self.quasar_managed_writes,
            }
        )
        stats.update({f"fallback_{key}": value for key, value in self.dogi.extra_stats().items()})
        return stats


class Simulator:
    def __init__(
        self,
        *,
        policy: Policy,
        zone_count: int,
        zone_capacity: int,
        min_free_zones: int,
        residual_threshold: int,
        hint_missing_rate: float,
        wrong_epoch_rate: float,
        straggler_rate: float,
        random_seed: int,
        base_write_ns: int,
        gc_copy_ns: int,
        policy_cpu_ns_per_write: int,
        operation_log: Optional[list[dict]] = None,
    ) -> None:
        self.policy = policy
        self.zone_count = zone_count
        self.zone_capacity = zone_capacity
        self.min_free_zones = min_free_zones
        self.residual_threshold = max(0, residual_threshold)
        self.rng = random.Random(random_seed)
        self.hint_missing_rate = hint_missing_rate
        self.wrong_epoch_rate = wrong_epoch_rate
        self.straggler_rate = straggler_rate
        self.base_write_ns = base_write_ns
        self.gc_copy_ns = gc_copy_ns
        self.policy_cpu_ns_per_write = policy_cpu_ns_per_write
        self.operation_log = operation_log

        self.free_zone_ids = list(range(zone_count))
        self.zones: dict[int, Zone] = {}
        self.active_by_group: dict[int, Zone] = {}
        self.refs: dict[int, list[tuple[int, int]]] = defaultdict(list)
        self.write_events: dict[int, dict] = {}
        self.user_write_blocks = 0
        self.gc_write_blocks = 0
        self.reset_count = 0
        self.quasar_reclaim_checks = 0
        self.reset_eligible_zones = 0
        self.residual_live_blocks = 0
        self.migrated_residual_blocks = 0
        self.expired_blocks_by_ts: Counter[int] = Counter()
        self.failed_gc = 0
        self.opened_zones = 0
        self.reset_zone_fills: list[float] = []
        self.write_latency_ns: list[int] = []
        self.hint_missing_injected = 0
        self.wrong_epoch_injected = 0
        self.stragglers_injected = 0
        self.stale_secret_block_seconds = 0
        self.max_secret_exposure_time = 0
        self.current_stale_secret_blocks = 0
        self.current_stale_secret_expired_ts_sum = 0
        self.current_stale_secret_ts_counts: Counter[int] = Counter()
        self.current_stale_secret_ts_heap: list[int] = []
        self.current_ts = 0
        self.reset_secret_tenant_impurity_weighted = 0.0
        self.reset_secret_epoch_impurity_weighted = 0.0
        self.reset_secret_impurity_blocks = 0

    def _record_operation(self, op: str, **fields) -> None:
        if self.operation_log is None:
            return
        row = {"op": op, "ts": self.current_ts}
        row.update(fields)
        self.operation_log.append(row)

    def _policy_event(self, event: dict) -> dict:
        if not self.policy.is_quasar():
            return event
        policy_event = dict(event)
        if self.rng.random() < self.hint_missing_rate:
            policy_event["confidence"] = "UNKNOWN"
            policy_event["intent"] = "UNKNOWN"
            self.hint_missing_injected += 1
        if self.rng.random() < self.wrong_epoch_rate:
            policy_event["epoch_id"] = int(policy_event.get("epoch_id", 0)) + self.rng.choice([-2, -1, 1, 2])
            self.wrong_epoch_injected += 1
        return policy_event

    def _open_zone(self, group: int, *, allow_gc: bool = True) -> Zone:
        if allow_gc:
            self._ensure_free_zone()
            current = self.active_by_group.get(group)
            if current is not None and current.free > 0 and not current.sealed:
                return current
        if not self.free_zone_ids:
            raise RuntimeError("out of free zones; increase --zones or lower workload pressure")
        zone_id = self.free_zone_ids.pop()
        zone = Zone(zone_id=zone_id, capacity=self.zone_capacity, group=group)
        self.zones[zone_id] = zone
        self.active_by_group[group] = zone
        self.opened_zones += 1
        return zone

    def _ensure_free_zone(self) -> None:
        while len(self.free_zone_ids) <= self.min_free_zones:
            before = len(self.free_zone_ids)
            if self._reset_any_fully_invalid_zone():
                continue
            if not self._gc_once():
                break
            # A victim with many live blocks can consume a destination zone and
            # produce no immediate free-zone progress. Let the foreground open
            # its reserved zone instead of cleaning repeatedly in one burst.
            if len(self.free_zone_ids) <= before:
                break

    def _append_one(self, block: Block, *, is_gc: bool, account_user: bool = True) -> tuple[int, int]:
        group = block.group
        zone = self.active_by_group.get(group)
        if zone is None:
            zone = self._open_zone(group, allow_gc=not is_gc)
        if zone.free == 0:
            zone.sealed = True
            zone = self._open_zone(group, allow_gc=not is_gc)
        if zone.first_write_ts is None:
            zone.first_write_ts = self.current_ts
        zone.last_write_ts = self.current_ts
        if is_gc:
            self.gc_write_blocks += 1
        elif account_user:
            self.user_write_blocks += 1
        offset = len(zone.blocks)
        zone.blocks.append(block)
        zone.live_blocks += 1
        self._record_operation(
            "append",
            zone_id=zone.zone_id,
            group=group,
            blocks=1,
            is_gc=is_gc,
            account_user=account_user,
            object_id=block.object_id,
            intent=block.intent,
            epoch_id=block.epoch_id,
        )
        return zone.zone_id, offset

    def _account_expired_secret(self, block: Block, reset_ts: int) -> None:
        if block.expired_ts is None or not block.is_secret:
            return
        exposure = max(0, reset_ts - block.expired_ts)
        self.stale_secret_block_seconds += exposure
        self.max_secret_exposure_time = max(self.max_secret_exposure_time, exposure)
        self._untrack_stale_secret(block)
        block.expired_ts = None

    def _track_stale_secret(self, block: Block) -> None:
        if block.expired_ts is None or not block.is_secret:
            return
        expired_ts = int(block.expired_ts)
        self.current_stale_secret_blocks += 1
        self.current_stale_secret_expired_ts_sum += expired_ts
        self.current_stale_secret_ts_counts[expired_ts] += 1
        heapq.heappush(self.current_stale_secret_ts_heap, expired_ts)

    def _untrack_stale_secret(self, block: Block) -> None:
        if block.expired_ts is None or not block.is_secret:
            return
        expired_ts = int(block.expired_ts)
        self.current_stale_secret_blocks -= 1
        self.current_stale_secret_expired_ts_sum -= expired_ts
        self.current_stale_secret_ts_counts[expired_ts] -= 1
        if self.current_stale_secret_ts_counts[expired_ts] <= 0:
            del self.current_stale_secret_ts_counts[expired_ts]

    def _remove_zone(self, zone: Zone, reset_ts: int) -> None:
        self._account_reset_impurity(zone)
        for block in zone.blocks:
            self._account_expired_secret(block, reset_ts)
        self.reset_zone_fills.append(zone.fill)
        self._record_operation(
            "reset_zone",
            ts=reset_ts,
            zone_id=zone.zone_id,
            group=zone.group,
            fill=zone.fill,
            live_blocks=zone.live_count,
            invalid_blocks=zone.invalid_count,
        )
        if self.active_by_group.get(zone.group) is zone:
            del self.active_by_group[zone.group]
        del self.zones[zone.zone_id]
        self.free_zone_ids.append(zone.zone_id)
        self.reset_count += 1

    def _account_reset_impurity(self, zone: Zone) -> None:
        secret_blocks = [block for block in zone.blocks if block.is_secret]
        if not secret_blocks:
            return
        count = len(secret_blocks)
        tenant_counts = Counter(block.tenant_id for block in secret_blocks)
        epoch_counts = Counter(block.epoch_id for block in secret_blocks)
        tenant_impurity = 1.0 - (max(tenant_counts.values()) / count)
        epoch_impurity = 1.0 - (max(epoch_counts.values()) / count)
        self.reset_secret_tenant_impurity_weighted += tenant_impurity * count
        self.reset_secret_epoch_impurity_weighted += epoch_impurity * count
        self.reset_secret_impurity_blocks += count

    def _migrate_live_blocks(self, zone: Zone) -> int:
        live_blocks = [block for block in zone.blocks if block.live]
        for block in live_blocks:
            block.live = False
            zone.live_blocks -= 1
            new_block = Block(
                object_id=block.object_id,
                epoch_id=block.epoch_id,
                intent=block.intent,
                group=block.group,
                tenant_id=block.tenant_id,
                live=True,
            )
            ref = self._append_one(new_block, is_gc=True)
            self.refs[block.object_id].append(ref)
        return len(live_blocks)

    def _reset_any_fully_invalid_zone(self) -> bool:
        candidates = [zone for zone in self.zones.values() if zone.invalid_count > 0 and zone.live_count == 0]
        if not candidates:
            return False
        zone = max(candidates, key=lambda z: len(z.blocks))
        self._remove_zone(zone, self.current_ts)
        return True

    def _gc_once(self) -> bool:
        candidates = [
            zone
            for zone in self.zones.values()
            if zone.sealed and zone.invalid_count > 0 and zone not in self.active_by_group.values()
        ]
        if not candidates:
            self.failed_gc += 1
            return False
        victim = max(candidates, key=lambda zone: (zone.invalid_ratio, len(zone.blocks)))
        self._migrate_live_blocks(victim)
        self._remove_zone(victim, self.current_ts)
        return True

    def write(self, event: dict, *, account_user: bool = True) -> None:
        before_gc_writes = self.gc_write_blocks
        before_user_writes = self.user_write_blocks
        policy_event = self._policy_event(event)
        group = self.policy.assign(policy_event)
        self.write_events[event["object_id"]] = event
        for _ in range(int(event["size_blocks"])):
            block = Block(
                object_id=event["object_id"],
                epoch_id=int(event.get("epoch_id", 0)),
                intent=event.get("intent", "UNKNOWN"),
                group=group,
                tenant_id=str(event.get("tenant_id", "tenant0")),
            )
            ref = self._append_one(block, is_gc=False, account_user=account_user)
            self.refs[event["object_id"]].append(ref)
        if account_user:
            user_delta = self.user_write_blocks - before_user_writes
            gc_delta = self.gc_write_blocks - before_gc_writes
            latency = (
                user_delta * (self.base_write_ns + self.policy_cpu_ns_per_write)
                + gc_delta * self.gc_copy_ns
            )
            self.write_latency_ns.append(latency)

    def _try_quasar_reclaim(self, zones_touched: set[int]) -> None:
        if not self.policy.is_quasar():
            return
        for zone_id in list(zones_touched):
            zone = self.zones.get(zone_id)
            if zone is None:
                continue
            family_type = self.policy.family_type(zone.group)
            if family_type not in RESETTABLE_QUASAR_FAMILIES:
                continue
            if zone.invalid_count == 0:
                continue
            self.quasar_reclaim_checks += 1
            if zone.live_count == 0:
                self.reset_eligible_zones += 1
                self._remove_zone(zone, self.current_ts)
            elif zone.live_count <= self.residual_threshold:
                self.reset_eligible_zones += 1
                self.residual_live_blocks += zone.live_count
                migrated = self._migrate_live_blocks(zone)
                self.migrated_residual_blocks += migrated
                self._remove_zone(zone, self.current_ts)

    def expire(self, event: dict) -> None:
        if self.policy.is_quasar() and self.rng.random() < self.straggler_rate:
            self.stragglers_injected += 1
            return

        object_id = event["object_id"]
        write_event = self.write_events.get(object_id)
        if write_event:
            self.policy.observe_expire(event, write_event)
        refs = self.refs.pop(object_id, [])
        expired = 0
        zones_touched: set[int] = set()
        for zone_id, offset in refs:
            zone = self.zones.get(zone_id)
            if zone is None or offset >= len(zone.blocks):
                continue
            block = zone.blocks[offset]
            if block.object_id == object_id and block.live:
                block.live = False
                block.expired_ts = int(event["ts"])
                self._track_stale_secret(block)
                zone.live_blocks -= 1
                expired += 1
                zones_touched.add(zone_id)
        if expired:
            self.expired_blocks_by_ts[int(event["ts"])] += expired
        self._try_quasar_reclaim(zones_touched)

    def run(self, trace_path: Path) -> dict[str, float]:
        with trace_path.open("r", encoding="utf-8") as trace:
            for line in trace:
                event = json.loads(line)
                self.current_ts = int(event["ts"])
                if event["op"] == "write":
                    self.write(event)
                elif event["op"] == "prefill":
                    self.write(event, account_user=False)
                elif event["op"] == "expire":
                    self.expire(event)
                else:
                    raise ValueError(f"unknown op: {event['op']}")
        while len(self.free_zone_ids) <= self.min_free_zones:
            if not self._reset_any_fully_invalid_zone() and not self._gc_once():
                break
        return self.stats()

    def _weighted_impurity(self, field: str, *, secret_only: bool = False) -> float:
        total_live = 0
        weighted = 0.0
        for zone in self.zones.values():
            values = [
                getattr(block, field)
                for block in zone.blocks
                if block.live and (not secret_only or block.is_secret)
            ]
            if not values:
                continue
            counts = Counter(values)
            live = len(values)
            impurity = 1.0 - (max(counts.values()) / live)
            weighted += impurity * live
            total_live += live
        return 0.0 if total_live == 0 else weighted / total_live

    def _remaining_secret_exposure(self) -> tuple[int, int, int]:
        while (
            self.current_stale_secret_ts_heap
            and self.current_stale_secret_ts_counts.get(self.current_stale_secret_ts_heap[0], 0) <= 0
        ):
            heapq.heappop(self.current_stale_secret_ts_heap)
        remaining = self.current_stale_secret_blocks
        block_seconds = max(
            0,
            self.current_ts * self.current_stale_secret_blocks
            - self.current_stale_secret_expired_ts_sum,
        )
        if remaining and self.current_stale_secret_ts_heap:
            max_exposure = max(0, self.current_ts - self.current_stale_secret_ts_heap[0])
        else:
            max_exposure = 0
        return remaining, block_seconds, max_exposure

    def _scan_remaining_secret_exposure(self) -> tuple[int, int, int]:
        remaining = 0
        block_seconds = 0
        max_exposure = 0
        for zone in self.zones.values():
            for block in zone.blocks:
                if block.expired_ts is None or not block.is_secret:
                    continue
                exposure = max(0, self.current_ts - block.expired_ts)
                remaining += 1
                block_seconds += exposure
                max_exposure = max(max_exposure, exposure)
        return remaining, block_seconds, max_exposure

    def _zone_fill_stats(self) -> tuple[float, float, float]:
        fills = self.reset_zone_fills + [zone.fill for zone in self.zones.values()]
        if not fills:
            return 0.0, 0.0, 0.0
        fills_sorted = sorted(fills)
        p10_idx = max(0, min(len(fills_sorted) - 1, math.ceil(0.10 * len(fills_sorted)) - 1))
        return sum(fills) / len(fills), fills_sorted[p10_idx], min(fills)

    def stats(self) -> dict[str, float]:
        waf = (self.user_write_blocks + self.gc_write_blocks) / max(1, self.user_write_blocks)
        live_blocks = sum(zone.live_count for zone in self.zones.values())
        invalid_blocks = sum(zone.invalid_count for zone in self.zones.values())
        occupied_blocks = live_blocks + invalid_blocks
        used_zones = len(self.zones)
        zone_utilization = occupied_blocks / max(1, used_zones * self.zone_capacity)
        lifetime_zone_utilization = (
            (self.user_write_blocks + self.gc_write_blocks)
            / max(1, self.opened_zones * self.zone_capacity)
        )
        fill_avg, fill_p10, fill_min = self._zone_fill_stats()
        max_burst = max(self.expired_blocks_by_ts.values()) if self.expired_blocks_by_ts else 0
        p99_burst = percentile(list(self.expired_blocks_by_ts.values()), 99)
        remaining_secret, remaining_block_seconds, remaining_max_exposure = self._remaining_secret_exposure()
        reset_eligibility = (
            self.reset_eligible_zones / self.quasar_reclaim_checks if self.quasar_reclaim_checks else 0.0
        )
        result = {
            "user_write_blocks": self.user_write_blocks,
            "gc_write_blocks": self.gc_write_blocks,
            "waf": waf,
            "resets": self.reset_count,
            "opened_zones": self.opened_zones,
            "used_zones": used_zones,
            "zone_utilization": zone_utilization,
            "lifetime_zone_utilization": lifetime_zone_utilization,
            "closed_zone_fill_avg": fill_avg,
            "closed_zone_fill_p10": fill_p10,
            "closed_zone_fill_min": fill_min,
            "live_blocks": live_blocks,
            "invalid_blocks": invalid_blocks,
            "max_expire_burst_blocks": max_burst,
            "p99_expire_burst_blocks": p99_burst,
            "epoch_impurity": self._weighted_impurity("epoch_id"),
            "intent_impurity": self._weighted_impurity("intent"),
            "tenant_impurity": self._weighted_impurity("tenant_id"),
            "secret_epoch_impurity": self._weighted_impurity("epoch_id", secret_only=True),
            "secret_tenant_impurity": self._weighted_impurity("tenant_id", secret_only=True),
            "reset_secret_tenant_impurity": (
                self.reset_secret_tenant_impurity_weighted / self.reset_secret_impurity_blocks
                if self.reset_secret_impurity_blocks
                else 0.0
            ),
            "reset_secret_epoch_impurity": (
                self.reset_secret_epoch_impurity_weighted / self.reset_secret_impurity_blocks
                if self.reset_secret_impurity_blocks
                else 0.0
            ),
            "reset_secret_impurity_blocks": self.reset_secret_impurity_blocks,
            "reset_eligibility": reset_eligibility,
            "reset_eligible_zones": self.reset_eligible_zones,
            "quasar_reclaim_checks": self.quasar_reclaim_checks,
            "residual_live_blocks": self.residual_live_blocks,
            "migrated_residual_blocks": self.migrated_residual_blocks,
            "stale_secret_blocks_remaining": remaining_secret,
            "stale_secret_block_seconds": self.stale_secret_block_seconds + remaining_block_seconds,
            "max_secret_exposure_time": max(self.max_secret_exposure_time, remaining_max_exposure),
            "hint_missing_injected": self.hint_missing_injected,
            "wrong_epoch_injected": self.wrong_epoch_injected,
            "stragglers_injected": self.stragglers_injected,
            "hint_bytes_per_write": 32 if self.policy.is_quasar() else 0,
            "policy_cpu_ns_per_write": self.policy_cpu_ns_per_write,
            "estimated_policy_cpu_ns": self.policy_cpu_ns_per_write * self.user_write_blocks,
            "estimated_gc_copy_ns": self.gc_copy_ns * self.gc_write_blocks,
            "estimated_mean_write_service_ns": (
                self.base_write_ns
                + self.policy_cpu_ns_per_write
                + (self.gc_write_blocks / max(1, self.user_write_blocks)) * self.gc_copy_ns
            ),
            "write_latency_p50_ns": percentile(self.write_latency_ns, 50),
            "write_latency_p95_ns": percentile(self.write_latency_ns, 95),
            "write_latency_p99_ns": percentile(self.write_latency_ns, 99),
            "write_latency_max_ns": max(self.write_latency_ns) if self.write_latency_ns else 0,
            "failed_gc_attempts": self.failed_gc,
        }
        result.update(self.policy.extra_stats())
        return result


def percentile(values: list[int], pct: int) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = math.ceil((pct / 100) * len(values)) - 1
    idx = max(0, min(idx, len(values) - 1))
    return float(values[idx])


def policy_cpu_cost(args: argparse.Namespace, policy_name: str) -> int:
    if policy_name == "dogi-history":
        return int(args.dogi_ml_ns_per_batch / max(1, args.dogi_batch_size))
    if policy_name in {"quasar-dogi-hybrid", "quasar-adaptive-hybrid"}:
        return int(args.dogi_ml_ns_per_batch / max(1, args.dogi_batch_size)) + args.quasar_hint_ns
    if policy_name in {"sepbit-style", "midas-style"}:
        return 120
    if policy_name in {"quasar", "quasar-adaptive"}:
        return args.quasar_hint_ns
    return 0


def quasar_open_zone_budget(args: argparse.Namespace) -> int:
    open_zone_budget = args.quasar_open_zone_budget
    if open_zone_budget <= 0:
        open_zone_budget = max(1, int((args.zones - args.min_free_zones) * 0.8))
    return open_zone_budget


def make_quasar_policy(args: argparse.Namespace, *, adaptive: bool = False) -> QuasarPolicy:
    policy_cls = AdaptiveQuasarPolicy if adaptive else QuasarPolicy
    kwargs = {
        "zone_capacity": args.zone_capacity,
        "cert_epochs": args.quasar_cert_epochs,
        "bin_width": args.quasar_bin_width,
        "min_epoch_fill": args.quasar_min_epoch_fill,
        "open_zone_budget": quasar_open_zone_budget(args),
        "overflow_enabled": not args.quasar_disable_overflow,
        "secret_priority": not args.quasar_disable_secret_priority,
    }
    if adaptive:
        kwargs.update(
            {
                "exact_min_blocks": getattr(args, "quasar_adaptive_exact_min_blocks", 4),
                "tenant_bin_width": getattr(args, "quasar_adaptive_tenant_bin_width", 16),
                "coarse_bin_width": getattr(args, "quasar_adaptive_coarse_bin_width", 32_000_000),
                "coarse_pressure": getattr(args, "quasar_adaptive_coarse_pressure", 0.75),
                "family_pressure": getattr(args, "quasar_adaptive_family_pressure", 8.0),
                "urgent_lifetime": getattr(args, "quasar_adaptive_urgent_lifetime", 32),
            }
        )
    return policy_cls(**kwargs)


def run_policy(args: argparse.Namespace, policy_name: str) -> dict[str, float]:
    if policy_name == "fifo":
        policy: Policy = FifoPolicy()
    elif policy_name == "sepbit-style":
        policy = SepbitStylePolicy(args.lba_bucket_size)
    elif policy_name == "midas-style":
        policy = MidasStylePolicy(args.lba_bucket_size)
    elif policy_name == "dogi-history":
        policy = DogiHistoryPolicy(args.lba_bucket_size)
    elif policy_name == "quasar":
        policy = make_quasar_policy(args)
    elif policy_name == "quasar-adaptive":
        policy = make_quasar_policy(args, adaptive=True)
    elif policy_name == "quasar-dogi-hybrid":
        policy = QuasarDogiHybridPolicy(
            quasar=make_quasar_policy(args),
            dogi=DogiHistoryPolicy(args.lba_bucket_size),
        )
    elif policy_name == "quasar-adaptive-hybrid":
        policy = QuasarDogiHybridPolicy(
            quasar=make_quasar_policy(args, adaptive=True),
            dogi=DogiHistoryPolicy(args.lba_bucket_size),
        )
    elif policy_name == "epoch-oracle":
        policy = EpochOraclePolicy()
    else:
        raise ValueError(policy_name)

    residual_threshold = 0
    quasar_policy_names = {"quasar", "quasar-dogi-hybrid", "quasar-adaptive", "quasar-adaptive-hybrid"}
    if policy_name in quasar_policy_names:
        residual_threshold = args.quasar_residual_threshold
        if residual_threshold < 0:
            residual_threshold = int(args.zone_capacity * args.quasar_residual_fraction)

    sim = Simulator(
        policy=policy,
        zone_count=args.zones,
        zone_capacity=args.zone_capacity,
        min_free_zones=args.min_free_zones,
        residual_threshold=residual_threshold,
        hint_missing_rate=args.hint_missing_rate if policy_name in quasar_policy_names else 0.0,
        wrong_epoch_rate=args.wrong_epoch_rate if policy_name in quasar_policy_names else 0.0,
        straggler_rate=args.straggler_rate if policy_name in quasar_policy_names else 0.0,
        random_seed=args.seed,
        base_write_ns=args.base_write_ns,
        gc_copy_ns=args.gc_copy_ns,
        policy_cpu_ns_per_write=policy_cpu_cost(args, policy_name),
    )
    stats = sim.run(args.trace)
    stats["policy"] = policy_name
    stats["trace"] = str(args.trace)
    stats["zones"] = args.zones
    stats["zone_capacity"] = args.zone_capacity
    return stats


def print_row(row: dict) -> None:
    printable = dict(row)
    printable.setdefault("prediction_accuracy", 0.0)
    printable.setdefault("off_by_gt1", 0.0)
    print(
        "{policy:13s} waf={waf:.3f} gc_blocks={gc_write_blocks:<8d} "
        "util={zone_utilization:.3f} epoch_imp={epoch_impurity:.3f} "
        "intent_imp={intent_impurity:.3f} reset_elg={reset_eligibility:.3f} "
        "stale_sec={stale_secret_blocks_remaining:<6d} pred_acc={prediction_accuracy:.3f}".format(
            **printable,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--zones", type=int, default=256)
    parser.add_argument("--zone-capacity", type=int, default=512)
    parser.add_argument("--min-free-zones", type=int, default=4)
    parser.add_argument("--lba-bucket-size", type=int, default=4096)
    parser.add_argument("--quasar-cert-epochs", type=int, default=12)
    parser.add_argument("--quasar-min-epoch-fill", type=float, default=0.0)
    parser.add_argument("--quasar-bin-width", type=int, default=1)
    parser.add_argument("--quasar-open-zone-budget", type=int, default=0)
    parser.add_argument("--quasar-residual-threshold", type=int, default=-1)
    parser.add_argument("--quasar-residual-fraction", type=float, default=0.0)
    parser.add_argument("--quasar-disable-overflow", action="store_true")
    parser.add_argument("--quasar-disable-secret-priority", action="store_true")
    parser.add_argument("--quasar-adaptive-exact-min-blocks", type=int, default=4)
    parser.add_argument("--quasar-adaptive-tenant-bin-width", type=int, default=16)
    parser.add_argument("--quasar-adaptive-coarse-bin-width", type=int, default=32_000_000)
    parser.add_argument("--quasar-adaptive-coarse-pressure", type=float, default=0.75)
    parser.add_argument("--quasar-adaptive-family-pressure", type=float, default=8.0)
    parser.add_argument("--quasar-adaptive-urgent-lifetime", type=int, default=32)
    parser.add_argument("--hint-missing-rate", type=float, default=0.0)
    parser.add_argument("--wrong-epoch-rate", type=float, default=0.0)
    parser.add_argument("--straggler-rate", type=float, default=0.0)
    parser.add_argument("--base-write-ns", type=int, default=10_000)
    parser.add_argument("--gc-copy-ns", type=int, default=15_000)
    parser.add_argument("--dogi-ml-ns-per-batch", type=int, default=600_000)
    parser.add_argument("--dogi-batch-size", type=int, default=128)
    parser.add_argument("--quasar-hint-ns", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--policies",
        nargs="+",
        default=[
            "fifo",
            "sepbit-style",
            "midas-style",
            "dogi-history",
            "quasar",
            "quasar-dogi-hybrid",
            "quasar-adaptive-hybrid",
            "epoch-oracle",
        ],
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    rows = [run_policy(args, policy_name) for policy_name in args.policies]
    for row in rows:
        print_row(row)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as out:
            json.dump(rows, out, indent=2, sort_keys=True)
            out.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
