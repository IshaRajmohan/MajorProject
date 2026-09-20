#!/usr/bin/env python3
"""
Qualitative CAMS demo — uses Pipeline + demo-scoped PostgreSQL (no HTTP).
Never writes to real (is_demo=False) cases. Upload bytes under data/demo_cases/.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import console_log as clog
from db_repository import DbRepository
from paths import DEMO_DATA_ROOT
from pipeline import Pipeline

repo = DbRepository(demo=True)
pipe = Pipeline(repository=repo)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def run() -> None:
    clog.banner("QUALITATIVE SIMULATE (demo storage only)")
    clog.kv("demo_root", str(DEMO_DATA_ROOT.resolve()))
    clog.detail("Real user cases are NOT touched.")

    await repo.reset_all()
    scenarios = [
        (
            "demo-conflict",
            "charge",
            [
                dict(
                    text="Charge: IPC 302\n",
                    source="court-delhi-1",
                    source_type="court",
                ),
                dict(
                    text="Charge: IPC 304\n",
                    source="news-toi",
                    source_type="media",
                ),
            ],
        ),
        (
            "demo-delayed",
            "arrest_date",
            [
                dict(
                    text="Arrested on 10 April 2024\n",
                    source="police-station-12",
                    source_type="police",
                ),
                dict(
                    text="Arrested on 01 March 2024\n",
                    source="wit-anonymous",
                    source_type="witness",
                ),
            ],
        ),
    ]

    for case_id, _fact, docs in scenarios:
        await pipe.create_case(case_id, title=case_id)
        for d in docs:
            await pipe.ingest_text(
                case_id,
                text=d["text"],
                source=d["source"],
                source_type=d["source_type"],
                force_fallback=True,
            )
        twin = await repo.get_facts(case_id)
        clog.banner("TWIN AFTER SCENARIO", case_id)
        for k, v in twin.items():
            clog.detail(f"{k} = {v.get('value')!r} ({v.get('status')})")

    clog.done(f"simulate finished — see {DEMO_DATA_ROOT.resolve()}")


if __name__ == "__main__":
    asyncio.run(run())
