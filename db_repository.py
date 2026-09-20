"""
Async PostgreSQL repository for NyayaOS (replaces FileRepository at runtime).

Structured case/CAMS state lives in PostgreSQL via the Task 1/2 models in
``db_models.py``. Only raw uploaded file bytes (and extracted .txt) are
written to disk, under the same layout as before:

  data/cases/{case_number}/            (real cases, is_demo=False)
  data/demo_cases/{case_number}/       (demo cases, is_demo=True)
    uploads/{stored_name}
    stakeholders/{source_type}__{source_id}/documents/{stored_name}

``DbRepository(demo=False)`` scopes every query by ``cases.is_demo`` so a
demo case and a real case may share a case_number (e.g. CASE-001) without
mixing. ``cases.id`` (UUID) is the internal FK; ``case_number`` is the
external identifier used by the API.

Serialization reproduces the old JSON shapes exactly (same dict keys and
ISO-8601 timestamp strings) so the FastAPI responses and the dashboard are
unchanged. Observations, sync_history and provenance are append-only.

Task 3 additions: documents carry an explicit ``visibility``
(INTERNAL | CITIZEN_VISIBLE, enforced by rbac.py filters), and citizen
submissions live in ``submissions`` — a PENDING row only becomes an official
document (and thus CAMS input) through an assigned COURT approval.
"""

from __future__ import annotations

import enum
import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import db
import db_models
from paths import DATA_ROOT, DEMO_DATA_ROOT

ROOT = Path(__file__).resolve().parent


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any, fallback: Optional[datetime] = None) -> datetime:
    if value is None or value == "":
        return fallback or _utcnow()
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return fallback or _utcnow()


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _iso_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _iso(value)
    return value.isoformat() if isinstance(value, date) else str(value)


def _parse_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, enum.Enum) else value


def _safe_segment(value: str, fallback: str = "unknown") -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or fallback).strip())[:80]
    return s or fallback


def stakeholder_key(source_type: str, source_id: str) -> str:
    return f"{_safe_segment(source_type)}__{_safe_segment(source_id)}"


def _u(value: Any) -> Optional[UUID]:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


# ---- row → old-JSON-shape dict serializers ----

def case_to_dict(row: db_models.Case) -> Dict[str, Any]:
    return {
        "case_id": row.case_number,
        "title": row.title,
        "description": row.description,
        "case_type": row.case_type,
        "case_status": row.case_status,
        "filing_date": _iso_date(row.filing_date),
        "court_name": row.court_name,
        "next_hearing_date": _iso_date(row.next_hearing_date),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _document_to_dict(row: db_models.Document, case_number: str) -> Dict[str, Any]:
    return {
        "document_id": str(row.document_id),
        "case_id": case_number,
        "source": row.source_id,
        "source_id": row.source_id,
        "source_type": row.source_type,
        "title": row.title,
        "text": row.text,
        "ingestion_time": _iso(row.ingestion_time),
        "extractor": row.extractor,
        "extractor_note": row.extractor_note,
        "ocr": row.ocr,
        "visibility": _enum_value(row.visibility),
    }


def _observation_to_dict(row: db_models.Observation, case_number: str) -> Dict[str, Any]:
    rel = row.extraction_reliability
    return {
        "observation_id": str(row.observation_id),
        "case_id": case_number,
        "source": row.source_id,
        "source_id": row.source_id,
        "source_type": row.source_type,
        "fact_key": row.fact_key,
        "value": row.value,
        "event_time": _iso(row.event_time),
        "ingestion_time": _iso(row.ingestion_time),
        "evidence": row.evidence,
        "extraction_confidence": rel,
        "extraction_reliability": rel,
        "status": row.status,
        "document_id": str(row.document_id) if row.document_id else None,
    }


def _fact_to_dict(row: db_models.TwinFact) -> Dict[str, Any]:
    return {
        "fact_key": row.fact_key,
        "value": row.value,
        "status": row.status,
        "confidence": row.confidence,
        "last_updated": _iso(row.last_updated),
        "supporting_observation_ids": row.supporting_observation_ids or [],
        "provenance": row.provenance or [],
    }


def _conflict_to_dict(row: db_models.Conflict) -> Dict[str, Any]:
    return {
        "fact_key": row.fact_key,
        "status": row.status,
        "reason": row.reason,
        "explanation": row.explanation,
        "previous_value": row.previous_value,
        "C1": row.C1,
        "C2": row.C2,
        "margin": row.margin,
        "candidates": row.candidates or [],
        "updated_at": _iso(row.updated_at),
    }


def _history_to_dict(row: db_models.SyncHistory, case_number: str) -> Dict[str, Any]:
    return {
        "history_id": str(row.history_id),
        "case_id": case_number,
        "fact_key": row.fact_key,
        "timestamp": _iso(row.timestamp),
        "decision": row.decision,
        "decided": row.decided,
        "selected_value": row.selected_value,
        "previous_value": row.previous_value,
        "unresolved": row.unresolved,
        "C1": row.C1,
        "C2": row.C2,
        "margin": row.margin,
        "tau": row.tau,
        "delta": row.delta,
        "weights": row.weights,
        "candidates": row.candidates or [],
        "supporting_observation_ids": row.supporting_observation_ids or [],
        "reason": row.reason,
        "explanation": row.explanation,
        "trigger_document_id": str(row.trigger_document_id) if row.trigger_document_id else None,
        "trigger_observation_id": (
            str(row.trigger_observation_id) if row.trigger_observation_id else None
        ),
    }


def _upload_to_dict(row: db_models.Upload) -> Dict[str, Any]:
    return {
        "upload_id": str(row.upload_id),
        "original_filename": row.original_filename,
        "stored_filename": row.stored_filename,
        "case_upload_path": row.case_upload_path,
        "stakeholder_path": row.stakeholder_path,
        "extracted_text_path": row.extracted_text_path,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "bytes": row.byte_size,
        "saved_at": _iso(row.saved_at),
        "ocr_method": row.ocr_method,
        "ocr_note": row.ocr_note,
    }


def _submission_options():
    return (
        selectinload(db_models.Submission.submitter),
        selectinload(db_models.Submission.reviewer),
    )


def _submission_to_dict(row: db_models.Submission, case_number: str) -> Dict[str, Any]:
    return {
        "submission_id": str(row.submission_id),
        "case_id": case_number,
        "submitted_by": str(row.submitted_by),
        "submitted_by_email": row.submitter.email if row.submitter else None,
        "title": row.title,
        "text": row.text,
        "status": _enum_value(row.status),
        "created_at": _iso(row.created_at),
        "reviewed_by": str(row.reviewed_by) if row.reviewed_by else None,
        "reviewed_by_email": row.reviewer.email if row.reviewer else None,
        "reviewed_at": _iso(row.reviewed_at),
        "review_note": row.review_note,
        "document_id": str(row.document_id) if row.document_id else None,
    }


class DbRepository:
    """PostgreSQL-backed repository with FileRepository-compatible shapes."""

    def __init__(self, demo: bool = False, root: Optional[Path] = None) -> None:
        self.demo = demo
        self.root = Path(root) if root is not None else (
            DEMO_DATA_ROOT if demo else DATA_ROOT
        )
        self.root.mkdir(parents=True, exist_ok=True)

    # -- session/lookup helpers --

    def _session(self) -> AsyncSession:
        if db.AsyncSessionLocal is None:
            raise RuntimeError(
                "DATABASE_URL is not configured; PostgreSQL is required at runtime "
                "(no JSON/FileRepository fallback)."
            )
        return db.AsyncSessionLocal()

    async def _case_row(
        self, session: AsyncSession, case_id: str, create: bool = False
    ) -> db_models.Case:
        row = (
            await session.execute(
                select(db_models.Case).where(
                    db_models.Case.case_number == case_id,
                    db_models.Case.is_demo == self.demo,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            if create:
                row = db_models.Case(
                    case_number=case_id,
                    title=case_id,
                    description="",
                    is_demo=self.demo,
                )
                session.add(row)
                await session.flush()
            else:
                raise KeyError(f"case not found: {case_id}")
        return row

    # -- disk layout (upload bytes only; metadata lives in PostgreSQL) --

    def _case_dir(self, case_id: str) -> Path:
        d = self.root / case_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "stakeholders").mkdir(exist_ok=True)
        (d / "uploads").mkdir(exist_ok=True)
        return d

    def stakeholder_dir(self, case_id: str, source_type: str, source_id: str) -> Path:
        d = self._case_dir(case_id) / "stakeholders" / stakeholder_key(source_type, source_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "documents").mkdir(exist_ok=True)
        return d

    # -- cases --

    async def exists(self, case_id: str) -> bool:
        async with self._session() as session:
            row = (
                await session.execute(
                    select(db_models.Case.id).where(
                        db_models.Case.case_number == case_id,
                        db_models.Case.is_demo == self.demo,
                    )
                )
            ).scalar_one_or_none()
            return row is not None

    async def list_cases(self) -> List[Dict[str, Any]]:
        async with self._session() as session:
            rows = (
                await session.execute(
                    select(db_models.Case)
                    .where(db_models.Case.is_demo == self.demo)
                    .order_by(db_models.Case.created_at, db_models.Case.case_number)
                )
            ).scalars().all()
            return [case_to_dict(r) for r in rows]

    async def create_case(
        self,
        case_id: Optional[str] = None,
        title: str = "Untitled case",
        description: str = "",
        case_type: Optional[str] = None,
        case_status: Optional[str] = None,
        filing_date: Any = None,
        court_name: Optional[str] = None,
        next_hearing_date: Any = None,
    ) -> Dict[str, Any]:
        cid = case_id or f"CASE-{uuid4().hex[:8].upper()}"
        async with self._session() as session:
            existing = (
                await session.execute(
                    select(db_models.Case).where(
                        db_models.Case.case_number == cid,
                        db_models.Case.is_demo == self.demo,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return case_to_dict(existing)
            row = db_models.Case(
                case_number=cid,
                title=title,
                description=description,
                is_demo=self.demo,
                case_type=case_type,
                case_status=case_status or "OPEN",
                filing_date=_parse_date(filing_date),
                court_name=court_name,
                next_hearing_date=_parse_date(next_hearing_date),
            )
            session.add(row)
            await session.commit()
            self._case_dir(cid)
            return case_to_dict(row)

    async def get_case(self, case_id: str) -> Dict[str, Any]:
        async with self._session() as session:
            row = await self._case_row(session, case_id)
            return case_to_dict(row)

    async def ensure_case(
        self, case_id: str, title: str = "", description: str = ""
    ) -> Dict[str, Any]:
        async with self._session() as session:
            row = await self._case_row(session, case_id, create=True)
            if title and row.title != title:
                row.title = title
            if description and not row.description:
                row.description = description
            await session.commit()
            self._case_dir(case_id)
            return case_to_dict(row)

    async def update_case(self, case_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Patch case metadata. Keys absent from ``patch`` are left unchanged."""
        async with self._session() as session:
            row = await self._case_row(session, case_id)
            if "title" in patch and patch["title"] is not None:
                row.title = patch["title"]
            if "description" in patch and patch["description"] is not None:
                row.description = patch["description"]
            if "case_type" in patch:
                row.case_type = patch["case_type"]
            if "case_status" in patch and patch["case_status"] is not None:
                row.case_status = patch["case_status"]
            if "filing_date" in patch:
                row.filing_date = _parse_date(patch["filing_date"])
            if "court_name" in patch:
                row.court_name = patch["court_name"]
            if "next_hearing_date" in patch:
                row.next_hearing_date = _parse_date(patch["next_hearing_date"])
            await session.commit()
            return case_to_dict(row)

    async def delete_case_dir(self, case_id: str) -> None:
        async with self._session() as session:
            row = (
                await session.execute(
                    select(db_models.Case).where(
                        db_models.Case.case_number == case_id,
                        db_models.Case.is_demo == self.demo,
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                await session.delete(row)
                await session.commit()
        d = self.root / case_id
        if d.exists():
            shutil.rmtree(d)

    async def reset_all(self) -> None:
        """Wipe only this repository's scope (demo vs real) — DB rows + disk."""
        async with self._session() as session:
            await session.execute(
                delete(db_models.Case).where(db_models.Case.is_demo == self.demo)
            )
            await session.commit()
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- documents --

    async def append_document(self, case_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        async with self._session() as session:
            case = await self._case_row(session, case_id, create=True)
            self.stakeholder_dir(case_id, doc.get("source_type") or "unknown", doc.get("source") or doc.get("source_id") or "unknown")
            visibility = doc.get("visibility") or db_models.DocumentVisibility.INTERNAL
            if not isinstance(visibility, db_models.DocumentVisibility):
                visibility = db_models.DocumentVisibility(str(visibility))
            row = db_models.Document(
                document_id=_u(doc.get("document_id")) or uuid4(),
                case_id=case.id,
                source_id=doc.get("source_id") or doc.get("source") or "unknown",
                source_type=doc.get("source_type") or "unknown",
                title=doc.get("title") or "",
                text=doc.get("text") or "",
                ingestion_time=_parse_dt(doc.get("ingestion_time")),
                extractor=doc.get("extractor"),
                extractor_note=doc.get("extractor_note"),
                ocr=doc.get("ocr"),
                visibility=visibility,
            )
            session.add(row)
            await session.commit()
            return _document_to_dict(row, case.case_number)

    async def get_documents(self, case_id: str) -> List[Dict[str, Any]]:
        async with self._session() as session:
            case = await self._case_row(session, case_id, create=True)
            rows = (
                await session.execute(
                    select(db_models.Document)
                    .where(db_models.Document.case_id == case.id)
                    .order_by(db_models.Document.ingestion_time, db_models.Document.document_id)
                )
            ).scalars().all()
            return [_document_to_dict(r, case.case_number) for r in rows]

    async def get_document(self, case_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        docs = await self.get_documents(case_id)
        for d in docs:
            if d.get("document_id") == document_id:
                return d
        return None

    # -- observations (append-only) --

    async def append_observations(
        self, case_id: str, observations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        async with self._session() as session:
            case = await self._case_row(session, case_id, create=True)
            out: List[Dict[str, Any]] = []
            for o in observations:
                row = db_models.Observation(
                    observation_id=_u(o.get("observation_id")) or uuid4(),
                    case_id=case.id,
                    document_id=_u(o.get("document_id")),
                    fact_key=o["fact_key"],
                    value=o.get("value"),
                    source_id=o.get("source_id") or o.get("source") or "unknown",
                    source_type=o.get("source_type") or "unknown",
                    event_time=_parse_dt(o.get("event_time")),
                    ingestion_time=_parse_dt(o.get("ingestion_time")),
                    extraction_reliability=float(
                        o.get("extraction_reliability", o.get("extraction_confidence", 0.7))
                    ),
                    evidence=o.get("evidence") or "",
                    status=o.get("status") or "recorded",
                )
                session.add(row)
                out.append(_observation_to_dict(row, case.case_number))
            await session.commit()
            return out

    async def get_observations(
        self, case_id: str, fact_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        async with self._session() as session:
            case = await self._case_row(session, case_id, create=True)
            stmt = (
                select(db_models.Observation)
                .where(db_models.Observation.case_id == case.id)
                .order_by(db_models.Observation.ingestion_time, db_models.Observation.observation_id)
            )
            if fact_key is not None:
                stmt = stmt.where(db_models.Observation.fact_key == fact_key)
            rows = (await session.execute(stmt)).scalars().all()
            return [_observation_to_dict(r, case.case_number) for r in rows]

    # -- twin facts --

    async def get_facts(self, case_id: str) -> Dict[str, Any]:
        async with self._session() as session:
            case = await self._case_row(session, case_id, create=True)
            rows = (
                await session.execute(
                    select(db_models.TwinFact)
                    .where(db_models.TwinFact.case_id == case.id)
                    .order_by(db_models.TwinFact.fact_key)
                )
            ).scalars().all()
            return {r.fact_key: _fact_to_dict(r) for r in rows}

    async def set_fact(self, case_id: str, fact_key: str, fact: Dict[str, Any]) -> None:
        async with self._session() as session:
            case = await self._case_row(session, case_id, create=True)
            row = await session.get(db_models.TwinFact, (case.id, fact_key))
            if row is None:
                row = db_models.TwinFact(case_id=case.id, fact_key=fact_key)
                session.add(row)
            row.value = fact.get("value")
            row.status = fact.get("status") or "unresolved"
            row.confidence = fact.get("confidence")
            row.last_updated = _parse_dt(fact.get("last_updated"))
            row.supporting_observation_ids = fact.get("supporting_observation_ids") or []
            row.provenance = fact.get("provenance") or []
            await session.commit()

    async def get_fact_value(self, case_id: str, fact_key: str) -> Any:
        facts = await self.get_facts(case_id)
        f = facts.get(fact_key)
        if not f or f.get("status") != "resolved":
            return None
        return f.get("value")

    # -- history (append-only) --

    async def append_history(self, case_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        async with self._session() as session:
            case = await self._case_row(session, case_id, create=True)
            row = db_models.SyncHistory(
                history_id=_u(entry.get("history_id")) or uuid4(),
                case_id=case.id,
                fact_key=entry["fact_key"],
                timestamp=_parse_dt(entry.get("timestamp")),
                decision=entry.get("decision") or "",
                decided=bool(entry.get("decided")),
                selected_value=entry.get("selected_value"),
                previous_value=entry.get("previous_value"),
                unresolved=bool(entry.get("unresolved")),
                C1=entry.get("C1"),
                C2=entry.get("C2"),
                margin=entry.get("margin"),
                tau=entry.get("tau"),
                delta=entry.get("delta"),
                weights=entry.get("weights"),
                candidates=entry.get("candidates"),
                supporting_observation_ids=entry.get("supporting_observation_ids"),
                reason=entry.get("reason"),
                explanation=entry.get("explanation"),
                trigger_document_id=_u(entry.get("trigger_document_id")),
                trigger_observation_id=_u(entry.get("trigger_observation_id")),
            )
            session.add(row)
            await session.commit()
            return entry

    async def get_history(self, case_id: str) -> List[Dict[str, Any]]:
        async with self._session() as session:
            case = await self._case_row(session, case_id, create=True)
            rows = (
                await session.execute(
                    select(db_models.SyncHistory)
                    .where(db_models.SyncHistory.case_id == case.id)
                    .order_by(db_models.SyncHistory.seq)
                )
            ).scalars().all()
            return [_history_to_dict(r, case.case_number) for r in rows]

    # -- conflicts --

    async def get_conflicts(self, case_id: str) -> Dict[str, Any]:
        async with self._session() as session:
            case = await self._case_row(session, case_id, create=True)
            rows = (
                await session.execute(
                    select(db_models.Conflict)
                    .where(db_models.Conflict.case_id == case.id)
                    .order_by(db_models.Conflict.fact_key)
                )
            ).scalars().all()
            return {r.fact_key: _conflict_to_dict(r) for r in rows}

    async def set_conflict(self, case_id: str, fact_key: str, conflict: Dict[str, Any]) -> None:
        async with self._session() as session:
            case = await self._case_row(session, case_id, create=True)
            row = await session.get(db_models.Conflict, (case.id, fact_key))
            if row is None:
                row = db_models.Conflict(case_id=case.id, fact_key=fact_key)
                session.add(row)
            row.status = conflict.get("status") or "unresolved"
            row.reason = conflict.get("reason")
            row.explanation = conflict.get("explanation")
            row.previous_value = conflict.get("previous_value")
            row.C1 = conflict.get("C1")
            row.C2 = conflict.get("C2")
            row.margin = conflict.get("margin")
            row.candidates = conflict.get("candidates") or []
            row.updated_at = _parse_dt(conflict.get("updated_at"))
            await session.commit()

    async def clear_conflict(self, case_id: str, fact_key: str) -> None:
        async with self._session() as session:
            case = await self._case_row(session, case_id, create=True)
            await session.execute(
                delete(db_models.Conflict).where(
                    db_models.Conflict.case_id == case.id,
                    db_models.Conflict.fact_key == fact_key,
                )
            )
            await session.commit()

    # -- provenance (append-only audit rows; one per supporting observation) --

    async def append_provenance(
        self,
        case_id: str,
        fact_key: str,
        history_id: str,
        rows: List[Dict[str, Any]],
    ) -> None:
        if not rows:
            return
        async with self._session() as session:
            case = await self._case_row(session, case_id, create=True)
            for r in rows:
                session.add(
                    db_models.Provenance(
                        id=uuid4(),
                        case_id=case.id,
                        fact_key=fact_key,
                        history_id=_u(history_id),
                        observation_id=_u(r.get("observation_id")),
                        document_id=_u(r.get("document_id")),
                        source_id=r.get("source"),
                        source_type=r.get("source_type"),
                        value=r.get("value"),
                        evidence=r.get("evidence"),
                    )
                )
            await session.commit()

    # -- stakeholders (derived from documents + uploads) --

    async def list_stakeholders(self, case_id: str) -> List[Dict[str, Any]]:
        async with self._session() as session:
            case = await self._case_row(session, case_id, create=True)
            docs = (
                await session.execute(
                    select(
                        db_models.Document.source_type,
                        db_models.Document.source_id,
                        db_models.Document.ingestion_time,
                    ).where(db_models.Document.case_id == case.id)
                )
            ).all()
            uploads = (
                await session.execute(
                    select(db_models.Upload).where(db_models.Upload.case_id == case.id)
                )
            ).scalars().all()

            merged: Dict[str, Dict[str, Any]] = {}

            def entry(source_type: str, source_id: str) -> Dict[str, Any]:
                key = stakeholder_key(source_type, source_id)
                if key not in merged:
                    merged[key] = {
                        "stakeholder_key": key,
                        "source_type": source_type,
                        "source_id": source_id,
                        "created_at": None,
                        "document_files": [],
                    }
                return merged[key]

            for source_type, source_id, ing_time in docs:
                e = entry(source_type, source_id)
                if ing_time is not None and (
                    e["created_at"] is None or ing_time < e["created_at"]
                ):
                    e["created_at"] = ing_time
            for up in uploads:
                e = entry(up.source_type, up.source_id)
                if up.saved_at is not None and (
                    e["created_at"] is None or up.saved_at < e["created_at"]
                ):
                    e["created_at"] = up.saved_at
                if up.stored_filename:
                    e["document_files"].append(up.stored_filename)
                if up.extracted_text_path:
                    e["document_files"].append(Path(up.extracted_text_path).name)

            out = []
            for key in sorted(merged):
                e = merged[key]
                e["created_at"] = _iso(e["created_at"])
                e["document_files"] = sorted(set(e["document_files"]))
                out.append(e)
            return out

    # -- uploads (metadata in PostgreSQL; bytes on disk) --

    async def save_upload(
        self,
        case_id: str,
        source_type: str,
        source_id: str,
        filename: str,
        data: bytes,
        extracted_text: str = "",
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        meta = extra_meta or {}
        async with self._session() as session:
            case = await self._case_row(session, case_id, create=True)
            safe_name = _safe_segment(Path(filename).name, "upload.bin")
            uid = uuid4().hex[:10]
            stored_name = f"{uid}__{safe_name}"

            case_upload = self._case_dir(case_id) / "uploads" / stored_name
            case_upload.write_bytes(data)

            sh = self.stakeholder_dir(case_id, source_type, source_id)
            sh_doc = sh / "documents" / stored_name
            sh_doc.write_bytes(data)

            text_path: Optional[Path] = None
            if extracted_text:
                text_path = sh / "documents" / f"{uid}__extracted.txt"
                text_path.write_text(extracted_text, encoding="utf-8")

            row = db_models.Upload(
                upload_id=uuid4(),
                case_id=case.id,
                source_id=source_id,
                source_type=source_type,
                original_filename=filename,
                stored_filename=stored_name,
                case_upload_path=str(case_upload),
                stakeholder_path=str(sh_doc),
                extracted_text_path=str(text_path) if text_path else None,
                byte_size=len(data),
                ocr_method=meta.get("ocr_method"),
                ocr_note=meta.get("ocr_note"),
                saved_at=_utcnow(),
            )
            session.add(row)
            await session.commit()
            return _upload_to_dict(row)

    # -- citizen submissions (Task 3; PENDING until COURT review) --

    async def _load_submission(
        self, session: AsyncSession, submission_id: Optional[UUID]
    ) -> Optional[db_models.Submission]:
        if submission_id is None:
            return None
        return (
            await session.execute(
                select(db_models.Submission)
                .options(*_submission_options())
                .where(db_models.Submission.submission_id == submission_id)
            )
        ).scalar_one_or_none()

    async def create_submission(
        self,
        case_id: str,
        submitted_by: UUID,
        title: str,
        text: str,
    ) -> Dict[str, Any]:
        async with self._session() as session:
            case = await self._case_row(session, case_id)
            row = db_models.Submission(
                submission_id=uuid4(),
                case_id=case.id,
                submitted_by=submitted_by,
                title=title,
                text=text,
                status=db_models.SubmissionStatus.PENDING,
            )
            session.add(row)
            await session.commit()
            loaded = await self._load_submission(session, row.submission_id)
            return _submission_to_dict(loaded, case.case_number)

    async def list_submissions(
        self, case_id: str, submitted_by: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        async with self._session() as session:
            case = await self._case_row(session, case_id)
            stmt = (
                select(db_models.Submission)
                .options(*_submission_options())
                .where(db_models.Submission.case_id == case.id)
                .order_by(
                    db_models.Submission.created_at, db_models.Submission.submission_id
                )
            )
            if submitted_by is not None:
                stmt = stmt.where(db_models.Submission.submitted_by == submitted_by)
            rows = (await session.execute(stmt)).scalars().all()
            return [_submission_to_dict(r, case.case_number) for r in rows]

    async def get_submission(self, case_id: str, submission_id: str) -> Dict[str, Any]:
        async with self._session() as session:
            case = await self._case_row(session, case_id)
            row = await self._load_submission(session, _u(submission_id))
            if row is None or row.case_id != case.id:
                raise KeyError(f"submission not found: {submission_id}")
            return _submission_to_dict(row, case.case_number)

    async def decide_submission(
        self,
        case_id: str,
        submission_id: str,
        decision: str,
        reviewer_id: UUID,
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Atomically claim a PENDING submission (→ APPROVED / REJECTED).

        Returns None when the row exists but was already reviewed, so two
        concurrent reviewers cannot both act on the same submission.
        """
        target = (
            db_models.SubmissionStatus.APPROVED
            if decision.upper() == "APPROVE"
            else db_models.SubmissionStatus.REJECTED
        )
        async with self._session() as session:
            case = await self._case_row(session, case_id)
            sid = _u(submission_id)
            result = await session.execute(
                update(db_models.Submission)
                .where(
                    db_models.Submission.submission_id == sid,
                    db_models.Submission.case_id == case.id,
                    db_models.Submission.status == db_models.SubmissionStatus.PENDING,
                )
                .values(
                    status=target,
                    reviewed_by=reviewer_id,
                    reviewed_at=_utcnow(),
                    review_note=note,
                )
            )
            if result.rowcount == 0:
                row = await self._load_submission(session, sid)
                if row is None or row.case_id != case.id:
                    raise KeyError(f"submission not found: {submission_id}")
                return None
            await session.commit()
            loaded = await self._load_submission(session, sid)
            return _submission_to_dict(loaded, case.case_number)

    async def revert_submission(self, submission_id: str, note: Optional[str] = None) -> None:
        """Undo an APPROVED claim after a failed ingestion (→ PENDING)."""
        async with self._session() as session:
            await session.execute(
                update(db_models.Submission)
                .where(
                    db_models.Submission.submission_id == _u(submission_id),
                    db_models.Submission.status == db_models.SubmissionStatus.APPROVED,
                )
                .values(
                    status=db_models.SubmissionStatus.PENDING,
                    reviewed_by=None,
                    reviewed_at=None,
                    review_note=note,
                )
            )
            await session.commit()

    async def attach_submission_document(
        self, submission_id: str, document_id: str
    ) -> None:
        async with self._session() as session:
            await session.execute(
                update(db_models.Submission)
                .where(db_models.Submission.submission_id == _u(submission_id))
                .values(document_id=_u(document_id))
            )
            await session.commit()
