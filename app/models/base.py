"""
OWNER: Person A
Shared declarative base — everyone's models import from here.
"""
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
