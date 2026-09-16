"""OWNER: Person C (schema) / Person B (seed values + usage in factors.py)"""
from __future__ import annotations

import uuid

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SourceAuthorityRule(Base):
    __tablename__ = "source_authority_rules"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    fact_type: Mapped[str] = mapped_column(String(120))
    source_role: Mapped[str] = mapped_column(String(20))
    authority_score: Mapped[float] = mapped_column(Float)


class CAMSConfig(Base):
    __tablename__ = "cams_config"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str | None] = mapped_column(String, nullable=True)  # null = global
    weight_authority: Mapped[float] = mapped_column(Float, default=0.3)
    weight_temporal: Mapped[float] = mapped_column(Float, default=0.3)
    weight_corroboration: Mapped[float] = mapped_column(Float, default=0.2)
    weight_extraction: Mapped[float] = mapped_column(Float, default=0.2)
    tau: Mapped[float] = mapped_column(Float, default=0.6)
    delta: Mapped[float] = mapped_column(Float, default=0.1)
    is_active: Mapped[bool] = mapped_column(default=True)
