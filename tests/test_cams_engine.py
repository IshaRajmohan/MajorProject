"""
OWNER: Person B
Unit tests against paper scenarios: conflicting, delayed, noisy, duplicate,
corroborated, and low-confidence observations.
"""
from datetime import datetime, timedelta

import pytest

from app.cams.engine import score, synchronize
from app.cams.factors import FactorCalculator
from app.cams.models import CAMSWeights, Candidate

W = CAMSWeights(w_A=0.3, w_T=0.3, w_X=0.2, w_E=0.2)


def test_score_formula():
    c = Candidate("o1", {"v": 1}, A=1.0, T=0.0, X=0.0, E=0.0)
    assert abs(score(c, W) - 0.3) < 1e-9


def test_empty_candidates_retained():
    result = synchronize([], W, tau=0.6, delta=0.1)
    assert result.decision == "retained"
    assert result.winner is None
    assert result.c1 == 0.0
    assert result.c2 is None
    assert result.scores == {}


def test_single_strong_candidate_updates():
    c = [Candidate("o1", {"v": "granted"}, A=0.9, T=0.9, X=0.5, E=1.0)]
    result = synchronize(c, W, tau=0.6, delta=0.1)
    assert result.decision == "updated"
    assert result.winner is not None
    assert result.winner.observation_id == "o1"
    assert result.c2 is None


def test_low_confidence_single_candidate_unresolved():
    c = [Candidate("o1", {"v": "granted"}, A=0.2, T=0.1, X=0.0, E=0.3)]
    result = synchronize(c, W, tau=0.6, delta=0.1)
    assert result.decision == "unresolved"
    assert result.winner is None


def test_conflicting_candidates_with_clear_winner():
    c = [
        Candidate("o1", {"v": "granted"}, A=0.95, T=0.9, X=0.8, E=1.0),
        Candidate("o2", {"v": "denied"}, A=0.4, T=0.3, X=0.1, E=0.5),
    ]
    result = synchronize(c, W, tau=0.5, delta=0.1)
    assert result.decision == "updated"
    assert result.winner.observation_id == "o1"
    assert result.c1 > result.c2


def test_conflicting_candidates_too_close_marks_retained():
    c = [
        Candidate("o1", {"v": "granted"}, A=0.7, T=0.7, X=0.5, E=0.7),
        Candidate("o2", {"v": "denied"}, A=0.68, T=0.68, X=0.5, E=0.68),
    ]
    result = synchronize(c, W, tau=0.5, delta=0.15)
    assert result.decision == "retained"
    assert result.winner is None


def test_delayed_observation_loses_on_temporal():
    """Older/out-of-order observation should lose when T is low."""
    fresh = Candidate("fresh", {"status": "in_custody"}, A=0.8, T=1.0, X=0.3, E=1.0)
    delayed = Candidate("delayed", {"status": "released"}, A=0.8, T=0.2, X=0.3, E=1.0)
    result = synchronize([fresh, delayed], W, tau=0.5, delta=0.05)
    assert result.decision == "updated"
    assert result.winner.observation_id == "fresh"


def test_noisy_low_extraction_reliability():
    clean = Candidate("clean", {"v": "A"}, A=0.7, T=0.7, X=0.4, E=1.0)
    noisy = Candidate("noisy", {"v": "B"}, A=0.7, T=0.7, X=0.4, E=0.2)
    result = synchronize([clean, noisy], W, tau=0.5, delta=0.05)
    assert result.decision == "updated"
    assert result.winner.observation_id == "clean"


def test_duplicate_observations_same_value():
    """Duplicates with equal strength → insufficient margin → retained."""
    c = [
        Candidate("d1", {"v": "same"}, A=0.8, T=0.8, X=0.5, E=1.0),
        Candidate("d2", {"v": "same"}, A=0.8, T=0.8, X=0.5, E=1.0),
    ]
    result = synchronize(c, W, tau=0.5, delta=0.1)
    assert result.decision == "retained"
    assert abs(result.c1 - result.c2) < 1e-9


def test_corroborated_observation_wins():
    weak = Candidate("weak", {"v": "denied"}, A=0.6, T=0.6, X=0.0, E=1.0)
    strong = Candidate("strong", {"v": "granted"}, A=0.6, T=0.6, X=1.0, E=1.0)
    result = synchronize([weak, strong], W, tau=0.5, delta=0.05)
    assert result.decision == "updated"
    assert result.winner.observation_id == "strong"


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        CAMSWeights(w_A=0.5, w_T=0.5, w_X=0.5, w_E=0.5).validate()


def test_factor_out_of_range_rejected():
    with pytest.raises(ValueError):
        Candidate("bad", 1, A=1.5, T=0.5, X=0.5, E=0.5)


def test_factor_calculator_authority_and_build():
    calc = FactorCalculator()
    assert calc.compute_A("court", "bail_status") == 0.95
    assert calc.compute_A("citizen", "unknown_fact") == 0.5

    anchor = datetime(2026, 1, 10)
    on_time = calc.compute_T(datetime(2026, 1, 12), anchor)
    late = calc.compute_T(datetime(2025, 12, 1), anchor)
    assert on_time == 1.0
    assert late < on_time

    assert calc.compute_X(0) == 0.0
    assert calc.compute_X(3) == 1.0
    assert calc.compute_E(None) == 1.0
    assert calc.compute_E(0.4) == 0.4

    candidate = calc.build_candidate(
        observation_id="obs-1",
        value={"bail": "granted"},
        source_role="court",
        fact_type="bail_status",
        event_time=datetime(2026, 1, 12),
        known_chronology_anchor=anchor,
        independent_source_count=2,
        extraction_reliability=0.9,
    )
    assert candidate.A == 0.95
    assert candidate.T == 1.0
    assert abs(candidate.X - 2 / 3) < 1e-9
    assert candidate.E == 0.9

    result = synchronize([candidate], W, tau=0.6, delta=0.1)
    assert result.decision == "updated"


def test_factor_calculator_delayed_vs_fresh_sync():
    calc = FactorCalculator()
    anchor = datetime(2026, 3, 1)
    fresh = calc.build_candidate(
        observation_id="fresh",
        value={"status": "in_custody"},
        source_role="police",
        fact_type="custody_status",
        event_time=anchor,
        known_chronology_anchor=anchor,
        independent_source_count=1,
        extraction_reliability=1.0,
    )
    delayed = calc.build_candidate(
        observation_id="delayed",
        value={"status": "released"},
        source_role="police",
        fact_type="custody_status",
        event_time=anchor - timedelta(days=25),
        known_chronology_anchor=anchor,
        independent_source_count=1,
        extraction_reliability=1.0,
    )
    result = synchronize([fresh, delayed], W, tau=0.4, delta=0.05)
    assert result.decision == "updated"
    assert result.winner.observation_id == "fresh"
