"""
OWNER: Person B
Framework-agnostic dataclasses — no SQLAlchemy/FastAPI imports allowed in this file
or in engine.py / factors.py. This module is imported directly by:
  - Person C's ObservationService (app/services/)
  - Person D's evaluation harness (app/eval/) and baselines (app/baselines/)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _clamp_unit(name: str, value: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{name} must be a number in [0, 1]")
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value}")
    return float(value)


@dataclass
class Candidate:
    observation_id: str
    value: Any
    A: float  # source authority           [0,1]
    T: float  # temporal consistency       [0,1]
    X: float  # cross-source corroboration [0,1]
    E: float  # extraction reliability     [0,1]

    def __post_init__(self) -> None:
        self.A = _clamp_unit("A", self.A)
        self.T = _clamp_unit("T", self.T)
        self.X = _clamp_unit("X", self.X)
        self.E = _clamp_unit("E", self.E)


@dataclass
class CAMSWeights:
    w_A: float
    w_T: float
    w_X: float
    w_E: float

    def validate(self) -> None:
        for name, w in (
            ("w_A", self.w_A),
            ("w_T", self.w_T),
            ("w_X", self.w_X),
            ("w_E", self.w_E),
        ):
            if not isinstance(w, (int, float)) or isinstance(w, bool):
                raise TypeError(f"{name} must be a number in [0, 1]")
            if w < 0.0 or w > 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {w}")
        total = self.w_A + self.w_T + self.w_X + self.w_E
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"weights must sum to 1, got {total}")


@dataclass
class SyncResult:
    decision: str  # "updated" | "retained" | "unresolved"
    winner: Candidate | None
    c1: float
    c2: float | None
    scores: dict[str, float] = field(default_factory=dict)
    explanation: str = ""
