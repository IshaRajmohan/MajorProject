"""Readable terminal progress logs for the NyayaOS pipeline."""

from __future__ import annotations

import sys
from typing import Any, Iterable, Optional


def _out(msg: str = "") -> None:
    print(msg, flush=True, file=sys.stdout)


def banner(title: str, case_id: Optional[str] = None) -> None:
    label = f" CASE {case_id} | {title} " if case_id else f" {title} "
    line = "=" * max(64, len(label) + 4)
    _out("")
    _out(line)
    _out(label.center(len(line)))
    _out(line)


def step(msg: str) -> None:
    _out(f"→ {msg}")


def detail(msg: str, indent: int = 2) -> None:
    _out((" " * indent) + msg)


def kv(key: str, value: Any, indent: int = 2) -> None:
    detail(f"{key}: {value}", indent=indent)


def list_items(items: Iterable[str], indent: int = 4) -> None:
    for item in items:
        detail(f"• {item}", indent=indent)


def cams_candidate_line(
    value: Any,
    confidence: float,
    factors: dict,
) -> str:
    f = factors or {}
    return (
        f"value={value!r}  C={confidence:.3f}  "
        f"A={float(f.get('source_authority', 0)):.2f} "
        f"T={float(f.get('temporal_consistency', 0)):.2f} "
        f"X={float(f.get('cross_source_corroboration', 0)):.2f} "
        f"E={float(f.get('extraction_reliability', 0)):.2f}"
    )


def done(msg: str = "done") -> None:
    _out(f"✓ {msg}")
