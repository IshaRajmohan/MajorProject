"""
Rule-based fact/event extraction for legal demo documents.

No ML / LLM — pattern matching only. Examples:
  Charge: IPC 302
  Arrested on 10 April 2024
  Weapon: knife
  Injury: fracture
  Location: Mumbai
"""

from __future__ import annotations

import calendar
import re
from datetime import datetime, timezone
from typing import List, Optional

from models import ExtractedFact

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})


def _parse_date(text: str) -> Optional[datetime]:
    """Parse common date forms into timezone-aware UTC midnight."""
    text = text.strip()
    # ISO / numeric: 2024-04-10 or 10/04/2024 or 10-04-2024
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", text)
    if m:
        y, mo, d = map(int, m.groups())
        return datetime(y, mo, d, tzinfo=timezone.utc)
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", text)
    if m:
        d, mo, y = map(int, m.groups())
        return datetime(y, mo, d, tzinfo=timezone.utc)
    # 10 April 2024 / April 10, 2024
    m = re.match(
        r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$",
        text,
    )
    if m:
        d, mon, y = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        if mon in _MONTHS:
            return datetime(y, _MONTHS[mon], d, tzinfo=timezone.utc)
    m = re.match(
        r"^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})$",
        text,
    )
    if m:
        mon, d, y = m.group(1).lower(), int(m.group(2)), int(m.group(3))
        if mon in _MONTHS:
            return datetime(y, _MONTHS[mon], d, tzinfo=timezone.utc)
    return None


# (compiled_pattern, fact_key, value_group, optional event_time from value)
_PATTERNS = [
    (
        re.compile(r"(?i)\bcharge\s*[:\-]\s*(IPC\s*\d+[A-Za-z]?)", re.I),
        "charge",
        1,
        None,
    ),
    (
        re.compile(r"(?i)\b(?:section|u/?s)\s*(IPC\s*\d+[A-Za-z]?)", re.I),
        "charge",
        1,
        None,
    ),
    (
        re.compile(
            r"(?i)\barrested\s+on\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})",
            re.I,
        ),
        "arrest_date",
        1,
        "date",
    ),
    (
        re.compile(r"(?i)\barrest\s*date\s*[:\-]\s*([^\n,;.]+)", re.I),
        "arrest_date",
        1,
        "date",
    ),
    (
        re.compile(r"(?i)\bweapon\s*[:\-]\s*([A-Za-z\- ]+)", re.I),
        "weapon_type",
        1,
        None,
    ),
    (
        re.compile(r"(?i)\b(?:injury|victim\s*injury)\s*[:\-]\s*([A-Za-z\- ]+)", re.I),
        "victim_injury",
        1,
        None,
    ),
    (
        re.compile(r"(?i)\b(?:location|incident\s*location|place)\s*[:\-]\s*([A-Za-z ]+)", re.I),
        "incident_location",
        1,
        None,
    ),
    (
        re.compile(r"(?i)\bbail\s*(?:status)?\s*[:\-]\s*([A-Za-z]+)", re.I),
        "bail_status",
        1,
        None,
    ),
]


def extract_facts(
    text: str,
    default_event_time: Optional[datetime] = None,
    base_reliability: float = 0.8,
) -> List[ExtractedFact]:
    """Extract structured facts from cleaned document text."""
    facts: List[ExtractedFact] = []
    seen = set()

    for pattern, fact_key, group, kind in _PATTERNS:
        for m in pattern.finditer(text):
            raw_val = m.group(group).strip()
            raw_val = re.sub(r"\s+", " ", raw_val).rstrip(".,;")
            event_time = default_event_time
            value: object = raw_val

            if kind == "date":
                parsed = _parse_date(raw_val)
                if parsed is not None:
                    value = parsed.date().isoformat()
                    event_time = parsed
                else:
                    value = raw_val

            if fact_key == "charge":
                value = re.sub(r"\s+", " ", str(value).upper().replace("IPC", "IPC ").strip())
                value = re.sub(r"IPC\s+", "IPC ", str(value))

            key = (fact_key, str(value).lower())
            if key in seen:
                continue
            seen.add(key)

            # Slightly lower reliability if the match is short/ambiguous
            conf = base_reliability
            if len(str(value)) < 3:
                conf = max(0.3, base_reliability - 0.2)

            facts.append(
                ExtractedFact(
                    fact_key=fact_key,
                    value=value,
                    event_time=event_time,
                    confidence=conf,
                    evidence_span=m.group(0).strip()[:200],
                )
            )

    return facts
