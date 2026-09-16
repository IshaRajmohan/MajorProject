"""
OWNER: Person D
Generates controlled test cases for the 5 scenarios in Section VI:
conflicting, delayed, noisy, corroboration, duplicate.
Each generated case = (list[Candidate], reference_answer, scenario_type).
"""
from app.cams.models import Candidate

def conflicting_scenario() -> tuple[list[Candidate], str]:
    candidates = [
        Candidate("o1", {"v": "bail_granted"}, A=0.9, T=0.8, X=0.7, E=1.0),
        Candidate("o2", {"v": "bail_denied"}, A=0.3, T=0.4, X=0.2, E=0.6),
    ]
    return candidates, "bail_granted"

def delayed_update_scenario() -> tuple[list[Candidate], str]:
    # TODO(Person D): candidate with later ingestion but earlier event_time
    # should not override — express via low T for the "late" one.
    raise NotImplementedError

def noisy_information_scenario() -> tuple[list[Candidate], str]:
    raise NotImplementedError

def corroboration_scenario() -> tuple[list[Candidate], str]:
    raise NotImplementedError

def duplicate_information_scenario() -> tuple[list[Candidate], str]:
    raise NotImplementedError
