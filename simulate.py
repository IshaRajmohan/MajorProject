#!/usr/bin/env python3
"""
Qualitative live demo: five CAMS scenarios via the FastAPI endpoints.

Starts uvicorn if the server is not already up, then runs scenarios in sequence.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests

BASE = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parent


def _wait_for_server(timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE}/", timeout=0.5)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            time.sleep(0.3)
    return False


def ensure_server() -> Optional[subprocess.Popen]:
    if _wait_for_server(timeout=1.0):
        print("Server already running.\n")
        return None
    print("Starting uvicorn on :8000 ...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not _wait_for_server():
        proc.terminate()
        raise RuntimeError("Failed to start server")
    print("Server ready.\n")
    return proc


def post_obs(case_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(f"{BASE}/cases/{case_id}/observations", json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


def get_state(case_id: str) -> Dict[str, Any]:
    r = requests.get(f"{BASE}/cases/{case_id}/state", timeout=10)
    r.raise_for_status()
    return r.json()


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _banner(title: str) -> None:
    print("=" * 72)
    print(title)
    print("=" * 72)


def _print_decision(label: str, decision: Dict[str, Any]) -> None:
    print(f"\n  >> {label}")
    print(f"     decided={decision['decided']}  unresolved={decision['unresolved']}")
    print(f"     message: {decision['message']}")
    print(f"     C1={decision.get('C1')}  C2={decision.get('C2')}  margin={decision.get('margin')}")
    print(f"     accepted_value={decision.get('accepted_value')!r}")
    for i, cand in enumerate(decision.get("candidates", []), 1):
        f = cand["factors"]
        print(
            f"     candidate[{i}] value={cand['value']!r}  C={cand['confidence']:.3f}  "
            f"A={f['source_authority']:.2f} T={f['temporal_consistency']:.2f} "
            f"X={f['cross_source_corroboration']:.2f} E={f['extraction_reliability']:.2f}"
        )


def _print_state(state: Dict[str, Any]) -> None:
    facts = state.get("facts", {})
    if not facts:
        print("  state: (empty)")
        return
    print("  state:")
    for k, v in facts.items():
        print(f"    {k}: value={v.get('value')!r} resolved={v.get('resolved')} conf={v.get('confidence')}")
    print(f"  unresolved: {state.get('unresolved', [])}")


def scenario_1_conflicting() -> None:
    _banner("Scenario 1 — Conflicting sources (court vs media on charge)")
    case_id = "demo-conflict"
    base = datetime(2024, 3, 1, 10, 0, tzinfo=timezone.utc)
    print("BEFORE:")
    _print_state(get_state(case_id))

    d1 = post_obs(
        case_id,
        {
            "fact_key": "charge",
            "value": "IPC 302",
            "source_id": "court-delhi-1",
            "source_type": "court",
            "event_time": _iso(base),
            "extraction_reliability": 0.95,
        },
    )
    _print_decision("ingest court: IPC 302", d1)

    d2 = post_obs(
        case_id,
        {
            "fact_key": "charge",
            "value": "IPC 304",
            "source_id": "news-toi",
            "source_type": "media",
            "event_time": _iso(base + timedelta(hours=2)),
            "extraction_reliability": 0.70,
        },
    )
    _print_decision("ingest media: IPC 304 (conflict)", d2)

    print("\nAFTER:")
    _print_state(get_state(case_id))
    print()


def scenario_2_delayed() -> None:
    _banner("Scenario 2 — Delayed out-of-order event")
    case_id = "demo-delayed"
    base = datetime(2024, 4, 10, 9, 0, tzinfo=timezone.utc)
    print("BEFORE:")
    _print_state(get_state(case_id))

    d1 = post_obs(
        case_id,
        {
            "fact_key": "arrest_date",
            "value": "2024-04-10",
            "source_id": "police-station-12",
            "source_type": "police",
            "event_time": _iso(base),
            "ingestion_time": _iso(base + timedelta(hours=1)),
            "extraction_reliability": 0.85,
        },
    )
    _print_decision("ingest police arrest_date (on time)", d1)

    # Late-arriving observation with earlier event_time (out of order)
    d2 = post_obs(
        case_id,
        {
            "fact_key": "arrest_date",
            "value": "2024-03-01",
            "source_id": "wit-anonymous",
            "source_type": "witness",
            "event_time": _iso(base - timedelta(days=40)),
            "ingestion_time": _iso(base + timedelta(days=5)),
            "extraction_reliability": 0.55,
        },
    )
    _print_decision("ingest witness with far-earlier event_time (delayed/OOO)", d2)

    print("\nAFTER:")
    _print_state(get_state(case_id))
    print()


def scenario_3_duplicate() -> None:
    _banner("Scenario 3 — Duplicate observation from same source")
    case_id = "demo-dup"
    base = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)
    print("BEFORE:")
    _print_state(get_state(case_id))

    payload = {
        "fact_key": "weapon_type",
        "value": "knife",
        "source_id": "police-1",
        "source_type": "police",
        "event_time": _iso(base),
        "extraction_reliability": 0.80,
    }
    d1 = post_obs(case_id, payload)
    _print_decision("first police: knife", d1)

    d2 = post_obs(
        case_id,
        {**payload, "ingestion_time": _iso(base + timedelta(hours=2))},
    )
    _print_decision("duplicate police: knife (same source_id)", d2)

    d3 = post_obs(
        case_id,
        {
            "fact_key": "weapon_type",
            "value": "firearm",
            "source_id": "media-1",
            "source_type": "media",
            "event_time": _iso(base + timedelta(hours=1)),
            "extraction_reliability": 0.60,
        },
    )
    _print_decision("media: firearm (should not win via fake corroboration)", d3)

    print("\nAFTER:")
    _print_state(get_state(case_id))
    print()


def scenario_4_noisy() -> None:
    _banner("Scenario 4 — Low-reliability noisy observation")
    case_id = "demo-noisy"
    base = datetime(2024, 6, 15, 8, 0, tzinfo=timezone.utc)
    print("BEFORE:")
    _print_state(get_state(case_id))

    d1 = post_obs(
        case_id,
        {
            "fact_key": "victim_injury",
            "value": "fracture",
            "source_id": "forensic-lab-1",
            "source_type": "forensic",
            "event_time": _iso(base),
            "extraction_reliability": 0.95,
        },
    )
    _print_decision("forensic: fracture (high reliability)", d1)

    d2 = post_obs(
        case_id,
        {
            "fact_key": "victim_injury",
            "value": "none",
            "source_id": "scraper-blog",
            "source_type": "media",
            "event_time": _iso(base + timedelta(hours=3)),
            "extraction_reliability": 0.12,
        },
    )
    _print_decision("noisy media OCR: none (low reliability)", d2)

    print("\nAFTER:")
    _print_state(get_state(case_id))
    print()


def scenario_5_corroboration() -> None:
    _banner("Scenario 5 — Three-source corroboration")
    case_id = "demo-corr"
    base = datetime(2024, 7, 20, 14, 0, tzinfo=timezone.utc)
    print("BEFORE:")
    _print_state(get_state(case_id))

    for sid, stype, hours, rel in [
        ("police-42", "police", 0, 0.85),
        ("forensic-7", "forensic", 6, 0.90),
        ("court-bench-2", "court", 24, 0.95),
    ]:
        d = post_obs(
            case_id,
            {
                "fact_key": "incident_location",
                "value": "Mumbai",
                "source_id": sid,
                "source_type": stype,
                "event_time": _iso(base + timedelta(hours=hours)),
                "extraction_reliability": rel,
            },
        )
        _print_decision(f"ingest {stype} ({sid}): Mumbai", d)

    print("\nAFTER:")
    _print_state(get_state(case_id))
    print()


def main() -> None:
    proc = ensure_server()
    try:
        scenario_1_conflicting()
        scenario_2_delayed()
        scenario_3_duplicate()
        scenario_4_noisy()
        scenario_5_corroboration()
        print("=" * 72)
        print("Demo complete.")
        print("=" * 72)
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    main()
