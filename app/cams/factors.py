"""
OWNER: Person B
Computes A, T, X, E for a raw observation before it becomes a Candidate.

v1 heuristics only — documented limitations, not scientifically validated.
Kept separate from engine.py so factor heuristics can be swapped/mocked in
tests independently of the scoring math.

NOTE: takes plain dicts/lists in, not ORM objects, so this stays DB-agnostic.
Person C's service layer is responsible for querying the DB and passing
plain data structures in here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.cams.models import Candidate


def authority_score(
    source_role: str,
    fact_type: str,
    rules: dict[tuple[str, str], float],
) -> float:
    """rules: {(fact_type, source_role): score}, default 0.5 if no match."""
    return rules.get((fact_type, source_role), 0.5)


def temporal_consistency_score(
    event_time: datetime | None,
    known_chronology_anchor: datetime | None,
) -> float:
    """
    v1 heuristic (documented limitation):
    1.0 if event_time is at/after the case's last known anchor for this entity,
    decaying toward 0 the further out of order it is (linear over ~30 days).
    Missing times → neutral 0.5.
    """
    if event_time is None or known_chronology_anchor is None:
        return 0.5
    if event_time >= known_chronology_anchor:
        return 1.0
    delta_days = (known_chronology_anchor - event_time).total_seconds() / 86400.0
    return max(0.0, 1.0 - delta_days / 30.0)


def corroboration_score(independent_source_count: int, cap: int = 3) -> float:
    """v1: linear ramp of independent agreeing sources, capped at `cap`."""
    if independent_source_count < 0:
        return 0.0
    return min(1.0, independent_source_count / cap)


def extraction_reliability_score(raw_value: float | None) -> float:
    """Pass-through; defaults to 1.0 for manually entered/structured input."""
    if raw_value is None:
        return 1.0
    return max(0.0, min(1.0, float(raw_value)))


class FactorCalculator:
    """
    Fact-specific A/T/X/E calculator using documented v1 heuristics.

    These scores are engineering priors for CAMS ranking, not validated
    forensic confidence measures.
    """

    DEFAULT_AUTHORITY_RULES: dict[tuple[str, str], float] = {
        ("bail_status", "court"): 0.95,
        ("bail_status", "police"): 0.55,
        ("bail_status", "lawyer"): 0.40,
        ("custody_status", "police"): 0.90,
        ("custody_status", "court"): 0.85,
        ("forensic_result", "forensic"): 0.95,
        ("forensic_result", "police"): 0.45,
        ("hearing_date", "court"): 0.95,
        ("hearing_date", "lawyer"): 0.50,
        ("identity", "police"): 0.80,
        ("identity", "court"): 0.85,
        ("identity", "citizen"): 0.35,
    }

    def __init__(self, authority_rules: dict[tuple[str, str], float] | None = None) -> None:
        self.authority_rules = authority_rules or dict(self.DEFAULT_AUTHORITY_RULES)

    def compute_A(self, source_role: str, fact_type: str) -> float:
        """Fact-specific source authority."""
        return authority_score(source_role, fact_type, self.authority_rules)

    def compute_T(
        self,
        event_time: datetime | None,
        known_chronology_anchor: datetime | None,
    ) -> float:
        """Temporal consistency vs known chronology."""
        return temporal_consistency_score(event_time, known_chronology_anchor)

    def compute_X(self, independent_source_count: int, cap: int = 3) -> float:
        """Independent-source corroboration."""
        return corroboration_score(independent_source_count, cap=cap)

    def compute_E(self, extraction_reliability: float | None) -> float:
        """Extraction reliability (OCR/NLP confidence or structured = 1.0)."""
        return extraction_reliability_score(extraction_reliability)

    def build_candidate(
        self,
        *,
        observation_id: str,
        value: Any,
        source_role: str,
        fact_type: str,
        event_time: datetime | None = None,
        known_chronology_anchor: datetime | None = None,
        independent_source_count: int = 0,
        extraction_reliability: float | None = None,
    ) -> Candidate:
        return Candidate(
            observation_id=observation_id,
            value=value,
            A=self.compute_A(source_role, fact_type),
            T=self.compute_T(event_time, known_chronology_anchor),
            X=self.compute_X(independent_source_count),
            E=self.compute_E(extraction_reliability),
        )
