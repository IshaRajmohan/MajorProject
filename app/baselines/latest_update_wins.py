"""
OWNER: Person D
Same input/output shape as app.cams.engine.synchronize so it's a drop-in swap
in the evaluation harness. Ignores confidence entirely: picks whichever
candidate has the latest ingestion_time (passed in via candidate.value["_ingested_at"]
or a parallel list — decide the convention with whoever wires up the harness input).
"""
from app.cams.models import Candidate, SyncResult

def synchronize(candidates: list[Candidate], ingestion_times: dict[str, "datetime"]) -> SyncResult:
    if not candidates:
        return SyncResult("retained", None, 0.0, None, {}, "no candidates")
    winner = max(candidates, key=lambda c: ingestion_times[c.observation_id])
    return SyncResult("updated", winner, 1.0, None, {}, "latest ingestion time wins")
