"""
OWNER: Person C
Append-only observation layer + fact_key + twin state + audit trail.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class FactKey(Base):
    __tablename__ = "fact_keys"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(String, index=True)
    entity_id: Mapped[str] = mapped_column(String, index=True)
    fact_name: Mapped[str] = mapped_column(String(120))


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    fact_key_id: Mapped[str] = mapped_column(String, index=True)
    case_id: Mapped[str] = mapped_column(String, index=True)
    source_id: Mapped[str] = mapped_column(String)
    source_role: Mapped[str] = mapped_column(String(20))
    candidate_value: Mapped[dict] = mapped_column(JSON)
    event_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ingestion_time: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    extraction_reliability: Mapped[float] = mapped_column(Float, default=1.0)
    raw_source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")


class TwinState(Base):
    __tablename__ = "twin_state"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(String, index=True)
    fact_key_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    current_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_observation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class SyncDecision(Base):
    __tablename__ = "sync_decisions"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    fact_key_id: Mapped[str] = mapped_column(String, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    winning_observation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    candidates_snapshot: Mapped[dict] = mapped_column(JSON)
    c1: Mapped[float] = mapped_column(Float)
    c2: Mapped[float | None] = mapped_column(Float, nullable=True)
    tau: Mapped[float] = mapped_column(Float)
    delta: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(20))
    explanation: Mapped[str] = mapped_column(String(255))
