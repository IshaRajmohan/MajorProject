"""
OWNER: Person B
Direct implementation of Section V / Algorithm 1 from the paper.
NO DB or HTTP imports here — keep this pure so Person D can call it
standalone from the evaluation harness.
"""
from app.cams.models import Candidate, CAMSWeights, SyncResult


def score(c: Candidate, w: CAMSWeights) -> float:
    return w.w_A * c.A + w.w_T * c.T + w.w_X * c.X + w.w_E * c.E


def synchronize(
    candidates: list[Candidate],
    w: CAMSWeights,
    tau: float,
    delta: float,
) -> SyncResult:
    w.validate()
    if not candidates:
        return SyncResult("retained", None, 0.0, None, {}, "no candidates")

    scored = sorted(
        ((c, score(c, w)) for c in candidates),
        key=lambda t: t[1],
        reverse=True,
    )
    top, c1 = scored[0]
    c2 = scored[1][1] if len(scored) > 1 else None
    scores = {c.observation_id: s for c, s in scored}

    if len(scored) == 1:
        if c1 >= tau:
            return SyncResult("updated", top, c1, c2, scores, "single candidate meets tau")
        return SyncResult("unresolved", None, c1, c2, scores, "single candidate below tau")

    if c1 >= tau and (c1 - c2) >= delta:
        return SyncResult("updated", top, c1, c2, scores, "meets tau and delta margin")

    return SyncResult(
        "retained", None, c1, c2, scores,
        "insufficient confidence or margin — marked unresolved",
    )
