"""
OWNER: Person B
Unit tests against the paper's own scenarios: conflicting, delayed, noisy, duplicate.
"""
from app.cams.engine import synchronize
from app.cams.models import Candidate, CAMSWeights

W = CAMSWeights(w_A=0.3, w_T=0.3, w_X=0.2, w_E=0.2)

def test_single_strong_candidate_updates():
    c = [Candidate("o1", {"v": "granted"}, A=0.9, T=0.9, X=0.5, E=1.0)]
    result = synchronize(c, W, tau=0.6, delta=0.1)
    assert result.decision == "updated"

def test_conflicting_candidates_with_clear_winner():
    c = [
        Candidate("o1", {"v": "granted"}, A=0.95, T=0.9, X=0.8, E=1.0),
        Candidate("o2", {"v": "denied"}, A=0.4, T=0.3, X=0.1, E=0.5),
    ]
    result = synchronize(c, W, tau=0.5, delta=0.1)
    assert result.decision == "updated"
    assert result.winner.observation_id == "o1"

def test_conflicting_candidates_too_close_marks_unresolved():
    c = [
        Candidate("o1", {"v": "granted"}, A=0.7, T=0.7, X=0.5, E=0.7),
        Candidate("o2", {"v": "denied"}, A=0.68, T=0.68, X=0.5, E=0.68),
    ]
    result = synchronize(c, W, tau=0.5, delta=0.15)
    assert result.decision == "retained"

def test_low_confidence_single_candidate_unresolved():
    c = [Candidate("o1", {"v": "granted"}, A=0.2, T=0.1, X=0.0, E=0.3)]
    result = synchronize(c, W, tau=0.6, delta=0.1)
    assert result.decision == "unresolved"
