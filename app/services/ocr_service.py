"""
PDF OCR / extraction service for NyayaOS.

1) Extract text from PDF (pypdf)
2) Optionally structure with Gemini into fact fields
3) Caller feeds result into ObservationService.ingest

Never logs API keys.
"""
from __future__ import annotations

import json
import re
from io import BytesIO
from typing import Any

from app.core import demo_log
from app.services.gemini_service import GeminiConfigError, GeminiService, get_gemini_service


class OCRService:
    def __init__(self, gemini: GeminiService | None = None) -> None:
        self.gemini = gemini or get_gemini_service()

    def extract_text_from_pdf(self, data: bytes, filename: str = "upload.pdf") -> str:
        demo_log.banner("OCR / PDF EXTRACTION")
        demo_log.step(1, "Extract text from PDF", filename=filename, bytes=len(data))
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("pypdf is not installed. Run: pip install pypdf") from exc

        reader = PdfReader(BytesIO(data))
        pages: list[str] = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            pages.append(text)
            demo_log.info(f"Page {i + 1}: {len(text)} characters")
        joined = "\n".join(pages).strip()
        if not joined:
            raise ValueError("No extractable text found in PDF (scanned image-only PDFs need OCR hardware/API)")
        demo_log.success(f"Extracted {len(joined)} characters from {len(pages)} page(s)")
        return joined

    def structure_legal_fact(
        self,
        text: str,
        *,
        default_fact_name: str = "bail_status",
    ) -> dict[str, Any]:
        """
        Turn raw PDF text into structured fields for ObservationCreate.
        Uses Gemini when configured; otherwise a deterministic keyword heuristic.
        """
        demo_log.step(2, "Structure extracted text into a legal fact")
        preview = text[:500].replace("\n", " ")
        demo_log.info("Text preview", preview=preview + ("…" if len(text) > 500 else ""))

        if self.gemini.is_configured:
            try:
                structured = self._structure_with_gemini(text, default_fact_name)
                demo_log.success("Structured via Gemini")
                demo_log.info("Structured output", **{k: structured.get(k) for k in structured})
                return structured
            except (GeminiConfigError, Exception) as exc:  # noqa: BLE001
                demo_log.warn(f"Gemini structuring failed ({exc}); using heuristic fallback")

        structured = self._structure_heuristic(text, default_fact_name)
        demo_log.success("Structured via heuristic fallback (no Gemini / Gemini failed)")
        demo_log.info("Structured output", **structured)
        return structured

    def _structure_with_gemini(self, text: str, default_fact_name: str) -> dict[str, Any]:
        prompt = f"""
You extract structured facts for an Indian justice digital twin.
Return ONLY valid JSON with keys:
fact_name (string), value (string), extraction_reliability (0..1), summary (string).
Prefer fact_name like bail_status, custody_status, hearing_date, forensic_result, identity.
Default fact_name if unclear: {default_fact_name}.

Document text:
\"\"\"{text[:6000]}\"\"\"
"""
        raw = self.gemini.generate_text(prompt, temperature=0.1)
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise ValueError("Gemini did not return JSON")
        data = json.loads(match.group(0))
        value = str(data.get("value", "unknown"))
        return {
            "fact_name": str(data.get("fact_name") or default_fact_name),
            "candidate_value": {"v": value, "summary": data.get("summary")},
            "extraction_reliability": float(data.get("extraction_reliability", 0.75)),
            "engine": "gemini",
        }

    def _structure_heuristic(self, text: str, default_fact_name: str) -> dict[str, Any]:
        lower = text.lower()
        value = "unknown"
        fact_name = default_fact_name
        reliability = 0.55

        if "bail granted" in lower or "bail is granted" in lower:
            fact_name, value, reliability = "bail_status", "bail_granted", 0.7
        elif "bail denied" in lower or "bail rejected" in lower:
            fact_name, value, reliability = "bail_status", "bail_denied", 0.7
        elif "in custody" in lower or "remanded" in lower:
            fact_name, value, reliability = "custody_status", "in_custody", 0.65
        elif "released" in lower:
            fact_name, value, reliability = "custody_status", "released", 0.65
        elif "hearing" in lower:
            fact_name, value, reliability = "hearing_date", "scheduled", 0.5

        return {
            "fact_name": fact_name,
            "candidate_value": {"v": value, "excerpt": text[:240]},
            "extraction_reliability": reliability,
            "engine": "heuristic",
        }
