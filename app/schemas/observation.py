"""OWNER: Person C — observation / twin / OCR request-response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SourceRole = Literal["police", "court", "lawyer", "forensic", "citizen", "admin"]


class ObservationCreate(BaseModel):
    case_id: str
    entity_id: str
    fact_name: str = Field(min_length=1, max_length=120)
    source_role: SourceRole
    candidate_value: dict[str, Any]
    event_time: datetime | None = None
    extraction_reliability: float | None = Field(default=None, ge=0.0, le=1.0)
    raw_source_ref: str | None = Field(default=None, max_length=255)


class SyncResultOut(BaseModel):
    decision: str
    c1: float
    c2: float | None
    explanation: str
    winner_observation_id: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)


class ObservationResponse(BaseModel):
    id: str
    fact_key_id: str
    case_id: str
    source_id: str
    source_role: str
    candidate_value: dict[str, Any]
    event_time: datetime | None
    ingestion_time: datetime
    extraction_reliability: float
    raw_source_ref: str | None
    status: str

    model_config = {"from_attributes": True}


class IngestResponse(BaseModel):
    observation: ObservationResponse
    sync: SyncResultOut
    twin_updated: bool


class TwinFactOut(BaseModel):
    fact_key_id: str
    fact_name: str | None = None
    entity_id: str | None = None
    current_value: dict[str, Any] | None
    confidence: float | None
    source_observation_id: str | None
    updated_at: datetime


class TwinStateOut(BaseModel):
    case_id: str
    facts: list[TwinFactOut]


class SyncDecisionOut(BaseModel):
    id: str
    fact_key_id: str
    timestamp: datetime
    winning_observation_id: str | None
    candidates_snapshot: dict[str, Any]
    c1: float
    c2: float | None
    tau: float
    delta: float
    decision: str
    explanation: str

    model_config = {"from_attributes": True}


class OCRIngestResponse(BaseModel):
    extracted_text_preview: str
    structured: dict[str, Any]
    ingest: IngestResponse
