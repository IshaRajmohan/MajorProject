"""
OWNER: Person A + Person B
Shared pytest fixtures. Auth/case tests use in-memory SQLite.
CAMS tests need no DB.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.base import Base
from app.models.case import Case, Entity  # noqa: F401 — register metadata
from app.models.observation import (  # noqa: F401 — register metadata
    FactKey,
    Observation,
    SyncDecision,
    TwinState,
    TwinStateVersion,
)
from app.models.source_authority import CAMSConfig, SourceAuthorityRule  # noqa: F401
from app.models.user import User
from main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _create_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    role: str,
    name: str = "Test User",
) -> User:
    user = User(
        name=name,
        email=email.lower(),
        hashed_password=hash_password(password),
        role=role,
        org="Test Org",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    return await _create_user(
        db_session,
        email="admin@example.com",
        password="AdminPass123!",
        role="admin",
        name="Admin",
    )


@pytest_asyncio.fixture
async def police_user(db_session: AsyncSession) -> User:
    return await _create_user(
        db_session,
        email="police@example.com",
        password="PolicePass123!",
        role="police",
        name="Police",
    )


@pytest_asyncio.fixture
async def court_user(db_session: AsyncSession) -> User:
    return await _create_user(
        db_session,
        email="court@example.com",
        password="CourtPass123!",
        role="court",
        name="Court",
    )


@pytest_asyncio.fixture
async def lawyer_user(db_session: AsyncSession) -> User:
    return await _create_user(
        db_session,
        email="lawyer@example.com",
        password="LawyerPass123!",
        role="lawyer",
        name="Lawyer",
    )


@pytest_asyncio.fixture
async def forensic_user(db_session: AsyncSession) -> User:
    return await _create_user(
        db_session,
        email="forensic@example.com",
        password="ForensicPass123!",
        role="forensic",
        name="Forensic",
    )


@pytest_asyncio.fixture
async def citizen_user(db_session: AsyncSession) -> User:
    return await _create_user(
        db_session,
        email="citizen@example.com",
        password="CitizenPass123!",
        role="citizen",
        name="Citizen",
    )


def auth_header(user: User) -> dict[str, str]:
    token = create_access_token({"sub": user.id, "role": user.role})
    return {"Authorization": f"Bearer {token}"}
