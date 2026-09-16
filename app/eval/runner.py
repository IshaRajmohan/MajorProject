"""
OWNER: Person D
Runs CAMS + all 3 baselines + 4 ablation variants (zero out one weight each)
over the same generated scenarios, and reports metrics from metrics.py.
This can run fully standalone against app.cams.engine — no DB required.
"""
from app.cams.engine import synchronize as cams_synchronize
from app.cams.models import CAMSWeights
from app.eval import scenario_generator

DEFAULT_WEIGHTS = CAMSWeights(w_A=0.3, w_T=0.3, w_X=0.2, w_E=0.2)
ABLATIONS = {
    "no_authority": CAMSWeights(w_A=0.0, w_T=0.4, w_X=0.3, w_E=0.3),
    "no_temporal": CAMSWeights(w_A=0.4, w_T=0.0, w_X=0.3, w_E=0.3),
    "no_corroboration": CAMSWeights(w_A=0.4, w_T=0.3, w_X=0.0, w_E=0.3),
    "no_extraction": CAMSWeights(w_A=0.4, w_T=0.3, w_X=0.3, w_E=0.0),
}

def run_all(tau: float = 0.6, delta: float = 0.1):
    candidates, reference = scenario_generator.conflicting_scenario()
    result = cams_synchronize(candidates, DEFAULT_WEIGHTS, tau, delta)
    predicted = result.winner.value["v"] if result.winner else None
    print(f"CAMS full: predicted={predicted} reference={reference} decision={result.decision}")
    # TODO(Person D): loop over all scenarios x [CAMS, ablations, baselines], collect metrics

if __name__ == "__main__":
    run_all()
