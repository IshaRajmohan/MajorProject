"""
OWNER: Person C
Append-only observation layer + fact_key + twin state + ODFS versions + audit trail.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class FactKey(Base):
    __tablename__ = "fact_keys"
    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "entity_id",
            "fact_name",
            name="uq_fact_keys_case_entity_name",
        ),
    )

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
    """Current Justice Twin pointer for one fact (latest ODFS version)."""

    __tablename__ = "twin_state"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(String, index=True)
    fact_key_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    current_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_observation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class TwinStateVersion(Base):
    """ODFS-style append-only versioned fact store. History is never overwritten."""

    __tablename__ = "twin_state_versions"
    __table_args__ = (
        UniqueConstraint("fact_key_id", "version", name="uq_twin_versions_fact_version"),
    )

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    twin_state_id: Mapped[str] = mapped_column(String, index=True)
    fact_key_id: Mapped[str] = mapped_column(String, index=True)
    case_id: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[int] = mapped_column(Integer)
    value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_observation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    sync_decision_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


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
