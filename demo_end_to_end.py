#!/usr/bin/env python3
"""
CASE-001 end-to-end demo — writes only demo-scoped PostgreSQL + data/demo_cases/.
"""

from __future__ import annotations

import asyncio

from demo_data import CASE_001_DESCRIPTION, CASE_001_ID, CASE_001_TITLE, case_001_documents
from db_repository import DbRepository
from paths import DEMO_DATA_ROOT
from pipeline import Pipeline
import console_log as clog

repo = DbRepository(demo=True)
pipe = Pipeline(repository=repo)


async def main() -> None:
    clog.banner("DEMO END-TO-END")
    clog.kv("storage", str(DEMO_DATA_ROOT.resolve()))
    clog.detail("Isolated from real (is_demo=False) cases.")
    await repo.reset_all()
    await pipe.create_case(CASE_001_ID, CASE_001_TITLE, CASE_001_DESCRIPTION)
    for doc in case_001_documents():
        await pipe.ingest_text(
            CASE_001_ID,
            text=doc["text"],
            source=doc["source_id"],
            source_type=doc["source_type"],
            title=doc.get("title") or "",
            force_fallback=True,
        )
    view = await pipe.full_case_view(CASE_001_ID)
    clog.banner("SUMMARY", CASE_001_ID)
    clog.kv("summary", view["summary"])
    clog.kv("folder", view["storage_hint"])
    clog.done("demo complete")


if __name__ == "__main__":
    asyncio.run(main())
