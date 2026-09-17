"""
OWNER: Person D
Runs CAMS (full model), 4 ablations (one confidence component zeroed and the
remaining weights renormalized, per Section V-D of the paper), and 3 baselines
over the 5 scenarios in scenario_generator.py, and reports per-scenario and
aggregate accuracy from metrics.py.

Standalone: only imports app.cams.* and app.baselines.* (no DB, no HTTP).
Run with:  python -m app.eval.runner
"""
from __future__ import annotations

from app.baselines import fixed_source_authority, latest_update_wins, majority_voting
from app.cams.engine import synchronize as cams_synchronize
from app.cams.models import CAMSWeights, Candidate
from app.eval import scenario_generator
from app.eval.metrics import twin_state_accuracy

DEFAULT_WEIGHTS = CAMSWeights(w_A=0.3, w_T=0.3, w_X=0.2, w_E=0.2)

# Each ablation zeroes one component's weight and renormalizes the rest so
# they still sum to 1 (Eq. 13-14 in the paper).
ABLATIONS: dict[str, CAMSWeights] = {
    "cams_minus_A": CAMSWeights(w_A=0.0, w_T=0.428571, w_X=0.285714, w_E=0.285714),
    "cams_minus_T": CAMSWeights(w_A=0.428571, w_T=0.0, w_X=0.285714, w_E=0.285714),
    "cams_minus_X": CAMSWeights(w_A=0.375, w_T=0.375, w_X=0.0, w_E=0.25),
    "cams_minus_E": CAMSWeights(w_A=0.375, w_T=0.375, w_X=0.25, w_E=0.0),
}

BASELINES = ("fixed_authority", "latest_wins", "majority_voting")
METHODS = ["cams_full", *ABLATIONS.keys(), *BASELINES]


def _cams_predict(candidates: list[Candidate], weights: CAMSWeights, tau: float, delta: float):
    result = cams_synchronize(candidates, weights, tau, delta)
    predicted = None if result.winner is None else result.winner.value["v"]
    return predicted, result.decision


def _baseline_predict(name: str, candidates: list[Candidate], meta: dict):
    if name == "fixed_authority":
        result = fixed_source_authority.synchronize(candidates, meta["source_role_by_id"])
    elif name == "latest_wins":
        result = latest_update_wins.synchronize(candidates, meta["order_by_id"])
    elif name == "majority_voting":
        values_by_id = {c.observation_id: c.value["v"] for c in candidates}
        result = majority_voting.synchronize(candidates, values_by_id)
    else:
        raise ValueError(f"unknown baseline: {name}")
    predicted = None if result.winner is None else result.winner.value["v"]
    return predicted, result.decision


def run_all(tau: float = 0.6, delta: float = 0.1) -> list[dict]:
    """Returns one row per (scenario, method): predicted, reference, decision, correct."""
    rows: list[dict] = []
    for scenario_name, generator in scenario_generator.SCENARIOS.items():
        candidates, reference, meta = generator()
        for method in METHODS:
            if method == "cams_full":
                predicted, decision = _cams_predict(candidates, DEFAULT_WEIGHTS, tau, delta)
            elif method in ABLATIONS:
                predicted, decision = _cams_predict(candidates, ABLATIONS[method], tau, delta)
            else:
                predicted, decision = _baseline_predict(method, candidates, meta)
            rows.append(
                {
                    "scenario": scenario_name,
                    "method": method,
                    "predicted": predicted,
                    "reference": reference,
                    "decision": decision,
                    "correct": predicted == reference,
                }
            )
    return rows


def summarize(rows: list[dict]) -> dict[str, float]:
    by_method: dict[str, list[dict]] = {}
    for row in rows:
        by_method.setdefault(row["method"], []).append(row)
    return {method: twin_state_accuracy(entries) for method, entries in by_method.items()}


def print_report(rows: list[dict]) -> None:
    header = f"{'scenario':<14}{'method':<16}{'predicted':<14}{'reference':<12}{'decision':<12}{'correct'}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['scenario']:<14}{row['method']:<16}"
            f"{str(row['predicted']):<14}{str(row['reference']):<12}"
            f"{row['decision']:<12}{row['correct']}"
        )
    print()
    print("Accuracy by method (predicted value == reference value):")
    for method, acc in summarize(rows).items():
        print(f"  {method:<16} {acc:.2%}")


if __name__ == "__main__":
    print_report(run_all())
