"""Synthetic CASE-001 documents demonstrating all five scenario families."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

CASE_001_ID = "CASE-001"
CASE_001_TITLE = "State vs. Fictional Accused — Mumbai Incident"
CASE_001_DESCRIPTION = (
    "Synthetic research demo covering conflict, delayed/out-of-order data, "
    "duplicate sources, noisy extraction, and multi-source corroboration. "
    "Not a real case. CAMS confidence is not legal truth."
)


def case_001_documents() -> List[Dict[str, Any]]:
    """Ordered document payloads for POST /cases/{id}/documents."""
    base = datetime(2024, 4, 10, 9, 0, tzinfo=timezone.utc)
    return [
        # Corroboration + baseline facts (police)
        {
            "scenario": "corroboration",
            "title": "FIR extract — Police Station 12",
            "source_id": "police-ps12",
            "source_type": "police",
            "event_time": base.isoformat().replace("+00:00", "Z"),
            "extraction_reliability": 0.85,
            "text": (
                "First Information Report.\n"
                "Location: Mumbai\n"
                "Arrested on 10 April 2024\n"
                "Charge: IPC 302\n"
                "Weapon: knife\n"
                "Injury: fracture\n"
            ),
        },
        # Forensic corroborates injury + weapon
        {
            "scenario": "corroboration",
            "title": "Forensic examination memo",
            "source_id": "forensic-lab-7",
            "source_type": "forensic",
            "event_time": datetime(2024, 4, 11, 14, 0, tzinfo=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "extraction_reliability": 0.93,
            "text": (
                "Forensic report.\n"
                "Weapon: knife\n"
                "Injury: fracture\n"
                "Location: Mumbai\n"
            ),
        },
        # Court corroborates charge + location
        {
            "scenario": "corroboration",
            "title": "Magistrate charge sheet note",
            "source_id": "court-mm-2",
            "source_type": "court",
            "event_time": datetime(2024, 4, 12, 11, 0, tzinfo=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "extraction_reliability": 0.95,
            "text": (
                "Court note.\n"
                "Charge: IPC 302\n"
                "Location: Mumbai\n"
                "Bail: denied\n"
            ),
        },
        # Conflict — media asserts different charge
        {
            "scenario": "conflict",
            "title": "News brief (conflicting charge)",
            "source_id": "media-toi",
            "source_type": "media",
            "event_time": datetime(2024, 4, 10, 18, 0, tzinfo=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "extraction_reliability": 0.55,
            "text": "Evening bulletin.\nCharge: IPC 304\nLocation: Mumbai\n",
        },
        # Delayed / out-of-order — witness claims earlier arrest
        {
            "scenario": "delayed",
            "title": "Delayed witness statement (OOO)",
            "source_id": "wit-anon-3",
            "source_type": "witness",
            "event_time": datetime(2024, 3, 1, 8, 0, tzinfo=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "extraction_reliability": 0.50,
            "text": (
                "Statement recorded late.\n"
                "Arrested on 01 March 2024\n"
                "Location: Mumbai\n"
            ),
        },
        # Duplicate — same police source repeats weapon
        {
            "scenario": "duplicate",
            "title": "Police follow-up (duplicate source)",
            "source_id": "police-ps12",
            "source_type": "police",
            "event_time": datetime(2024, 4, 10, 9, 30, tzinfo=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "extraction_reliability": 0.85,
            "text": "Supplementary note.\nWeapon: knife\nLocation: Mumbai\n",
        },
        # Noisy — low-reliability OCR noise on injury
        {
            "scenario": "noisy",
            "title": "Scraped blog OCR (noisy)",
            "source_id": "scraper-blog",
            "source_type": "media",
            "event_time": datetime(2024, 4, 11, 20, 0, tzinfo=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "extraction_reliability": 0.12,
            "text": "Auto-OCR dump.\nInjury: none\nWeapon: firearm\n",
        },
    ]


def scenario_document(name: str) -> Dict[str, Any]:
    """Return a single document dict for a named scenario button."""
    name = name.lower().strip()
    mapping = {
        "conflict": "conflict",
        "conflicting": "conflict",
        "delayed": "delayed",
        "duplicate": "duplicate",
        "noisy": "noisy",
        "noise": "noisy",
        "corroboration": "corroboration",
    }
    key = mapping.get(name)
    if key is None:
        raise KeyError(f"unknown scenario: {name}")
    docs = [d for d in case_001_documents() if d["scenario"] == key]
    if key == "corroboration":
        # return first corroborating doc for incremental demo
        return docs[0]
    return docs[0]
