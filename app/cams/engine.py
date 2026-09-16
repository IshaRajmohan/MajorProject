"""
OWNER: Person B
Direct implementation of Section V / Algorithm 1 from the paper.
NO DB or HTTP imports here — keep this pure so Person D can call it
standalone from the evaluation harness.
"""
from __future__ import annotations

from app.cams.models import CAMSWeights, Candidate, SyncResult


def score(candidate: Candidate, weights: CAMSWeights) -> float:
    """C = w_A*A + w_T*T + w_X*X + w_E*E"""
    return (
        weights.w_A * candidate.A
        + weights.w_T * candidate.T
        + weights.w_X * candidate.X
        + weights.w_E * candidate.E
    )


def synchronize(
    candidates: list[Candidate],
    weights: CAMSWeights,
    tau: float,
    delta: float,
) -> SyncResult:
    """
    CAMS synchronization (v1).

    Decision rules:
    - no candidates → retained
    - one candidate, C >= tau → updated
    - one candidate, C < tau → unresolved
    - many candidates, c1 >= tau and (c1 - c2) >= delta → updated
    - otherwise → retained (keep prior twin state; margin/confidence insufficient)
    """
    weights.validate()
    if not 0.0 <= tau <= 1.0:
        raise ValueError("tau must be in [0, 1]")
    if not 0.0 <= delta <= 1.0:
        raise ValueError("delta must be in [0, 1]")

    if not candidates:
        return SyncResult(
            decision="retained",
            winner=None,
            c1=0.0,
            c2=None,
            scores={},
            explanation="no candidates",
        )

    scored = sorted(
        ((c, score(c, weights)) for c in candidates),
        key=lambda t: t[1],
        reverse=True,
    )
    top, c1 = scored[0]
    c2 = scored[1][1] if len(scored) > 1 else None
    scores = {c.observation_id: s for c, s in scored}

    if len(scored) == 1:
        if c1 >= tau:
            return SyncResult(
                decision="updated",
                winner=top,
                c1=c1,
                c2=c2,
                scores=scores,
                explanation="single candidate meets tau",
            )
        return SyncResult(
            decision="unresolved",
            winner=None,
            c1=c1,
            c2=c2,
            scores=scores,
            explanation="single candidate below tau",
        )

    if c1 >= tau and (c1 - c2) >= delta:  # type: ignore[operator]
        return SyncResult(
            decision="updated",
            winner=top,
            c1=c1,
            c2=c2,
            scores=scores,
            explanation="meets tau and delta margin",
        )

    return SyncResult(
        decision="retained",
        winner=None,
        c1=c1,
        c2=c2,
        scores=scores,
        explanation="insufficient confidence or margin — prior state retained",
    )
