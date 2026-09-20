"""Shared fixtures: one asyncio loop for PostgreSQL-backed tests."""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-task2")
os.environ.setdefault("JWT_EXPIRE_MINUTES", "60")
os.environ.setdefault("DEV_SEED_PASSWORD", "NyayaOS-dev-2026!")

DATABASE_URL = os.getenv("DATABASE_URL")


def postgres_driver_ok() -> bool:
    try:
        from asyncpg.protocol import protocol  # noqa: F401

        return True
    except Exception:
        return False


async def _connect_once() -> None:
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def loop_runner():
    runner = asyncio.Runner()
    yield runner
    try:
        from db import engine as db_engine

        if db_engine is not None:
            runner.run(db_engine.dispose())
    except Exception:
        pass
    runner.close()


@pytest.fixture(scope="session")
def require_postgres(loop_runner):
    if not postgres_driver_ok():
        pytest.skip("asyncpg driver is not importable in this interpreter")
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not configured")
    try:
        loop_runner.run(asyncio.wait_for(_connect_once(), timeout=5))
    except Exception:
        pytest.skip("PostgreSQL server unreachable")


@pytest.fixture
def case_id() -> str:
    return f"T2-{uuid.uuid4().hex[:10].upper()}"
