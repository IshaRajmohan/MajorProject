"""Baseline synchronizers for comparison against CAMS."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional, Sequence

from config import SOURCE_TYPE_PRIORITY
from models import Observation


def _norm(v: Any) -> str:
    return str(v)


def latest_update_wins(observations: Sequence[Observation]) -> Optional[Any]:
    """Pick the value of the observation with the latest ingestion_time."""
    if not observations:
        return None
    best = max(observations, key=lambda o: o.ingestion_time)
    return best.value


def majority_voting(observations: Sequence[Observation]) -> Optional[Any]:
    """
    Pick the value with the most distinct source_ids supporting it.
    Ties -> None (abstain).
    """
    if not observations:
        return None
    by_value: dict[str, set[str]] = defaultdict(set)
    value_map: dict[str, Any] = {}
    for o in observations:
        k = _norm(o.value)
        by_value[k].add(o.source_id)
        value_map[k] = o.value

    ranked = sorted(by_value.items(), key=lambda kv: len(kv[1]), reverse=True)
    if not ranked:
        return None
    if len(ranked) > 1 and len(ranked[0][1]) == len(ranked[1][1]):
        return None  # tie -> abstain
    return value_map[ranked[0][0]]


def fixed_source_authority(observations: Sequence[Observation]) -> Optional[Any]:
    """
    Pick value from the observation whose source_type has the highest priority
    in the fixed global ranking (court > forensic > police > lawyer > ...).
    Ties among same priority: latest ingestion_time wins.
    """
    if not observations:
        return None

    def priority(o: Observation) -> tuple:
        return (
            SOURCE_TYPE_PRIORITY.get(o.source_type, -1),
            o.ingestion_time,
        )

    best = max(observations, key=priority)
    return best.value
