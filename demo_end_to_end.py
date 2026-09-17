#!/usr/bin/env python3
"""
CASE-001 end-to-end demo — writes only under data/demo_cases/.
"""

from __future__ import annotations

from demo_data import CASE_001_DESCRIPTION, CASE_001_ID, CASE_001_TITLE, case_001_documents
from file_repository import DEMO_DATA_ROOT, demo_repo
from pipeline import Pipeline
import console_log as clog

pipe = Pipeline(repository=demo_repo)


def main() -> None:
    clog.banner("DEMO END-TO-END")
    clog.kv("storage", str(DEMO_DATA_ROOT.resolve()))
    clog.detail("Isolated from data/cases/.")
    demo_repo.reset_all()
    pipe.create_case(CASE_001_ID, CASE_001_TITLE, CASE_001_DESCRIPTION)
    for doc in case_001_documents():
        pipe.ingest_text(
            CASE_001_ID,
            text=doc["text"],
            source=doc["source_id"],
            source_type=doc["source_type"],
            title=doc.get("title") or "",
            force_fallback=True,
        )
    view = pipe.full_case_view(CASE_001_ID)
    clog.banner("SUMMARY", CASE_001_ID)
    clog.kv("summary", view["summary"])
    clog.kv("folder", view["storage_hint"])
    clog.done("demo complete")


if __name__ == "__main__":
    main()
