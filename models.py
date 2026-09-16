"""Pydantic models for nyayaos-lite observations and CAMS decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
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


class ObservationIn(BaseModel):
    """Request body for ingesting an observation (case_id comes from path)."""

    fact_key: str
    value: Any
    source_id: str
    source_type: str
    event_time: datetime
    ingestion_time: Optional[datetime] = None
    extraction_reliability: float = Field(ge=0.0, le=1.0, default=0.8)


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
