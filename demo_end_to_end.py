#!/usr/bin/env python3
"""
End-to-end demo: Document → Extraction → Observation → CAMS → Digital Twin.

Runs against a live server (starts one if needed) and loads CASE-001.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from demo_data import CASE_001_DESCRIPTION, CASE_001_ID, CASE_001_TITLE, case_001_documents

BASE = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parent


def _wait(timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE}/api/health", timeout=0.5)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            try:
                r = requests.get(f"{BASE}/docs", timeout=0.5)
                if r.status_code == 200:
                    return True
            except requests.RequestException:
                pass
            time.sleep(0.3)
    return False


def ensure_server() -> Optional[subprocess.Popen]:
    if _wait(1.0):
        print("Server already running.\n")
        return None
    print("Starting uvicorn on :8000 ...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not _wait():
        proc.terminate()
        raise RuntimeError("Failed to start server")
    print("Server ready.\n")
    return proc


def _banner(msg: str) -> None:
    print("=" * 72)
    print(msg)
    print("=" * 72)


def run_demo() -> Dict[str, Any]:
    # Reset / create case
    requests.post(f"{BASE}/api/reset", timeout=10)
    r = requests.post(
        f"{BASE}/cases",
        json={
            "case_id": CASE_001_ID,
            "title": CASE_001_TITLE,
            "description": CASE_001_DESCRIPTION,
        },
        timeout=10,
    )
    r.raise_for_status()
    _banner(f"Created {CASE_001_ID}")
    print(r.json())

    pipeline_log = []
    for i, doc in enumerate(case_001_documents(), 1):
        scenario = doc.get("scenario", "?")
        _banner(f"[{i}/{len(case_001_documents())}] Document ({scenario}): {doc['title']}")
        print("--- INPUT DOCUMENT ---")
        print(doc["text"])
        payload = {k: v for k, v in doc.items() if k != "scenario"}
        resp = requests.post(
            f"{BASE}/cases/{CASE_001_ID}/documents",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        pipeline_log.append(data)

        print("\n--- EXTRACTION ---")
        for f in data.get("extracted_facts", []):
            print(f"  {f['fact_key']} = {f['value']!r}  (span={f.get('evidence_span')!r})")

        print("\n--- OBSERVATIONS CREATED ---")
        for o in data.get("observations", []):
            print(
                f"  {o['fact_key']}={o['value']!r} src={o['source_id']}/{o['source_type']} "
                f"E={o['extraction_reliability']}"
            )

        print("\n--- CAMS DECISIONS ---")
        for d in data.get("decisions", []):
            print(
                f"  {d['fact_key']}: decided={d['decided']} value={d.get('accepted_value')!r} "
                f"C1={d.get('C1')} C2={d.get('C2')} margin={d.get('margin')} | {d['message']}"
            )
            for c in d.get("candidates", [])[:3]:
                fac = c["factors"]
                print(
                    f"    cand={c['value']!r} C={c['confidence']:.3f} "
                    f"A={fac['source_authority']:.2f} T={fac['temporal_consistency']:.2f} "
                    f"X={fac['cross_source_corroboration']:.2f} E={fac['extraction_reliability']:.2f}"
                )

        twin = data.get("twin", {})
        print("\n--- DIGITAL TWIN (current) ---")
        for k, v in twin.get("facts", {}).items():
            print(f"  {k}: {v.get('value')!r} resolved={v.get('resolved')} conf={v.get('confidence')}")
        print(f"  unresolved: {twin.get('unresolved')}")
        print()

    # Role views
    _banner("Role-based views")
    for role in ("court", "police", "lawyer", "forensic", "citizen"):
        view = requests.get(f"{BASE}/cases/{CASE_001_ID}", params={"role": role}, timeout=10).json()
        print(f"  [{role}] facts={list(view.get('facts', {}).keys())} "
              f"obs={len(view.get('observations', []))} unresolved={view.get('unresolved')}")

    hist = requests.get(f"{BASE}/cases/{CASE_001_ID}/history", timeout=10).json()
    unresolved = requests.get(f"{BASE}/cases/{CASE_001_ID}/unresolved", timeout=10).json()
    _banner("Provenance / History / Unresolved")
    print(f"History entries: {len(hist.get('history', hist if isinstance(hist, list) else []))}")
    print(f"Unresolved: {unresolved}")
    print("\nDemo complete: Document → Extraction → Observation → CAMS → Twin → Provenance → Roles")
    return {"case_id": CASE_001_ID, "steps": len(pipeline_log)}


def main() -> None:
    proc = ensure_server()
    try:
        run_demo()
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()


if __name__ == "__main__":
    main()
