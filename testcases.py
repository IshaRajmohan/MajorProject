"""Synthetic test-case generator for CAMS evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Sequence
import random

from models import Observation

CATEGORIES = ("conflicting", "delayed", "duplicate", "noisy", "corroboration")

FACT_KEYS = [
    "arrest_date",
    "charge",
    "victim_injury",
    "weapon_type",
    "incident_location",
    "bail_status",
]

# Plausible value pools per fact_key
VALUE_POOLS = {
    "arrest_date": ["2023-01-15", "2023-01-16", "2023-01-20", "2023-02-01", "2023-03-10"],
    "charge": ["IPC 302", "IPC 307", "IPC 376", "IPC 420", "IPC 506"],
    "victim_injury": ["fracture", "laceration", "contusion", "fatal", "none"],
    "weapon_type": ["knife", "firearm", "blunt", "poison", "none"],
    "incident_location": ["Delhi", "Mumbai", "Chennai", "Kolkata", "Bengaluru"],
    "bail_status": ["granted", "denied", "pending", "cancelled"],
}

SOURCE_TYPES = ["court", "forensic", "police", "lawyer", "media", "witness"]


@dataclass
class TestCase:
    case_id: str
    fact_key: str
    observations: List[Observation]
    ground_truth_value: Optional[Any]  # None means correct behavior is abstain
    category: str
    meta: dict = field(default_factory=dict)


def _dt(base: datetime, days: float = 0, hours: float = 0) -> datetime:
    return base + timedelta(days=days, hours=hours)


def _obs(
    case_id: str,
    fact_key: str,
    value: Any,
    source_id: str,
    source_type: str,
    event_time: datetime,
    ingestion_time: datetime,
    reliability: float,
) -> Observation:
    return Observation(
        case_id=case_id,
        fact_key=fact_key,
        value=value,
        source_id=source_id,
        source_type=source_type,
        event_time=event_time,
        ingestion_time=ingestion_time,
        extraction_reliability=max(0.0, min(1.0, reliability)),
    )


def _pick_values(rng: random.Random, fact_key: str, n: int = 2) -> List[str]:
    pool = list(VALUE_POOLS[fact_key])
    rng.shuffle(pool)
    return pool[:n]


def _make_conflicting(rng: random.Random, idx: int, base: datetime) -> TestCase:
    """Two+ authoritative sources disagree; often ground truth = higher-authority or abstain."""
    fact_key = FACT_KEYS[idx % len(FACT_KEYS)]
    vals = _pick_values(rng, fact_key, 2)
    true_v, false_v = vals[0], vals[1]
    case_id = f"conflict-{idx:03d}"

    # Court / forensic assert truth; media / lawyer assert false — close reliability
    pattern = idx % 4
    if pattern == 0:
        # Clear court vs media — GT = court value (should resolve)
        obs = [
            _obs(case_id, fact_key, true_v, "court-1", "court", _dt(base, 0), _dt(base, 1), 0.95),
            _obs(case_id, fact_key, false_v, "media-1", "media", _dt(base, 0.5), _dt(base, 1.2), 0.70),
        ]
        gt = true_v
    elif pattern == 1:
        # Police vs lawyer, similar authority on some facts — often abstain
        obs = [
            _obs(case_id, fact_key, true_v, "police-1", "police", _dt(base, 0), _dt(base, 1), 0.80),
            _obs(case_id, fact_key, false_v, "lawyer-1", "lawyer", _dt(base, 0.2), _dt(base, 1.1), 0.80),
        ]
        # For charge/bail court would dominate; here similar — abstain is correct
        gt = None if fact_key not in ("arrest_date", "incident_location") else true_v
        if fact_key in ("arrest_date", "incident_location"):
            gt = true_v  # police higher than lawyer on these
        else:
            gt = None
    elif pattern == 2:
        # Forensic + court agree on truth; witness disagrees
        obs = [
            _obs(case_id, fact_key, true_v, "forensic-1", "forensic", _dt(base, 0), _dt(base, 2), 0.92),
            _obs(case_id, fact_key, true_v, "court-1", "court", _dt(base, 1), _dt(base, 3), 0.95),
            _obs(case_id, fact_key, false_v, "wit-1", "witness", _dt(base, 0.5), _dt(base, 1), 0.75),
        ]
        gt = true_v
    else:
        # Two equal-ish media sources conflict — abstain
        obs = [
            _obs(case_id, fact_key, true_v, "media-a", "media", _dt(base, 0), _dt(base, 1), 0.65),
            _obs(case_id, fact_key, false_v, "media-b", "media", _dt(base, 0.1), _dt(base, 1.05), 0.65),
        ]
        gt = None

    return TestCase(case_id, fact_key, obs, gt, "conflicting")


def _make_delayed(rng: random.Random, idx: int, base: datetime) -> TestCase:
    """Out-of-order / delayed ingestion; GT is the chronologically correct event value."""
    fact_key = FACT_KEYS[idx % len(FACT_KEYS)]
    vals = _pick_values(rng, fact_key, 2)
    early_v, late_v = vals[0], vals[1]
    case_id = f"delayed-{idx:03d}"

    # Early event is truth; late-arriving correction from court is also truth variant
    # Scenario: police reports early_v (correct time), then delayed court confirms early_v
    # OR: early wrong media, delayed court with correct late_v that has later event_time
    pattern = idx % 3
    if pattern == 0:
        # Delayed court correction: event_time later, ingested late — GT = court value
        obs = [
            _obs(case_id, fact_key, early_v, "media-1", "media", _dt(base, 0), _dt(base, 0.5), 0.60),
            _obs(case_id, fact_key, late_v, "court-1", "court", _dt(base, 5), _dt(base, 20), 0.95),
        ]
        gt = late_v
    elif pattern == 1:
        # Out-of-order: court arrives first (late event), then police early event arrives late
        # Chronology: early event is true incident; court later updates — GT = court for legal facts
        obs = [
            _obs(case_id, fact_key, late_v, "court-1", "court", _dt(base, 10), _dt(base, 11), 0.95),
            _obs(case_id, fact_key, early_v, "police-1", "police", _dt(base, 0), _dt(base, 15), 0.85),
        ]
        # Court still more authoritative for most legal facts
        gt = late_v if fact_key in ("charge", "bail_status", "arrest_date") else late_v
    else:
        # Far out-of-order noisy event_time from witness — should not override court
        obs = [
            _obs(case_id, fact_key, early_v, "court-1", "court", _dt(base, 2), _dt(base, 3), 0.95),
            _obs(case_id, fact_key, late_v, "wit-1", "witness", _dt(base, -30), _dt(base, 4), 0.50),
        ]
        gt = early_v

    return TestCase(case_id, fact_key, obs, gt, "delayed")


def _make_duplicate(rng: random.Random, idx: int, base: datetime) -> TestCase:
    """Same source repeats; should not inflate corroboration. GT = that value."""
    fact_key = FACT_KEYS[idx % len(FACT_KEYS)]
    vals = _pick_values(rng, fact_key, 2)
    true_v, other_v = vals[0], vals[1]
    case_id = f"dup-{idx:03d}"

    pattern = idx % 3
    if pattern == 0:
        # Same police source duplicates true_v three times; one media other
        obs = [
            _obs(case_id, fact_key, true_v, "police-1", "police", _dt(base, 0), _dt(base, 1), 0.85),
            _obs(case_id, fact_key, true_v, "police-1", "police", _dt(base, 0), _dt(base, 1.5), 0.85),
            _obs(case_id, fact_key, true_v, "police-1", "police", _dt(base, 0), _dt(base, 2), 0.85),
            _obs(case_id, fact_key, other_v, "media-1", "media", _dt(base, 0.5), _dt(base, 2.5), 0.55),
        ]
        gt = true_v
    elif pattern == 1:
        # Duplicate court filings — GT clear
        obs = [
            _obs(case_id, fact_key, true_v, "court-1", "court", _dt(base, 1), _dt(base, 2), 0.95),
            _obs(case_id, fact_key, true_v, "court-1", "court", _dt(base, 1), _dt(base, 3), 0.95),
        ]
        gt = true_v
    else:
        # Duplicate low-authority shouldn't beat single court
        obs = [
            _obs(case_id, fact_key, other_v, "media-1", "media", _dt(base, 0), _dt(base, 1), 0.60),
            _obs(case_id, fact_key, other_v, "media-1", "media", _dt(base, 0), _dt(base, 1.2), 0.60),
            _obs(case_id, fact_key, other_v, "media-1", "media", _dt(base, 0), _dt(base, 1.4), 0.60),
            _obs(case_id, fact_key, true_v, "court-1", "court", _dt(base, 1), _dt(base, 2), 0.95),
        ]
        gt = true_v

    return TestCase(case_id, fact_key, obs, gt, "duplicate")


def _make_noisy(rng: random.Random, idx: int, base: datetime) -> TestCase:
    """Low extraction_reliability noise; should be ignored / abstain if sole signal."""
    fact_key = FACT_KEYS[idx % len(FACT_KEYS)]
    vals = _pick_values(rng, fact_key, 2)
    true_v, noise_v = vals[0], vals[1]
    case_id = f"noisy-{idx:03d}"

    pattern = idx % 3
    if pattern == 0:
        # Reliable court + noisy contradicting extraction
        obs = [
            _obs(case_id, fact_key, true_v, "court-1", "court", _dt(base, 0), _dt(base, 1), 0.95),
            _obs(case_id, fact_key, noise_v, "media-nlp", "media", _dt(base, 0.5), _dt(base, 1.2), 0.15),
        ]
        gt = true_v
    elif pattern == 1:
        # Only noisy observations of conflicting values — abstain
        obs = [
            _obs(case_id, fact_key, true_v, "media-a", "media", _dt(base, 0), _dt(base, 1), 0.20),
            _obs(case_id, fact_key, noise_v, "media-b", "media", _dt(base, 0.2), _dt(base, 1.1), 0.18),
        ]
        gt = None
    else:
        # Forensic reliable + lawyer noisy wrong
        obs = [
            _obs(case_id, fact_key, true_v, "forensic-1", "forensic", _dt(base, 1), _dt(base, 2), 0.93),
            _obs(case_id, fact_key, noise_v, "lawyer-ocr", "lawyer", _dt(base, 1.5), _dt(base, 2.5), 0.10),
        ]
        gt = true_v

    return TestCase(case_id, fact_key, obs, gt, "noisy")


def _make_corroboration(rng: random.Random, idx: int, base: datetime) -> TestCase:
    """Three distinct sources agree — should accept with high confidence."""
    fact_key = FACT_KEYS[idx % len(FACT_KEYS)]
    vals = _pick_values(rng, fact_key, 2)
    true_v, other_v = vals[0], vals[1]
    case_id = f"corr-{idx:03d}"

    pattern = idx % 3
    if pattern == 0:
        obs = [
            _obs(case_id, fact_key, true_v, "police-1", "police", _dt(base, 0), _dt(base, 1), 0.85),
            _obs(case_id, fact_key, true_v, "forensic-1", "forensic", _dt(base, 1), _dt(base, 2), 0.90),
            _obs(case_id, fact_key, true_v, "court-1", "court", _dt(base, 2), _dt(base, 3), 0.95),
        ]
        gt = true_v
    elif pattern == 1:
        # 3 agree, 1 disagrees weakly
        obs = [
            _obs(case_id, fact_key, true_v, "police-1", "police", _dt(base, 0), _dt(base, 1), 0.80),
            _obs(case_id, fact_key, true_v, "lawyer-1", "lawyer", _dt(base, 0.5), _dt(base, 1.5), 0.75),
            _obs(case_id, fact_key, true_v, "wit-1", "witness", _dt(base, 0.2), _dt(base, 1.2), 0.70),
            _obs(case_id, fact_key, other_v, "media-1", "media", _dt(base, 1), _dt(base, 2), 0.50),
        ]
        gt = true_v
    else:
        # Triple media corroboration of same value
        obs = [
            _obs(case_id, fact_key, true_v, "media-a", "media", _dt(base, 0), _dt(base, 1), 0.70),
            _obs(case_id, fact_key, true_v, "media-b", "media", _dt(base, 0.1), _dt(base, 1.1), 0.68),
            _obs(case_id, fact_key, true_v, "media-c", "media", _dt(base, 0.2), _dt(base, 1.2), 0.72),
        ]
        gt = true_v

    return TestCase(case_id, fact_key, obs, gt, "corroboration")


_BUILDERS = {
    "conflicting": _make_conflicting,
    "delayed": _make_delayed,
    "duplicate": _make_duplicate,
    "noisy": _make_noisy,
    "corroboration": _make_corroboration,
}


def generate_test_cases(seed: int, per_category: int = 25) -> List[TestCase]:
    """
    Build synthetic test cases across 5 categories (~per_category each).

    Use different seeds for independent validation vs test sets.
    """
    rng = random.Random(seed)
    base = datetime(2023, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    cases: List[TestCase] = []
    for cat in CATEGORIES:
        builder = _BUILDERS[cat]
        for i in range(per_category):
            # Offset base per case for timeline diversity
            case_base = base + timedelta(days=rng.randint(0, 200), hours=rng.randint(0, 23))
            cases.append(builder(rng, i, case_base))
    return cases


def split_labels(cases: Sequence[TestCase]) -> List[str]:
    return [c.category for c in cases]
