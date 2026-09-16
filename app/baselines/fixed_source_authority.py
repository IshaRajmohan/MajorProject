"""
OWNER: Person D
Selects the candidate from the highest-ranked source in a FIXED global
hierarchy (unlike CAMS's fact-specific authority). Define the hierarchy here.
"""
from app.cams.models import Candidate, SyncResult

FIXED_HIERARCHY = ["court", "forensic", "police", "lawyer", "citizen"]

def synchronize(candidates: list[Candidate], source_role_by_id: dict[str, str]) -> SyncResult:
    if not candidates:
        return SyncResult("retained", None, 0.0, None, {}, "no candidates")
    def rank(c: Candidate) -> int:
        role = source_role_by_id[c.observation_id]
        return FIXED_HIERARCHY.index(role) if role in FIXED_HIERARCHY else len(FIXED_HIERARCHY)
    winner = min(candidates, key=rank)
    return SyncResult("updated", winner, 1.0, None, {}, "fixed source authority ranking")
