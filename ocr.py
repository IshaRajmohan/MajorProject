"""
OCR / document text extraction for uploaded PDFs and images.

Priority:
  1) PDF text layer via pypdf (fast, no system deps)
  2) Image / scanned-page OCR via Tesseract if installed
  3) Clear labelled failure so the UI can ask the user to paste text

OCR only recovers text. Gemini/fallback then extract facts. CAMS still decides.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
PDF_EXTS = {".pdf"}
TEXT_EXTS = {".txt", ".md", ".csv"}


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    # keep blank lines collapsed
    out: List[str] = []
    for ln in lines:
        if ln:
            out.append(ln)
        elif out and out[-1] != "":
            out.append("")
    return "\n".join(out).strip()


def extract_text_from_pdf_bytes(data: bytes) -> Tuple[str, Dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is not installed. Run: pip install pypdf") from exc

    reader = PdfReader(io.BytesIO(data))
    pages: List[str] = []
    for i, page in enumerate(reader.pages):
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001
            pages.append(f"[page {i+1} extract error: {exc}]")
    text = _clean("\n\n".join(pages))
    meta = {
        "method": "pypdf",
        "pages": len(reader.pages),
        "chars": len(text),
        "has_text_layer": bool(text),
    }
    return text, meta


def extract_text_from_image_bytes(data: bytes, filename: str = "image.png") -> Tuple[str, Dict[str, Any]]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is not installed. Run: pip install pillow") from exc

    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError(
            "pytesseract is not installed. Run: pip install pytesseract "
            "and install the Tesseract OCR binary (e.g. brew install tesseract)."
        ) from exc

    img = Image.open(io.BytesIO(data))
    # Improve OCR a bit on simple scans
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    try:
        text = pytesseract.image_to_string(img)
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError(
            "Tesseract OCR binary not found. Install it (macOS: brew install tesseract) "
            "or paste the document text manually."
        ) from exc

    text = _clean(text)
    meta = {
        "method": "tesseract",
        "filename": filename,
        "size": img.size,
        "chars": len(text),
    }
    return text, meta


def extract_text_from_plain_bytes(data: bytes) -> Tuple[str, Dict[str, Any]]:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            text = _clean(data.decode(enc))
            return text, {"method": f"plain:{enc}", "chars": len(text)}
        except UnicodeDecodeError:
            continue
    text = _clean(data.decode("utf-8", errors="replace"))
    return text, {"method": "plain:replace", "chars": len(text)}


def ocr_file(
    data: bytes,
    filename: str,
    content_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract text from an uploaded file.

    Returns dict with: text, method, note, meta, ok
    """
    name = filename or "upload.bin"
    ext = Path(name).suffix.lower()
    ctype = (content_type or "").lower()

    try:
        if ext in TEXT_EXTS or ctype.startswith("text/"):
            text, meta = extract_text_from_plain_bytes(data)
            note = "Read as plain text file."
        elif ext in PDF_EXTS or "pdf" in ctype:
            text, meta = extract_text_from_pdf_bytes(data)
            if text:
                note = f"PDF text layer extracted with pypdf ({meta.get('pages')} pages)."
            else:
                # PDF may be scan-only — try rendering first page via optional deps is heavy;
                # tell the user clearly.
                note = (
                    "PDF has little/no selectable text (likely a scan). "
                    "Install Tesseract and re-upload page images, or paste text manually."
                )
        elif ext in IMAGE_EXTS or ctype.startswith("image/"):
            text, meta = extract_text_from_image_bytes(data, filename=name)
            note = "Image OCR via Tesseract."
        else:
            # Best-effort: try PDF then plain
            try:
                text, meta = extract_text_from_pdf_bytes(data)
                note = "Treated upload as PDF."
            except Exception:
                text, meta = extract_text_from_plain_bytes(data)
                note = f"Unknown type {ext or ctype}; treated as text."

        ok = bool(text and text.strip())
        if not ok:
            note = (
                (note + " ") if note else ""
            ) + "No usable text recovered. Paste the content into the text box, or use a text-based PDF / clearer scan."
        return {
            "ok": ok,
            "text": text or "",
            "method": meta.get("method"),
            "note": note,
            "meta": meta,
            "filename": name,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "text": "",
            "method": None,
            "note": f"OCR failed: {type(exc).__name__}: {exc}",
            "meta": {},
            "filename": name,
            "error": str(exc),
        }
