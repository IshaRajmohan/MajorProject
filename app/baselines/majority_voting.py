"""
OWNER: Person D
Picks the candidate value supported by the most observations.
Per the paper: duplicate observations from the same underlying source should
be treated consistently (i.e. don't let one source's repeats inflate its vote
beyond what the test protocol defines — document your counting rule here).
"""
from collections import Counter
from app.cams.models import Candidate, SyncResult

def synchronize(candidates: list[Candidate], values_by_id: dict[str, str]) -> SyncResult:
    if not candidates:
        return SyncResult("retained", None, 0.0, None, {}, "no candidates")
    counts = Counter(values_by_id[c.observation_id] for c in candidates)
    winning_value, n = counts.most_common(1)[0]
    winner = next(c for c in candidates if values_by_id[c.observation_id] == winning_value)
    return SyncResult("updated", winner, n / len(candidates), None, {}, f"majority vote ({n}/{len(candidates)})")
