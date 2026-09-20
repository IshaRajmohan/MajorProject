"""PostgreSQL foundation checks (auth tables + Task 2 case/CAMS tables).

Skipped when DATABASE_URL is unset or the server is unreachable.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

DATABASE_URL = os.getenv("DATABASE_URL")

pytestmark = pytest.mark.usefixtures("require_postgres")


def test_database_url_configured():
    assert DATABASE_URL.startswith("postgresql+asyncpg://")


def test_connectivity_select_one(loop_runner):
    async def check():
        engine = create_async_engine(DATABASE_URL)
        try:
            async with engine.connect() as conn:
                return (await conn.execute(text("SELECT 1"))).scalar_one()
        finally:
            await engine.dispose()

    assert loop_runner.run(check()) == 1


def test_schema_tables_exist(loop_runner):
    async def check():
        engine = create_async_engine(DATABASE_URL)
        try:
            async with engine.connect() as conn:
                rows = (
                    await conn.execute(
                        text(
                            "SELECT tablename FROM pg_tables "
                            "WHERE schemaname='public' ORDER BY 1"
                        )
                    )
                ).scalars()
                return set(rows)
        finally:
            await engine.dispose()

    tables = loop_runner.run(check())
    assert {
        "users",
        "cases",
        "case_access",
        "documents",
        "observations",
        "twin_facts",
        "conflicts",
        "sync_history",
        "provenance",
        "uploads",
        "alembic_version",
    } <= tables


def test_enums_exist(loop_runner):
    async def check():
        engine = create_async_engine(DATABASE_URL)
        try:
            async with engine.connect() as conn:
                rows = (
                    await conn.execute(
                        text(
                            "SELECT typname FROM pg_type WHERE typname "
                            "IN ('system_role', 'access_status')"
                        )
                    )
                ).scalars()
                return set(rows)
        finally:
            await engine.dispose()

    assert loop_runner.run(check()) == {"system_role", "access_status"}


def test_constraints_exist(loop_runner):
    async def check():
        engine = create_async_engine(DATABASE_URL)
        try:
            async with engine.connect() as conn:
                rows = (
                    await conn.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE connamespace='public'::regnamespace "
                            "AND contype IN ('u', 'f')"
                        )
                    )
                ).scalars()
                return set(rows)
        finally:
            await engine.dispose()

    constraints = loop_runner.run(check())
    assert "uq_case_access_user_case" in constraints
    assert {
        "case_access_user_id_fkey",
        "case_access_case_id_fkey",
        "case_access_granted_by_fkey",
    } <= constraints


def test_unique_indexes_exist(loop_runner):
    async def check():
        engine = create_async_engine(DATABASE_URL)
        try:
            async with engine.connect() as conn:
                rows = (
                    await conn.execute(
                        text("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
                    )
                ).scalars()
                return set(rows)
        finally:
            await engine.dispose()

    indexes = loop_runner.run(check())
    assert "ix_users_email" in indexes
    assert "ix_cases_case_number" in indexes
    assert "ix_case_access_case_status" in indexes


def test_get_db_yields_session(loop_runner):
    """The FastAPI dependency opens a real AsyncSession against the DB."""
    from db import AsyncSessionLocal

    assert AsyncSessionLocal is not None, "db.AsyncSessionLocal not built"

    async def check():
        async with AsyncSessionLocal() as session:
            assert isinstance(session, AsyncSession)
            return (await session.execute(text("SELECT 1"))).scalar_one()

    assert loop_runner.run(check()) == 1


def test_roundtrip_user_case_access(loop_runner):
    """Insert a user, a case, and a grant; clean up afterwards."""
    from db import AsyncSessionLocal
    from db_models import AccessStatus, Case, CaseAccess, SystemRole, User

    uid = uuid.uuid4()
    cid = uuid.uuid4()

    async def check():
        async with AsyncSessionLocal() as session:
            session.add_all(
                [
                    User(
                        id=uid,
                        email=f"task1-test-{uid.hex[:8]}@example.com",
                        password_hash="not-a-real-hash",
                        system_role=SystemRole.COURT,
                    ),
                    Case(
                        id=cid,
                        case_number=f"TASK1-{uid.hex[:8].upper()}",
                        title="Task 1 roundtrip",
                    ),
                    CaseAccess(
                        user_id=uid,
                        case_id=cid,
                        case_role=SystemRole.LAWYER,
                        status=AccessStatus.ACTIVE,
                        granted_by=uid,
                    ),
                ]
            )
            await session.commit()
        async with AsyncSessionLocal() as session:
            fetched = (
                await session.execute(
                    text(
                        "SELECT case_role, status FROM case_access "
                        "WHERE user_id = :u AND case_id = :c"
                    ),
                    {"u": uid, "c": cid},
                )
            ).one()
            assert fetched.case_role == "LAWYER"
            assert fetched.status == "ACTIVE"
            await session.execute(text("DELETE FROM case_access WHERE user_id = :u"), {"u": uid})
            await session.execute(text("DELETE FROM cases WHERE id = :c"), {"c": cid})
            await session.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
            await session.commit()
        return True

    assert loop_runner.run(check()) is True
