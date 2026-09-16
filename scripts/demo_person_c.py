"""
Person C console demonstration — Justice Digital Twin + CAMS observation pipeline.

Run from the repository root (no frontend, no browser):

    python scripts/demo_person_c.py

Uses an isolated in-memory SQLite database so the demo never needs PostgreSQL
or a running API server. Teachers can follow numbered steps and tables.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Allow `python scripts/demo_person_c.py` from any cwd.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.cams import CAMSWeights, FactorCalculator, score, synchronize
from app.core import demo_log
from app.core.security import hash_password
from app.models.base import Base
from app.models.case import Case, Entity
from app.models.observation import Observation, SyncDecision, TwinState, TwinStateVersion  # noqa: F401
from app.models.source_authority import CAMSConfig, SourceAuthorityRule
from app.models.user import User
from app.schemas.observation import ObservationCreate
from app.services.observation_service import ObservationService


def heading(number: int, title: str) -> None:
    demo_log.banner(f"STEP {number}: {title}")


def explain(text: str) -> None:
    demo_log.info(text)


async def make_user(db: AsyncSession, *, name: str, email: str, role: str) -> User:
    user = User(
        name=name,
        email=email,
        hashed_password=hash_password("DemoPass123!"),
        role=role,
        org="Demo Court Complex",
    )
    db.add(user)
    await db.flush()
    return user


async def ingest(
    db: AsyncSession,
    user: User,
    *,
    case_id: str,
    entity_id: str,
    fact_name: str,
    source_role: str,
    value: dict,
    extraction_reliability: float | None = None,
    event_time: datetime | None = None,
    raw_source_ref: str | None = None,
):
    service = ObservationService(db)
    return await service.ingest(
        ObservationCreate(
            case_id=case_id,
            entity_id=entity_id,
            fact_name=fact_name,
            source_role=source_role,
            candidate_value=value,
            extraction_reliability=extraction_reliability,
            event_time=event_time,
            raw_source_ref=raw_source_ref,
        ),
        user,
    )


def print_observation_table(rows: list[Observation]) -> None:
    demo_log.table(
        ["id[:8]", "role", "value", "E", "event_time", "status"],
        [
            [
                o.id[:8],
                o.source_role,
                o.candidate_value,
                f"{o.extraction_reliability:.2f}",
                "-" if o.event_time is None else str(o.event_time),
                o.status,
            ]
            for o in rows
        ],
    )


def print_ranking(snapshot: dict) -> None:
    ranked = sorted(snapshot.items(), key=lambda kv: kv[1].get("score") or 0, reverse=True)
    demo_log.table(
        ["rank", "obs[:8]", "value", "A", "T", "X", "E", "CAMS C"],
        [
            [
                i + 1,
                oid[:8],
                data.get("value"),
                f"{data.get('A', 0):.3f}",
                f"{data.get('T', 0):.3f}",
                f"{data.get('X', 0):.3f}",
                f"{data.get('E', 0):.3f}",
                f"{(data.get('score') or 0):.4f}",
            ]
            for i, (oid, data) in enumerate(ranked)
        ],
    )


async def print_twin(db: AsyncSession, case_id: str) -> None:
    service = ObservationService(db)
    facts = await service.get_twin_facts(case_id)
    if not facts:
        explain("Twin has no accepted facts yet (unresolved / never updated).")
        return
    demo_log.table(
        ["fact", "version", "value", "confidence", "updated_at"],
        [
            [
                f.get("fact_name"),
                f.get("version"),
                f.get("current_value"),
                "-" if f.get("confidence") is None else f"{f['confidence']:.4f}",
                f.get("updated_at"),
            ]
            for f in facts
        ],
    )


async def run() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        heading(0, "Person C console demo — NyayaOS Justice Twin")
        explain("This script uses local Python objects + an in-memory SQLite database.")
        explain("No web UI, no browser, and no Gemini/OpenAI calls.")
        explain("CAMS engine is the existing pure-Python module: app.cams.synchronize()")

        heading(1, "Creating a demo case")
        court = await make_user(db, name="Judge Mehta", email="court@demo.local", role="court")
        police = await make_user(db, name="Inspector Rao", email="police@demo.local", role="police")
        lawyer = await make_user(db, name="Adv. Sharma", email="lawyer@demo.local", role="lawyer")
        forensic = await make_user(db, name="Dr. Iyer", email="forensic@demo.local", role="forensic")

        db.add(
            CAMSConfig(
                case_id=None,
                weight_authority=0.3,
                weight_temporal=0.3,
                weight_corroboration=0.2,
                weight_extraction=0.2,
                tau=0.6,
                delta=0.1,
                is_active=True,
            )
        )
        for (fact_type, role), a in FactorCalculator.DEFAULT_AUTHORITY_RULES.items():
            db.add(SourceAuthorityRule(fact_type=fact_type, source_role=role, authority_score=a))

        case = Case(
            case_number="NYA-DEMO-C",
            title="State vs. Demo Accused — Bail Status (Person C viva)",
            status="open",
        )
        db.add(case)
        await db.flush()
        entity = Entity(
            case_id=case.id,
            entity_type="person",
            label="Demo Accused",
            attributes={"role_in_case": "accused", "age": 34},
        )
        db.add(entity)
        await db.commit()

        explain(f"Case number: {case.case_number}")
        explain(f"Case id:     {case.id}")
        explain(f"Entity:      {entity.label} ({entity.id})")
        explain("Actors: court, police, lawyer, forensic (role-based authority).")
        demo_log.table(
            ["role", "name", "why they matter"],
            [
                ["court", court.name, "Highest authority for bail_status (A=0.95)"],
                ["police", police.name, "Operational source (A=0.55 for bail)"],
                ["lawyer", lawyer.name, "Weaker authority / low-confidence demos"],
                ["forensic", forensic.name, "Highest authority for forensic_result"],
            ],
        )

        heading(2, "Adding observations (append-only)")
        explain("Observations are never overwritten. Each ingest is a new row.")
        now = datetime.now(UTC).replace(tzinfo=None)

        r_court = await ingest(
            db,
            court,
            case_id=case.id,
            entity_id=entity.id,
            fact_name="bail_status",
            source_role="court",
            value={"status": "granted"},
            extraction_reliability=1.0,
            event_time=now,
            raw_source_ref="order-sheet-12.pdf",
        )
        explain("Court filed: bail_status = granted (structured, E=1.0)")

        heading(3, "Displaying observation details")
        service = ObservationService(db)
        rows = await service.list_observations(case.id)
        print_observation_table(rows)

        heading(4, "Extracting / preparing facts")
        explain("FactKey groups all observations for (case, entity, fact_name).")
        explain(f"Fact name: bail_status    FactKey: {r_court['fact_key_id']}")
        explain("candidate_value is JSON so facts stay structured (status, dates, etc.).")

        heading(5, "Calculating A / T / X / E factors")
        explain("A = source authority (role × fact type)")
        explain("T = temporal consistency vs last twin update")
        explain("X = independent sources that agree on the same value")
        explain("E = extraction reliability (1.0 = typed/structured; low = noisy OCR)")
        decision = r_court["decision"]
        print_ranking(decision.candidates_snapshot)

        heading(6, "Calculating CAMS scores")
        weights = CAMSWeights(0.3, 0.3, 0.2, 0.2)
        explain("C = 0.3·A + 0.3·T + 0.2·X + 0.2·E   (weights sum to 1)")
        explain(f"Thresholds: tau={decision.tau} (min confidence), delta={decision.delta} (min margin)")
        calc = FactorCalculator()
        preview = calc.build_candidate(
            observation_id="preview-court",
            value={"status": "granted"},
            source_role="court",
            fact_type="bail_status",
            event_time=now,
            extraction_reliability=1.0,
        )
        explain(f"Worked example (court, T=0.5 if no twin yet): C={score(preview, weights):.4f}")

        heading(7, "Showing candidate ranking")
        print_ranking(decision.candidates_snapshot)

        heading(8, "Running synchronization")
        explain("synchronize() is Person B's pure-Python CAMS Algorithm 1.")
        sync = r_court["sync"]
        explain(f"decision={sync.decision}  c1={sync.c1:.4f}  c2={sync.c2}  {sync.explanation}")

        heading(9, "Showing the SyncDecision")
        demo_log.table(
            ["field", "value"],
            [
                ["decision", decision.decision],
                ["c1", f"{decision.c1:.4f}"],
                ["c2", decision.c2],
                ["tau", decision.tau],
                ["delta", decision.delta],
                ["winner", decision.winning_observation_id],
                ["explanation", decision.explanation],
            ],
        )

        heading(10, "Updating Justice Twin / ODFS state")
        explain("On decision=updated, TwinState pointer advances and a new ODFS version is appended.")
        await print_twin(db, case.id)
        versions = await service.list_versions(case.id, r_court["fact_key_id"])
        demo_log.table(
            ["v", "value", "confidence", "created_at"],
            [[v.version, v.value, f"{(v.confidence or 0):.4f}", v.created_at] for v in versions],
        )

        heading(11, "Corroboration: police and lawyer agree with the court")
        await ingest(
            db,
            police,
            case_id=case.id,
            entity_id=entity.id,
            fact_name="bail_status",
            source_role="police",
            value={"status": "granted"},
            extraction_reliability=1.0,
            event_time=now,
        )
        r_lawyer = await ingest(
            db,
            lawyer,
            case_id=case.id,
            entity_id=entity.id,
            fact_name="bail_status",
            source_role="lawyer",
            value={"status": "granted"},
            extraction_reliability=1.0,
            event_time=now,
        )
        explain("Independent agreeing sources increase X (corroboration). Court should still win.")
        print_ranking(r_lawyer["decision"].candidates_snapshot)
        await print_twin(db, case.id)

        heading(12, "Demonstrating conflicting observations")
        explain("Police now reports a conflicting value: bail_status = denied.")
        r_conflict = await ingest(
            db,
            police,
            case_id=case.id,
            entity_id=entity.id,
            fact_name="bail_status",
            source_role="police",
            value={"status": "denied"},
            extraction_reliability=1.0,
            event_time=now,
        )
        print_ranking(r_conflict["decision"].candidates_snapshot)
        explain(
            f"SyncDecision: {r_conflict['sync'].decision} — {r_conflict['sync'].explanation}"
        )
        explain("Court remains more authoritative for bail; twin should keep 'granted' if margin holds.")
        await print_twin(db, case.id)

        heading(13, "Demonstrating a delayed (out-of-order) observation")
        delayed_time = now - timedelta(days=25)
        r_delay = await ingest(
            db,
            police,
            case_id=case.id,
            entity_id=entity.id,
            fact_name="bail_status",
            source_role="police",
            value={"status": "in_custody"},
            extraction_reliability=1.0,
            event_time=delayed_time,
        )
        explain(f"Delayed event_time = {delayed_time} (25 days before the twin chronology anchor).")
        explain("Temporal factor T decays linearly over ~30 days of lateness.")
        print_ranking(r_delay["decision"].candidates_snapshot)
        await print_twin(db, case.id)

        heading(14, "Demonstrating a duplicate observation")
        r_dup = await ingest(
            db,
            court,
            case_id=case.id,
            entity_id=entity.id,
            fact_name="bail_status",
            source_role="court",
            value={"status": "granted"},
            extraction_reliability=1.0,
            event_time=now,
        )
        explain(f"is_duplicate={r_dup['is_duplicate']}  decision={r_dup['sync'].decision}")
        explain("Duplicates are stored for audit. Equal top scores fail the delta margin → retained.")
        print_ranking(r_dup["decision"].candidates_snapshot)

        heading(15, "Demonstrating noisy vs clean forensic evidence")
        r_clean = await ingest(
            db,
            forensic,
            case_id=case.id,
            entity_id=entity.id,
            fact_name="forensic_result",
            source_role="forensic",
            value={"result": "DNA_match"},
            extraction_reliability=1.0,
            raw_source_ref="fsl-lab-sheet",
        )
        r_noisy = await ingest(
            db,
            forensic,
            case_id=case.id,
            entity_id=entity.id,
            fact_name="forensic_result",
            source_role="forensic",
            value={"result": "inconclusive_scan"},
            extraction_reliability=0.18,
            raw_source_ref="blurry-ocr",
        )
        explain("Noisy OCR (E=0.18) is ranked below a clean structured lab result (E=1.0).")
        print_ranking(r_noisy["decision"].candidates_snapshot)
        explain(f"Forensic twin updated? {r_noisy['twin_updated']}  decision={r_noisy['sync'].decision}")

        heading(16, "Demonstrating a low-confidence observation")
        r_low = await ingest(
            db,
            lawyer,
            case_id=case.id,
            entity_id=entity.id,
            fact_name="identity",
            source_role="lawyer",
            value={"name": "possibly Ramesh?"},
            extraction_reliability=0.15,
        )
        explain(
            f"Single weak candidate: C={r_low['sync'].c1:.4f} < tau=0.6 → {r_low['sync'].decision}"
        )
        explain("Twin is NOT created for identity because confidence is insufficient.")
        await print_twin(db, case.id)

        heading(17, "Displaying final case facts and confidence")
        print_observation_table(await service.list_observations(case.id))
        await print_twin(db, case.id)
        explain("ODFS versions for bail_status (history is append-only):")
        bail_versions = await service.list_versions(case.id, r_court["fact_key_id"])
        demo_log.table(
            ["v", "value", "confidence"],
            [[v.version, v.value, f"{(v.confidence or 0):.4f}"] for v in bail_versions],
        )
        explain("ODFS versions for forensic_result:")
        demo_log.table(
            ["v", "value", "confidence"],
            [
                [v.version, v.value, f"{(v.confidence or 0):.4f}"]
                for v in await service.list_versions(case.id, r_clean["fact_key_id"])
            ],
        )

        heading(18, "What teachers should take away")
        explain("1. Observations are append-only evidence, not overwrites.")
        explain("2. CAMS scores candidates with A/T/X/E, then applies tau and delta.")
        explain("3. Justice Twin holds the current accepted fact + confidence.")
        explain("4. ODFS stores every accepted version so history can be audited.")
        explain("5. Conflict, delay, noise, duplicates, and low confidence are first-class cases.")
        demo_log.banner("DEMO COMPLETE — Person C")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
