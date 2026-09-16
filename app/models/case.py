"""
OWNER: Person A
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base

# JSONB on PostgreSQL; plain JSON elsewhere (e.g. SQLite tests)
JSONBCompat = JSON().with_variant(JSONB(), "postgresql")


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    case_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    entities: Mapped[list["Entity"]] = relationship(back_populates="case", cascade="all, delete-orphan")


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(30))  # person|evidence|hearing|order|document
    label: Mapped[str] = mapped_column(String(255))
    attributes: Mapped[dict] = mapped_column(JSONBCompat, default=dict)

    case: Mapped["Case"] = relationship(back_populates="entities")
