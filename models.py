"""Pydantic models for nyayaos-lite observations and CAMS decisions."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Observation(BaseModel):
    case_id: str
    fact_key: str
    value: Any
    source_id: str
    source_type: str
    event_time: datetime
    ingestion_time: datetime = Field(default_factory=_utcnow)
    extraction_reliability: float = Field(ge=0.0, le=1.0)
    observation_id: str = Field(default_factory=lambda: str(uuid4()))
    # Persistence / provenance fields (ignored by CAMS math except reliability)
    evidence: str = ""
    status: str = "recorded"
    document_id: Optional[str] = None


class ObservationIn(BaseModel):
    """Request body for ingesting an observation (case_id comes from path)."""

    fact_key: str
    value: Any
    source_id: str
    source_type: str
    event_time: datetime
    ingestion_time: Optional[datetime] = None
    extraction_reliability: float = Field(ge=0.0, le=1.0, default=0.8)
    evidence: str = ""


class TextIn(BaseModel):
    """Plain text submission for Gemini extraction + CAMS pipeline.

    ``source`` / ``source_type`` are accepted for dashboard compatibility but
    IGNORED: the RBAC layer derives both from the caller's system role and
    case_role (see rbac.source_type_for). ``visibility`` is honoured only for
    COURT assignees (CITIZEN_VISIBLE); everyone else always gets INTERNAL.
    """

    text: str
    source: Optional[str] = None
    source_type: Optional[str] = None
    title: Optional[str] = None
    force_fallback: bool = False
    visibility: Optional[str] = None


class FactorBreakdown(BaseModel):
    source_authority: float
    temporal_consistency: float
    cross_source_corroboration: float
    extraction_reliability: float
    confidence: float


class CandidateScore(BaseModel):
    value: Any
    confidence: float
    factors: FactorBreakdown
    supporting_observation_ids: List[str]
    supporting_source_ids: List[str]


class DecisionResult(BaseModel):
    case_id: str
    fact_key: str
    decided: bool
    accepted_value: Optional[Any] = None
    previous_value: Optional[Any] = None
    unresolved: bool
    C1: Optional[float] = None
    C2: Optional[float] = None
    margin: Optional[float] = None
    tau: float
    delta: float
    candidates: List[CandidateScore]
    message: str


class FactState(BaseModel):
    fact_key: str
    value: Optional[Any] = None
    confidence: Optional[float] = None
    resolved: bool = False
    last_updated: Optional[datetime] = None
    supporting_observation_ids: List[str] = Field(default_factory=list)


class CaseState(BaseModel):
    case_id: str
    facts: Dict[str, FactState] = Field(default_factory=dict)


# --- End-to-end pipeline models (additive; does not alter CAMS Observation) ---


class CaseCreate(BaseModel):
    case_id: Optional[str] = None
    title: str = "Untitled case"
    description: str = ""
    case_type: Optional[str] = None
    case_status: Optional[str] = None
    filing_date: Optional[date] = None
    court_name: Optional[str] = None
    next_hearing_date: Optional[date] = None


class CasePatch(BaseModel):
    """Basic case metadata edit (COURT assignees / ADMIN)."""

    title: Optional[str] = None
    description: Optional[str] = None
    case_type: Optional[str] = None
    case_status: Optional[str] = None
    filing_date: Optional[date] = None
    court_name: Optional[str] = None
    next_hearing_date: Optional[date] = None


class AccessGrantIn(BaseModel):
    email: str
    case_role: str


class SubmissionCreate(BaseModel):
    """Citizen submission body. Text only: no extraction happens until review."""

    title: str = ""
    text: str


class SubmissionReviewIn(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    note: Optional[str] = None
    force_fallback: bool = False


class CaseMeta(BaseModel):
    case_id: str
    title: str = "Untitled case"
    description: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class DocumentIn(BaseModel):
    source_id: str
    source_type: str
    text: str
    title: Optional[str] = None
    event_time: Optional[datetime] = None
    extraction_reliability: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class DocumentRecord(BaseModel):
    document_id: str = Field(default_factory=lambda: str(uuid4()))
    case_id: str
    source_id: str
    source_type: str
    title: str = ""
    raw_text: str
    cleaned_text: str = ""
    event_time: Optional[datetime] = None
    ingestion_time: datetime = Field(default_factory=_utcnow)
    extraction_reliability: float = 0.8


class ExtractedFact(BaseModel):
    fact_key: str
    value: Any
    event_time: Optional[datetime] = None
    confidence: float = 0.8
    evidence_span: str = ""


class SyncHistoryEntry(BaseModel):
    history_id: str = Field(default_factory=lambda: str(uuid4()))
    case_id: str
    fact_key: str
    timestamp: datetime = Field(default_factory=_utcnow)
    decided: bool
    selected_value: Optional[Any] = None
    previous_value: Optional[Any] = None
    unresolved: bool
    C1: Optional[float] = None
    C2: Optional[float] = None
    margin: Optional[float] = None
    tau: float
    delta: float
    message: str
    supporting_observation_ids: List[str] = Field(default_factory=list)
    candidates: List[CandidateScore] = Field(default_factory=list)
    trigger_observation_id: Optional[str] = None
    trigger_document_id: Optional[str] = None
