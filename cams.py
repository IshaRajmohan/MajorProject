"""
CAMS — Confidence-Aware Multi-Source Synchronization.

score() / decide() / synchronize(), with optional single-factor ablation.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from config import (
    DELTA,
    TAU,
    WEIGHTS,
    ablate_weights,
    lookup_authority,
)
from models import CandidateScore, DecisionResult, FactorBreakdown, Observation


def _norm_value(v: Any) -> str:
    """Canonical string key for grouping candidate values."""
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


def temporal_consistency(
    event_time: datetime,
    timeline: Sequence[datetime],
) -> float:
    """
    Score how well event_time fits the case timeline.

    Distance from the median event time (MAD scale) so a single out-of-order
    outlier is penalized without collapsing T for chronological inliers.
    Empty timeline -> 1.0.
    """
    if not timeline:
        return 1.0

    def _aware(dt: datetime, ref: datetime) -> datetime:
        if dt.tzinfo is None and ref.tzinfo is not None:
            return dt.replace(tzinfo=ref.tzinfo)
        if dt.tzinfo is not None and ref.tzinfo is None:
            return dt.replace(tzinfo=None)
        return dt

    times = list(timeline)
    ref0 = times[0]
    times = [_aware(t, ref0) for t in times]
    et = _aware(event_time, ref0)

    times_sorted = sorted(times)
    median = times_sorted[len(times_sorted) // 2]
    abs_devs = [abs((t - median).total_seconds()) for t in times_sorted]
    mad = sorted(abs_devs)[len(abs_devs) // 2]
    scale = mad if mad > 0 else 86400.0

    gap = abs((et - median).total_seconds())
    score = 1.0 / (1.0 + gap / scale)
    return max(0.0, min(1.0, score))


def cross_source_corroboration(
    observations: Sequence[Observation],
    candidate_value: Any,
) -> float:
    """
    Fraction of distinct source_ids (among all obs for this fact) that agree
    on the same candidate value.
    """
    all_sources = {o.source_id for o in observations}
    if not all_sources:
        return 0.0
    agree = {
        o.source_id
        for o in observations
        if _norm_value(o.value) == _norm_value(candidate_value)
    }
    return len(agree) / len(all_sources)


def score_observation(
    obs: Observation,
    all_for_fact: Sequence[Observation],
    timeline: Sequence[datetime],
    weights: Optional[Dict[str, float]] = None,
) -> FactorBreakdown:
    """Compute four factors and weighted confidence for one observation."""
    w = weights or WEIGHTS
    A = lookup_authority(obs.fact_key, obs.source_type)
    ref_timeline = list(timeline) if timeline else [o.event_time for o in all_for_fact]
    T = temporal_consistency(obs.event_time, ref_timeline)
    X = cross_source_corroboration(all_for_fact, obs.value)
    E = float(obs.extraction_reliability)
    C = w["wA"] * A + w["wT"] * T + w["wX"] * X + w["wE"] * E
    return FactorBreakdown(
        source_authority=A,
        temporal_consistency=T,
        cross_source_corroboration=X,
        extraction_reliability=E,
        confidence=C,
    )


def aggregate_candidates(
    observations: Sequence[Observation],
    timeline: Sequence[datetime],
    weights: Optional[Dict[str, float]] = None,
) -> List[CandidateScore]:
    """
    Group observations by value; for each group take the max confidence
    among member observations (factors from that best obs), plus support lists.
    """
    if not observations:
        return []

    by_value: Dict[str, List[Observation]] = defaultdict(list)
    for o in observations:
        by_value[_norm_value(o.value)].append(o)

    candidates: List[CandidateScore] = []
    for _key, group in by_value.items():
        best_breakdown: Optional[FactorBreakdown] = None
        best_obs: Optional[Observation] = None
        for o in group:
            # Timeline for temporal score excludes only this obs's time if desired;
            # use full case timeline passed in.
            fb = score_observation(o, observations, timeline, weights)
            if best_breakdown is None or fb.confidence > best_breakdown.confidence:
                best_breakdown = fb
                best_obs = o
        assert best_breakdown is not None and best_obs is not None
        candidates.append(
            CandidateScore(
                value=best_obs.value,
                confidence=best_breakdown.confidence,
                factors=best_breakdown,
                supporting_observation_ids=[o.observation_id for o in group],
                supporting_source_ids=sorted({o.source_id for o in group}),
            )
        )

    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates


def decide(
    candidates: List[CandidateScore],
    tau: float = TAU,
    delta: float = DELTA,
    previous_value: Any = None,
) -> Tuple[bool, Optional[Any], Optional[float], Optional[float], str]:
    """
    Decision rule: update if C1 >= tau and (C2 is None or C1 - C2 >= delta).
    Returns (decided, accepted_value, C1, C2, message).
    """
    if not candidates:
        return False, None, None, None, "no candidates"

    C1 = candidates[0].confidence
    C2 = candidates[1].confidence if len(candidates) > 1 else None
    top_value = candidates[0].value

    if C1 < tau:
        return (
            False,
            previous_value,
            C1,
            C2,
            f"abstain: C1={C1:.3f} < tau={tau}",
        )

    if C2 is not None and (C1 - C2) < delta:
        return (
            False,
            previous_value,
            C1,
            C2,
            f"abstain: margin={C1 - C2:.3f} < delta={delta}",
        )

    return True, top_value, C1, C2, f"accept value with C1={C1:.3f}"


def synchronize(
    case_id: str,
    fact_key: str,
    observations: Sequence[Observation],
    timeline: Sequence[datetime],
    previous_value: Any = None,
    tau: float = TAU,
    delta: float = DELTA,
    weights: Optional[Dict[str, float]] = None,
    ablation: Optional[str] = None,
) -> DecisionResult:
    """
    Full CAMS pass for one fact_key.

    ablation: if set to 'A'|'T'|'X'|'E', zero that factor and renormalize weights.
    """
    w = dict(weights or WEIGHTS)
    if ablation:
        w = ablate_weights(ablation, w)

    candidates = aggregate_candidates(observations, timeline, w)
    decided, accepted, C1, C2, message = decide(candidates, tau, delta, previous_value)
    margin = (C1 - C2) if (C1 is not None and C2 is not None) else None

    return DecisionResult(
        case_id=case_id,
        fact_key=fact_key,
        decided=decided,
        accepted_value=accepted if decided else previous_value,
        previous_value=previous_value,
        unresolved=not decided,
        C1=C1,
        C2=C2,
        margin=margin,
        tau=tau,
        delta=delta,
        candidates=candidates,
        message=message,
    )


def cams_decide_value(
    observations: Sequence[Observation],
    tau: float = TAU,
    delta: float = DELTA,
    weights: Optional[Dict[str, float]] = None,
    ablation: Optional[str] = None,
    previous_value: Any = None,
) -> Tuple[Optional[Any], Optional[float], DecisionResult]:
    """
    Standalone CAMS for evaluation (no store).

    Returns (decided_value_or_None_if_abstain, confidence_or_None, full DecisionResult).
    Abstain returns None as the value even if previous_value existed.
    """
    if not observations:
        empty = DecisionResult(
            case_id="",
            fact_key="",
            decided=False,
            accepted_value=None,
            previous_value=previous_value,
            unresolved=True,
            C1=None,
            C2=None,
            margin=None,
            tau=tau,
            delta=delta,
            candidates=[],
            message="no observations",
        )
        return None, None, empty

    fact_key = observations[0].fact_key
    case_id = observations[0].case_id
    timeline = [o.event_time for o in observations]
    result = synchronize(
        case_id=case_id,
        fact_key=fact_key,
        observations=observations,
        timeline=timeline,
        previous_value=previous_value,
        tau=tau,
        delta=delta,
        weights=weights,
        ablation=ablation,
    )
    if result.decided:
        return result.accepted_value, result.C1, result
    return None, result.C1, result
