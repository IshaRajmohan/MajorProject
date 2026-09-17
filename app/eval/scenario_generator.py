"""
OWNER: Person D
Generates controlled test cases for the 5 scenarios in Section VI:
conflicting, delayed, noisy, corroboration, duplicate.

Each generated case = (list[Candidate], reference_answer, meta), where meta
carries the side information (source role, ingestion order) that the
baselines in app/baselines/ need but the Candidate dataclass itself does not
store. Candidate.value is always a dict with a "v" key so predictions can be
compared uniformly across CAMS, its ablations, and the three baselines.

"order" in meta is an integer ingestion sequence (0 = first ingested), used
by latest_update_wins as a stand-in for wall-clock ingestion time.
"""
from app.cams.models import Candidate


def conflicting_scenario() -> tuple[list[Candidate], str, dict]:
    candidates = [
        Candidate("o1", {"v": "bail_granted"}, A=0.9, T=0.8, X=0.7, E=1.0),
        Candidate("o2", {"v": "bail_denied"}, A=0.3, T=0.4, X=0.2, E=0.6),
    ]
    meta = {
        "source_role_by_id": {"o1": "court", "o2": "police"},
        "order_by_id": {"o1": 0, "o2": 1},
    }
    return candidates, "bail_granted", meta


def delayed_update_scenario() -> tuple[list[Candidate], str, dict]:
    """
    'fresh' is ingested first and is temporally consistent with the case
    chronology (T=1.0). 'delayed' is ingested second (later ingestion time)
    but describes an event 25 days out of order, so its temporal-consistency
    factor is low (T=0.2, matching the ~30-day linear decay in factors.py).
    A baseline that trusts the latest ingestion would wrongly prefer
    'delayed'; CAMS should not, because T penalizes the chronological
    contradiction regardless of when the record arrived.
    """
    candidates = [
        Candidate("fresh", {"v": "in_custody"}, A=0.8, T=1.0, X=0.3, E=1.0),
        Candidate("delayed", {"v": "released"}, A=0.8, T=0.2, X=0.3, E=1.0),
    ]
    meta = {
        "source_role_by_id": {"fresh": "police", "delayed": "police"},
        "order_by_id": {"fresh": 0, "delayed": 1},
    }
    return candidates, "in_custody", meta


def noisy_information_scenario() -> tuple[list[Candidate], str, dict]:
    """'clean' has structured/high extraction reliability; 'noisy' shares the
    same A/T/X but was extracted with low reliability (e.g. degraded OCR)."""
    candidates = [
        Candidate("clean", {"v": "A"}, A=0.7, T=0.7, X=0.4, E=1.0),
        Candidate("noisy", {"v": "B"}, A=0.7, T=0.7, X=0.4, E=0.2),
    ]
    meta = {
        "source_role_by_id": {"clean": "forensic", "noisy": "forensic"},
        "order_by_id": {"clean": 0, "noisy": 1},
    }
    return candidates, "A", meta


def corroboration_scenario() -> tuple[list[Candidate], str, dict]:
    """'weak' has no independent corroboration (X=0); 'strong' shares the
    same A/T/E but is independently corroborated by other source groups
    (X=1.0). CAMS should prefer the corroborated candidate even though its
    single-source authority (A) is identical."""
    candidates = [
        Candidate("weak", {"v": "denied"}, A=0.6, T=0.6, X=0.0, E=1.0),
        Candidate("strong", {"v": "granted"}, A=0.6, T=0.6, X=1.0, E=1.0),
    ]
    meta = {
        "source_role_by_id": {"weak": "police", "strong": "court"},
        "order_by_id": {"weak": 0, "strong": 1},
    }
    return candidates, "granted", meta


def duplicate_information_scenario() -> tuple[list[Candidate], str, dict]:
    """Two observations carrying the identical value from the same source
    group. Because their scores are equal, CAMS's margin condition is not
    met and the engine returns 'retained' (no forced pick) rather than
    'updated'. This is by design, not a value error: there is no competing
    value to resolve. Baselines without a margin concept will trivially
    report the (unambiguous) shared value. The 'reference' below is the
    single value both duplicates carry, used only to check that no method
    invents a different value."""
    candidates = [
        Candidate("d1", {"v": "same"}, A=0.8, T=0.8, X=0.5, E=1.0),
        Candidate("d2", {"v": "same"}, A=0.8, T=0.8, X=0.5, E=1.0),
    ]
    meta = {
        "source_role_by_id": {"d1": "court", "d2": "court"},
        "order_by_id": {"d1": 0, "d2": 1},
    }
    return candidates, "same", meta


SCENARIOS = {
    "conflicting": conflicting_scenario,
    "delayed": delayed_update_scenario,
    "noisy": noisy_information_scenario,
    "corroboration": corroboration_scenario,
    "duplicate": duplicate_information_scenario,
}
