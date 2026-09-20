"""
Async PostgreSQL foundation for NyayaOS (auth + all runtime case/CAMS state).

Scope: connection plumbing — async engine, session factory, declarative Base,
and the FastAPI ``get_db()`` dependency. ORM models live in ``db_models.py``.

PostgreSQL is authoritative for users and all structured case data. The JSON
FileRepository is not used at runtime. Physical upload bytes stay on disk.

DATABASE_URL comes from the environment or a local ``.env`` file, e.g.:
    postgresql+asyncpg://user:password@localhost:5432/nyayaos_rbac
It is never hardcoded. Importing this module without DATABASE_URL is allowed;
a clear error is raised when a session is requested (no JSON fallback).
"""

from __future__ import annotations

import os
from typing import AsyncGenerator, Optional

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")


class Base(DeclarativeBase):
    """Declarative base for all PostgreSQL-backed models (see db_models.py)."""


def _engine_url() -> str:
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set it in .env, e.g. "
            "postgresql+asyncpg://user:password@localhost:5432/nyayaos_rbac"
        )
    return DATABASE_URL


# The engine connects lazily (no connection is opened here), so importing this
# module never requires a running PostgreSQL server.
engine: Optional[AsyncEngine] = (
    create_async_engine(_engine_url(), pool_pre_ping=True) if DATABASE_URL else None
)

AsyncSessionLocal: Optional[async_sessionmaker[AsyncSession]] = (
    async_sessionmaker(engine, expire_on_commit=False) if engine is not None else None
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a request-scoped async session."""
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "DATABASE_URL is not configured; cannot open a database session."
        )
    async with AsyncSessionLocal() as session:
        yield session
