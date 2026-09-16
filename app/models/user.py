"""
OWNER: Person A
Roles: police | court | lawyer | forensic | citizen | admin
"""
import uuid
from sqlalchemy import String, Enum
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(120), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # police|court|lawyer|forensic|citizen|admin
    org: Mapped[str] = mapped_column(String(120), nullable=True)
