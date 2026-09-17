#!/usr/bin/env python3
"""
Qualitative CAMS demo — uses Pipeline + data/demo_cases/ directly (no HTTP).
Never writes to data/cases/.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import console_log as clog
from file_repository import DEMO_DATA_ROOT, demo_repo
from pipeline import Pipeline

pipe = Pipeline(repository=demo_repo)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def run() -> None:
    clog.banner("QUALITATIVE SIMULATE (demo storage only)")
    clog.kv("demo_root", str(DEMO_DATA_ROOT.resolve()))
    clog.detail("Real user cases under data/cases/ are NOT touched.")

    demo_repo.reset_all()
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
        pipe.create_case(case_id, title=case_id)
        for d in docs:
            pipe.ingest_text(
                case_id,
                text=d["text"],
                source=d["source"],
                source_type=d["source_type"],
                force_fallback=True,
            )
        twin = demo_repo.get_facts(case_id)
        clog.banner("TWIN AFTER SCENARIO", case_id)
        for k, v in twin.items():
            clog.detail(f"{k} = {v.get('value')!r} ({v.get('status')})")

    clog.done(f"simulate finished — see {DEMO_DATA_ROOT.resolve()}")


if __name__ == "__main__":
    run()
