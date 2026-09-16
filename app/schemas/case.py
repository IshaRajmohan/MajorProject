"""OWNER: Person A"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

CaseStatus = Literal["open", "closed", "archived", "pending"]
EntityType = Literal["person", "evidence", "hearing", "order", "document"]


class CaseCreate(BaseModel):
    case_number: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=255)
    status: CaseStatus = "open"


class CaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    status: CaseStatus | None = None


class CaseResponse(BaseModel):
    id: str
    case_number: str
    title: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class EntityCreate(BaseModel):
    entity_type: EntityType
    label: str = Field(min_length=1, max_length=255)
    attributes: dict[str, Any] = Field(default_factory=dict)


class EntityResponse(BaseModel):
    id: str
    case_id: str
    entity_type: str
    label: str
    attributes: dict[str, Any]

    model_config = {"from_attributes": True}
