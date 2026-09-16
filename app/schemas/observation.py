"""OWNER: Person C"""
from datetime import datetime
from pydantic import BaseModel

class ObservationCreate(BaseModel):
    case_id: str
    entity_id: str
    fact_name: str
    source_role: str
    candidate_value: dict
    event_time: datetime | None = None
    extraction_reliability: float | None = None
    raw_source_ref: str | None = None

class SyncResultOut(BaseModel):
    decision: str
    c1: float
    c2: float | None
    explanation: str
