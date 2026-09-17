"""CAMS configuration: weights, thresholds, and source-authority table."""

from __future__ import annotations

from typing import Dict, Tuple

# Decision thresholds
TAU: float = 0.55
DELTA: float = 0.10

# Factor weights (must sum to 1.0)
WEIGHTS: Dict[str, float] = {
    "wA": 0.30,  # source authority
    "wT": 0.30,  # temporal consistency
    "wX": 0.20,  # cross-source corroboration
    "wE": 0.20,  # extraction reliability
}

# Fixed global ranking for baseline fixed_source_authority (higher = more trusted)
SOURCE_TYPE_PRIORITY: Dict[str, int] = {
    "court": 4,
    "forensic": 3,
    "police": 2,
    "lawyer": 1,
    "media": 0,
    "witness": 0,
}

# source_authority[fact_key][source_type] -> float in [0, 1]
# Default 0.5 when missing.
SOURCE_AUTHORITY: Dict[str, Dict[str, float]] = {
    "arrest_date": {
        "court": 0.95,
        "police": 0.85,
        "lawyer": 0.55,
        "media": 0.35,
        "witness": 0.40,
        "forensic": 0.50,
    },
    "charge": {
        "court": 0.98,
        "police": 0.70,
        "lawyer": 0.65,
        "media": 0.30,
        "witness": 0.25,
        "forensic": 0.40,
    },
    "victim_injury": {
        "court": 0.90,
        "forensic": 0.95,
        "police": 0.70,
        "lawyer": 0.50,
        "media": 0.25,
        "witness": 0.55,
    },
    "weapon_type": {
        "court": 0.85,
        "forensic": 0.95,
        "police": 0.75,
        "lawyer": 0.45,
        "media": 0.30,
        "witness": 0.50,
    },
    "incident_location": {
        "court": 0.90,
        "police": 0.85,
        "lawyer": 0.50,
        "media": 0.40,
        "witness": 0.60,
        "forensic": 0.55,
    },
    "bail_status": {
        "court": 0.98,
        "police": 0.60,
        "lawyer": 0.70,
        "media": 0.35,
        "witness": 0.20,
        "forensic": 0.30,
    },
}


def lookup_authority(fact_key: str, source_type: str) -> float:
    """Return source_authority for (fact_key, source_type), default 0.5."""
    by_fact = SOURCE_AUTHORITY.get(fact_key, {})
    return float(by_fact.get(source_type, 0.5))


def weights_tuple(weights: Dict[str, float] | None = None) -> Tuple[float, float, float, float]:
    w = weights or WEIGHTS
    return w["wA"], w["wT"], w["wX"], w["wE"]


def ablate_weights(zero_factor: str, base: Dict[str, float] | None = None) -> Dict[str, float]:
    """
    Zero out one factor weight and renormalize the rest so they sum to 1.

    zero_factor: one of 'A', 'T', 'X', 'E' (or 'wA', 'wT', ...).
    """
    key_map = {"A": "wA", "T": "wT", "X": "wX", "E": "wE"}
    z = zero_factor if zero_factor.startswith("w") else key_map[zero_factor.upper()]
    w = dict(base or WEIGHTS)
    w[z] = 0.0
    total = sum(w.values())
    if total <= 0:
        # Fallback equal split among remaining (should not happen with valid base)
        remaining = [k for k in w if k != z]
        for k in remaining:
            w[k] = 1.0 / len(remaining)
        return w
    for k in w:
        w[k] = w[k] / total
    return w


# Role-based view permissions (demo only — not real auth).
# visible_facts: None means all facts; list means allow-list.
# show_provenance / show_confidence / show_unresolved / show_raw_observations
ROLE_PERMISSIONS: Dict[str, Dict] = {
    "court": {
        "visible_facts": None,
        "show_provenance": True,
        "show_confidence": True,
        "show_unresolved": True,
        "show_raw_observations": True,
        "show_history": True,
    },
    "police": {
        "visible_facts": [
            "arrest_date",
            "charge",
            "weapon_type",
            "incident_location",
            "victim_injury",
            "bail_status",
        ],
        "show_provenance": True,
        "show_confidence": True,
        "show_unresolved": True,
        "show_raw_observations": True,
        "show_history": True,
    },
    "lawyer": {
        "visible_facts": [
            "charge",
            "arrest_date",
            "bail_status",
            "incident_location",
            "weapon_type",
            "victim_injury",
        ],
        "show_provenance": True,
        "show_confidence": True,
        "show_unresolved": True,
        "show_raw_observations": False,
        "show_history": True,
    },
    "forensic": {
        "visible_facts": ["victim_injury", "weapon_type", "incident_location"],
        "show_provenance": True,
        "show_confidence": True,
        "show_unresolved": True,
        "show_raw_observations": True,
        "show_history": False,
    },
    "citizen": {
        "visible_facts": ["charge", "bail_status", "incident_location"],
        "show_provenance": False,
        "show_confidence": False,
        "show_unresolved": False,
        "show_raw_observations": False,
        "show_history": False,
    },
}
