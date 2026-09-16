"""
OWNER: Person B
Framework-agnostic dataclasses — no SQLAlchemy/FastAPI imports allowed in this file
or in engine.py / factors.py. This module is imported directly by:
  - Person C's ObservationService (app/services/)
  - Person D's evaluation harness (app/eval/) and baselines (app/baselines/)
"""
from dataclasses import dataclass, field

@dataclass
class Candidate:
    observation_id: str
    value: dict
    A: float  # source authority        [0,1]
    T: float  # temporal consistency    [0,1]
    X: float  # cross-source corroboration [0,1]
    E: float  # extraction reliability  [0,1]

@dataclass
class CAMSWeights:
    w_A: float
    w_T: float
    w_X: float
    w_E: float

    def validate(self) -> None:
        total = self.w_A + self.w_T + self.w_X + self.w_E
        assert abs(total - 1.0) < 1e-6, f"weights must sum to 1, got {total}"
        for w in (self.w_A, self.w_T, self.w_X, self.w_E):
            assert 0 <= w <= 1, "each weight must be in [0,1]"

@dataclass
class SyncResult:
    decision: str                 # "updated" | "retained" | "unresolved"
    winner: Candidate | None
    c1: float
    c2: float | None
    scores: dict = field(default_factory=dict)   # observation_id -> C(f_i)
    explanation: str = ""
