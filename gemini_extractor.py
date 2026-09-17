"""
Gemini fact extractor for NyayaOS.

Gemini ONLY extracts structured facts + evidence quotes from user text.
It must NOT resolve conflicts or decide legal truth — that is CAMS.

If GEMINI_API_KEY is missing or the API fails, a clearly labelled
deterministic rule-based fallback is used so the demo still works.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from extractor import extract_facts as rule_extract

# Load .env if present (no hard dependency failure)
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"

KNOWN_FACTS = [
    "charge",
    "arrest_date",
    "weapon_type",
    "victim_injury",
    "incident_location",
    "bail_status",
]

_SYSTEM = """You are a legal-document information extractor for a research prototype.
Extract ONLY facts explicitly stated in the user text. Do NOT invent facts.
Do NOT decide which source is correct. Do NOT resolve conflicts. Do NOT give legal opinions.
Return JSON only (no markdown) with this shape:
{
  "facts": [
    {
      "fact_key": "charge|arrest_date|weapon_type|victim_injury|incident_location|bail_status|or_other_snake_case",
      "value": "normalized short value",
      "event_time": "ISO-8601 datetime or null",
      "evidence": "exact quote copied from the user text",
      "extraction_confidence": 0.0
    }
  ]
}
extraction_confidence is your confidence that the quote supports the value (0-1), NOT legal truth.
Prefer these fact_keys when applicable: charge, arrest_date, weapon_type, victim_injury, incident_location, bail_status.
You may add other snake_case fact_keys if clearly present.
"""


def _parse_json_blob(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group(0))
        raise


def _normalize_fact(raw: Dict[str, Any], source_type: str) -> Optional[Dict[str, Any]]:
    fact_key = str(raw.get("fact_key") or raw.get("key") or "").strip().lower().replace(" ", "_")
    value = raw.get("value")
    if not fact_key or value is None or str(value).strip() == "":
        return None
    evidence = str(raw.get("evidence") or raw.get("quote") or raw.get("evidence_span") or "").strip()
    conf = raw.get("extraction_confidence", raw.get("confidence", 0.7))
    try:
        conf = float(conf)
    except (TypeError, ValueError):
        conf = 0.7
    conf = max(0.0, min(1.0, conf))
    event_time = raw.get("event_time")
    if event_time == "" or event_time == "null":
        event_time = None
    return {
        "fact_key": fact_key,
        "value": value if not isinstance(value, str) else value.strip(),
        "event_time": event_time,
        "evidence": evidence,
        "extraction_confidence": conf,
        "source_type": source_type,
    }


def parse_gemini_response(text: str, source_type: str) -> List[Dict[str, Any]]:
    """Parse Gemini (or similar) JSON text into normalized fact dicts."""
    data = _parse_json_blob(text)
    items = data.get("facts") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        n = _normalize_fact(item, source_type)
        if n:
            out.append(n)
    return out


def fallback_extract(text: str, source_type: str) -> Tuple[List[Dict[str, Any]], str]:
    """
    Deterministic rule-based extractor (clearly labelled fallback).
    Uses the existing extractor.py patterns — no ML.
    """
    facts = rule_extract(text, default_event_time=datetime.now(timezone.utc), base_reliability=0.75)
    out = []
    for f in facts:
        out.append(
            {
                "fact_key": f.fact_key,
                "value": f.value,
                "event_time": f.event_time.isoformat() if f.event_time else None,
                "evidence": f.evidence_span,
                "extraction_confidence": float(f.confidence),
                "source_type": source_type,
            }
        )
    note = (
        "FALLBACK: rule-based extractor used "
        "(Gemini unavailable or failed). Extraction only — not legal truth."
    )
    return out, note


def _call_gemini(text: str, source_type: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            f"{_SYSTEM}\n\n"
                            f"Source type supplied by user (metadata only): {source_type}\n\n"
                            f"Document text:\n{text}"
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }
    with httpx.Client(timeout=45.0) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        body = r.json()
    candidates = body.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {body}")
    parts = candidates[0].get("content", {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts)


def extract_from_text(
    text: str,
    source_type: str = "unknown",
    force_fallback: bool = False,
) -> Dict[str, Any]:
    """
    Extract structured facts from plain text.

    Returns:
      {
        "facts": [...],
        "extractor": "gemini" | "fallback",
        "note": str,
        "raw_response": optional str
      }
    """
    text = (text or "").strip()
    if not text:
        return {
            "facts": [],
            "extractor": "none",
            "note": "Empty text — nothing to extract.",
            "raw_response": None,
        }

    if force_fallback or not GEMINI_API_KEY:
        facts, note = fallback_extract(text, source_type)
        if not GEMINI_API_KEY:
            note = (
                "FALLBACK: GEMINI_API_KEY not configured. "
                "Using deterministic rule-based extraction. "
                "Gemini does not resolve conflicts — CAMS will."
            )
        return {"facts": facts, "extractor": "fallback", "note": note, "raw_response": None}

    try:
        raw = _call_gemini(text, source_type)
        facts = parse_gemini_response(raw, source_type)
        if not facts:
            # Empty parse — fall back so demo still produces something
            fb, note = fallback_extract(text, source_type)
            return {
                "facts": fb,
                "extractor": "fallback",
                "note": "FALLBACK: Gemini returned no parseable facts. " + note,
                "raw_response": raw,
            }
        return {
            "facts": facts,
            "extractor": "gemini",
            "note": (
                "Gemini extracted facts and evidence quotes only. "
                "It did NOT decide which claim is true — CAMS handles synchronization."
            ),
            "raw_response": raw,
        }
    except Exception as exc:  # noqa: BLE001 — demo must continue
        facts, note = fallback_extract(text, source_type)
        return {
            "facts": facts,
            "extractor": "fallback",
            "note": f"FALLBACK after Gemini error ({type(exc).__name__}: {exc}). {note}",
            "raw_response": None,
        }
