"""Regenerate the demo PDF from the demo .txt (hand-rolled, no PDF library).

    python frontend/demo/_make_demo_pdf.py

Rebuilds nyayaos-demo-fir-police.pdf as a real single-font text-layer PDF so
pypdf can read it without Tesseract. Kept next to the documents it produces.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "nyayaos-demo-fir-police.txt"
DST = HERE / "nyayaos-demo-fir-police.pdf"

FONT_SIZE = 9.5
LEADING = 12.5
LEFT = 46.0
TOP = 786.0
PAGE_HEIGHT = 842.0
PAGE_WIDTH = 595.0
LINES_PER_PAGE = int((TOP - 50.0) // LEADING)


def esc(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_pdf(text: str) -> tuple[bytes, int]:
    lines = text.split("\n")
    chunks = [
        lines[i:i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)
    ] or [[""]]

    streams = []
    for chunk in chunks:
        parts = ["BT", f"/F1 {FONT_SIZE} Tf", f"{LEADING} TL", f"{LEFT} {TOP} Td"]
        parts += [f"({esc(ln)}) Tj T*" for ln in chunk]
        parts.append("ET")
        streams.append("\n".join(parts).encode("latin-1", "replace"))

    n_pages = len(streams)
    catalog_num, pages_num, first_page_num = 1, 2, 3
    page_nums, content_nums = [], []
    n = first_page_num
    for _ in range(n_pages):
        page_nums.append(n)
        content_nums.append(n + 1)
        n += 2
    font_num = n

    objects = [None] * (font_num)
    objects[catalog_num - 1] = f"<< /Type /Catalog /Pages {pages_num} 0 R >>".encode()
    kids = " ".join(f"{p} 0 R" for p in page_nums)
    objects[pages_num - 1] = f"<< /Type /Pages /Count {n_pages} /Kids [{kids}] >>".encode()
    for i, pnum in enumerate(page_nums):
        objects[pnum - 1] = (
            f"<< /Type /Page /Parent {pages_num} 0 R "
            f"/MediaBox [0 0 {PAGE_WIDTH:.1f} {PAGE_HEIGHT:.1f}] "
            f"/Resources << /Font << /F1 {font_num} 0 R >> >> "
            f"/Contents {content_nums[i]} 0 R >>"
        ).encode()
        objects[content_nums[i] - 1] = streams[i]
    objects[font_num - 1] = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >>"
    )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for idx, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{idx} 0 obj\n".encode()
        if isinstance(body, bytes) and body[:2] == b"BT":
            out += f"<< /Length {len(body)} >>\nstream\n".encode()
            out += body
            out += b"\nendstream\n"
        else:
            out += body
            out += b"\n"
        out += b"endobj\n"

    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    out += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets)
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_num} 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    return bytes(out), n_pages


if __name__ == "__main__":
    payload, pages = build_pdf(SRC.read_text(encoding="utf-8"))
    DST.write_bytes(payload)
    print(f"wrote {DST.name} ({len(payload)} bytes, {pages} pages)")
