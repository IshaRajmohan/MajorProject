"""Lightweight document cleaning / normalization before extraction."""

from __future__ import annotations

import re
import unicodedata
from typing import Tuple


def process_document(raw_text: str) -> Tuple[str, str]:
    """
    Normalize document text for rule-based extraction.

    Returns (cleaned_text, notes).
    """
    if raw_text is None:
        return "", "empty"

    text = unicodedata.normalize("NFKC", raw_text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse whitespace but keep newlines as paragraph breaks
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    cleaned = "\n".join(lines)
    notes = f"lines={len(lines)} chars={len(cleaned)}"
    return cleaned, notes
