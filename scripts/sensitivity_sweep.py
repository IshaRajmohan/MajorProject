"""
Threshold (tau) and margin (delta) sensitivity sweep for CAMS synchronization.

Uses the same pure app.cams.engine.synchronize() and the controlled scenarios
in app.eval.scenario_generator — no DB, no HTTP. Run with:

    python scripts/sensitivity_sweep.py

Reports, for each scenario, the range of tau (with delta fixed at 0.1) and
the range of delta (with tau fixed at 0.6) over which the decision changes.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.cams.engine import synchronize
from app.cams.models import CAMSWeights
from app.eval import scenario_generator

WEIGHTS = CAMSWeights(w_A=0.3, w_T=0.3, w_X=0.2, w_E=0.2)
TAUS = [round(0.30 + 0.05 * i, 2) for i in range(13)]  # 0.30 .. 0.90
DELTAS = [round(0.00 + 0.02 * i, 2) for i in range(16)]  # 0.00 .. 0.30


def sweep_tau(candidates, delta=0.1):
    rows = []
    for tau in TAUS:
        result = synchronize(candidates, WEIGHTS, tau, delta)
        rows.append((tau, result.decision, round(result.c1, 4)))
    return rows


def sweep_delta(candidates, tau=0.6):
    rows = []
    for delta in DELTAS:
        result = synchronize(candidates, WEIGHTS, tau, delta)
        rows.append((delta, result.decision, None if result.c2 is None else round(result.c1 - result.c2, 4)))
    return rows


def main() -> None:
    for name, generator in scenario_generator.SCENARIOS.items():
        candidates, reference, _meta = generator()
        print(f"=== scenario: {name} (reference={reference}) ===")

        print("-- tau sweep (delta=0.1) --")
        prev_decision = None
        for tau, decision, c1 in sweep_tau(candidates):
            marker = " <-- boundary" if decision != prev_decision else ""
            print(f"  tau={tau:.2f}  decision={decision:<10} c1={c1}{marker}")
            prev_decision = decision

        print("-- delta sweep (tau=0.6) --")
        prev_decision = None
        for delta, decision, margin in sweep_delta(candidates):
            marker = " <-- boundary" if decision != prev_decision else ""
            print(f"  delta={delta:.2f}  decision={decision:<10} margin(c1-c2)={margin}{marker}")
            prev_decision = decision
        print()


if __name__ == "__main__":
    main()
