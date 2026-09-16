"""
OWNER: Person B
Computes A, T, X, E for a raw observation dict before it becomes a Candidate.
Kept separate from engine.py so factor heuristics can be swapped/mocked in
tests independently of the scoring math.

NOTE: takes plain dicts/lists in, not ORM objects, so this stays DB-agnostic.
Person C's service layer is responsible for querying the DB and passing
plain data structures in here.
"""

def authority_score(source_role: str, fact_type: str, rules: dict[tuple[str, str], float]) -> float:
    """rules: {(fact_type, source_role): score}, default 0.5 if no match."""
    return rules.get((fact_type, source_role), 0.5)


def temporal_consistency_score(event_time, known_chronology_anchor) -> float:
    """
    v1 heuristic (documented limitation, see paper Section VIII):
    1.0 if event_time is at/after the case's last known anchor for this entity,
    decaying toward 0 the further out of order it is.
    TODO(Person B): refine if time allows.
    """
    if event_time is None or known_chronology_anchor is None:
        return 0.5
    if event_time >= known_chronology_anchor:
        return 1.0
    delta_days = (known_chronology_anchor - event_time).days
    return max(0.0, 1.0 - delta_days / 30.0)


def corroboration_score(independent_source_count: int, cap: int = 3) -> float:
    return min(1.0, independent_source_count / cap)


def extraction_reliability_score(raw_value: float | None) -> float:
    """Pass-through; defaults to 1.0 for manually entered/structured input."""
    return 1.0 if raw_value is None else max(0.0, min(1.0, raw_value))
