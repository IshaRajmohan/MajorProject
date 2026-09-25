"""Neutral runtime filesystem paths (Task 4).

Only raw upload bytes and extracted text (.md) live on disk, under:

  data/cases/{case_number}/        (is_demo=False — real cases)
  data/demo_cases/{case_number}/   (is_demo=True — demo cases)

All structured case/CAMS state is persisted in PostgreSQL (db_repository.py).
Legacy JSON files left under these trees are never read at runtime and are
kept only for historical reference.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_ROOT = ROOT / "data" / "cases"
DEMO_DATA_ROOT = ROOT / "data" / "demo_cases"
