"""
PostgreSQL models for NyayaOS (Task 1 auth foundation + Task 2 case data).

PostgreSQL is authoritative for ALL runtime case/CAMS structured data:
``users``, ``cases``, ``case_access``, ``documents``, ``observations``,
``twin_facts``, ``conflicts``, ``sync_history``, ``provenance``, ``uploads``.
Physical upload bytes stay on disk under data/cases|demo_cases.

The JSON FileRepository is no longer used at runtime (see db_repository.py);
old JSON files under data/ are kept on disk but never read by the app.

Login/JWT lives in security.py + auth.py; case-RBAC permission checks live in
rbac.py (capabilities, resource filtering, access management, submissions).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SystemRole(str, enum.Enum):
    ADMIN = "ADMIN"
    COURT = "COURT"
    POLICE = "POLICE"
    LAWYER = "LAWYER"
    FORENSIC = "FORENSIC"
    CITIZEN = "CITIZEN"


class AccessStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class DocumentVisibility(str, enum.Enum):
    INTERNAL = "INTERNAL"
    CITIZEN_VISIBLE = "CITIZEN_VISIBLE"


class SubmissionStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


system_role_enum = Enum(SystemRole, name="system_role", native_enum=True)
access_status_enum = Enum(AccessStatus, name="access_status", native_enum=True)
document_visibility_enum = Enum(
    DocumentVisibility, name="document_visibility", native_enum=True
)
submission_status_enum = Enum(SubmissionStatus, name="submission_status", native_enum=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    system_role: Mapped[SystemRole] = mapped_column(system_role_enum, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    case_access: Mapped[List["CaseAccess"]] = relationship(
        back_populates="user",
        foreign_keys="CaseAccess.user_id",
        cascade="all, delete-orphan",
    )
    granted_access: Mapped[List["CaseAccess"]] = relationship(
        back_populates="granted_by_user",
        foreign_keys="CaseAccess.granted_by",
    )


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        UniqueConstraint("case_number", "is_demo", name="uq_cases_case_number_demo"),
        Index("ix_cases_case_number", "case_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_number: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    case_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    case_status: Mapped[str] = mapped_column(String(64), nullable=False, default="OPEN")
    filing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    court_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    next_hearing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    access_entries: Mapped[List["CaseAccess"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )
    documents: Mapped[List["Document"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="Document.ingestion_time",
    )
    observations: Mapped[List["Observation"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="Observation.ingestion_time",
    )
    twin_facts: Mapped[List["TwinFact"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )
    conflicts: Mapped[List["Conflict"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )
    history_entries: Mapped[List["SyncHistory"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="SyncHistory.seq",
    )
    provenance_rows: Mapped[List["Provenance"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )
    uploads: Mapped[List["Upload"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )
    submissions: Mapped[List["Submission"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )


class CaseAccess(Base):
    __tablename__ = "case_access"
    __table_args__ = (
        UniqueConstraint("user_id", "case_id", name="uq_case_access_user_case"),
        Index("ix_case_access_case_status", "case_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_role: Mapped[SystemRole] = mapped_column(system_role_enum, nullable=False)
    status: Mapped[AccessStatus] = mapped_column(
        access_status_enum, nullable=False, default=AccessStatus.ACTIVE
    )
    granted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    user: Mapped[User] = relationship(back_populates="case_access", foreign_keys=[user_id])
    case: Mapped[Case] = relationship(
        back_populates="access_entries", foreign_keys=[case_id]
    )
    granted_by_user: Mapped[Optional[User]] = relationship(
        back_populates="granted_access", foreign_keys=[granted_by]
    )


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_case", "case_id"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, default="unknown")
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ingestion_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    extractor: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    extractor_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ocr: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    visibility: Mapped[DocumentVisibility] = mapped_column(
        document_visibility_enum, nullable=False, default=DocumentVisibility.INTERNAL
    )

    case: Mapped[Case] = relationship(back_populates="documents", foreign_keys=[case_id])
    observations: Mapped[List["Observation"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class Observation(Base):
    """Append-only: pipeline never updates or deletes observation rows."""

    __tablename__ = "observations"
    __table_args__ = (
        Index("ix_observations_case", "case_id"),
        Index("ix_observations_case_fact", "case_id", "fact_key"),
    )

    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.document_id", ondelete="SET NULL"),
        nullable=True,
    )
    fact_key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, default="unknown")
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    ingestion_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    extraction_reliability: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="recorded")

    case: Mapped[Case] = relationship(back_populates="observations", foreign_keys=[case_id])
    document: Mapped[Optional[Document]] = relationship(
        back_populates="observations", foreign_keys=[document_id]
    )


class TwinFact(Base):
    """Current Digital Twin state per fact (old facts.json)."""

    __tablename__ = "twin_facts"
    __table_args__ = (Index("ix_twin_facts_case", "case_id"),)

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        primary_key=True,
    )
    fact_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unresolved")
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    supporting_observation_ids: Mapped[Optional[List[Any]]] = mapped_column(
        JSONB, nullable=True
    )
    provenance: Mapped[Optional[List[Any]]] = mapped_column(JSONB, nullable=True)

    case: Mapped[Case] = relationship(back_populates="twin_facts", foreign_keys=[case_id])


class Conflict(Base):
    """Unresolved/abstained facts (old conflicts.json)."""

    __tablename__ = "conflicts"
    __table_args__ = (Index("ix_conflicts_case", "case_id"),)

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        primary_key=True,
    )
    fact_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unresolved")
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    previous_value: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    C1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    C2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    candidates: Mapped[Optional[List[Any]]] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    case: Mapped[Case] = relationship(back_populates="conflicts", foreign_keys=[case_id])


class SyncHistory(Base):
    """Append-only record of every CAMS decision (old history.json).

    ``seq`` (identity) gives deterministic insert ordering — UUIDs and
    timestamps alone do not.
    """

    __tablename__ = "sync_history"
    __table_args__ = (Index("ix_sync_history_case_seq", "case_id", "seq"),)

    history_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    fact_key: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    decided: Mapped[bool] = mapped_column(Boolean, nullable=False)
    selected_value: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    previous_value: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    unresolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    C1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    C2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tau: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delta: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weights: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    candidates: Mapped[Optional[List[Any]]] = mapped_column(JSONB, nullable=True)
    supporting_observation_ids: Mapped[Optional[List[Any]]] = mapped_column(
        JSONB, nullable=True
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trigger_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    trigger_observation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    case: Mapped[Case] = relationship(
        back_populates="history_entries", foreign_keys=[case_id]
    )


class Provenance(Base):
    """Append-only provenance rows — one per supporting observation per decision."""

    __tablename__ = "provenance"
    __table_args__ = (Index("ix_provenance_case_fact", "case_id", "fact_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    fact_key: Mapped[str] = mapped_column(String(128), nullable=False)
    history_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sync_history.history_id", ondelete="CASCADE"),
        nullable=True,
    )
    observation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("observations.observation_id", ondelete="SET NULL"),
        nullable=True,
    )
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    source_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    value: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    case: Mapped[Case] = relationship(
        back_populates="provenance_rows", foreign_keys=[case_id]
    )


class Upload(Base):
    """Metadata for every raw uploaded file (old uploads_index.json)."""

    __tablename__ = "uploads"
    __table_args__ = (Index("ix_uploads_case", "case_id"),)

    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, default="unknown")
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    stored_filename: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    case_upload_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stakeholder_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    extracted_text_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    byte_size: Mapped[int] = mapped_column("bytes", nullable=False, default=0)
    ocr_method: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ocr_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    case: Mapped[Case] = relationship(back_populates="uploads", foreign_keys=[case_id])


class Submission(Base):
    """Citizen submission workflow (Task 3).

    A citizen submits text for an assigned case; the row is PENDING until an
    assigned COURT user reviews it. Approval feeds the text through the normal
    extraction → observations → CAMS pipeline and links the created document;
    rejection leaves case/CAMS state untouched.
    """

    __tablename__ = "submissions"
    __table_args__ = (
        Index("ix_submissions_case_status", "case_id", "status"),
        Index("ix_submissions_submitted_by", "submitted_by"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[SubmissionStatus] = mapped_column(
        submission_status_enum, nullable=False, default=SubmissionStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.document_id", ondelete="SET NULL"),
        nullable=True,
    )

    case: Mapped[Case] = relationship(back_populates="submissions", foreign_keys=[case_id])
    submitter: Mapped[User] = relationship(foreign_keys=[submitted_by])
    reviewer: Mapped[Optional[User]] = relationship(foreign_keys=[reviewed_by])
