"""Shared fixtures: one asyncio loop for PostgreSQL-backed tests."""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, Dict, Optional

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-task2")
os.environ.setdefault("JWT_EXPIRE_MINUTES", "60")
os.environ.setdefault("DEV_SEED_PASSWORD", "NyayaOS-dev-2026!")

DATABASE_URL = os.getenv("DATABASE_URL")
DEV_SEED_PASSWORD = os.getenv("DEV_SEED_PASSWORD") or "NyayaOS-dev-2026!"


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


@pytest.fixture(scope="session")
def seed_users(require_postgres, loop_runner) -> Dict[str, str]:
    """Ensure the six dev accounts exist; returns {RoleName: email}."""
    from seed import SEED_USERS, seed_dev_users

    loop_runner.run(seed_dev_users())
    return {role: email for email, role in SEED_USERS}


@pytest.fixture
def pg_repo(require_postgres, tmp_path):
    from db_repository import DbRepository

    return DbRepository(demo=False, root=tmp_path / "cases")


@pytest.fixture
def pg_demo_repo(require_postgres, tmp_path):
    from db_repository import DbRepository

    return DbRepository(demo=True, root=tmp_path / "demo_cases")


class ApiClient:
    """ASGI test client: one event loop, optional auth headers."""

    def __init__(self, runner) -> None:
        self._runner = runner

    def request(
        self, method: str, url: str, headers: Optional[Dict[str, str]] = None, **kwargs: Any
    ):
        import main as main_mod
        from httpx import ASGITransport, AsyncClient

        async def _do():
            transport = ASGITransport(app=main_mod.app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                return await getattr(ac, method)(url, headers=headers, **kwargs)

        return self._runner.run(_do())

    def get(self, url: str, headers=None, **kwargs: Any):
        return self.request("get", url, headers=headers, **kwargs)

    def post(self, url: str, headers=None, **kwargs: Any):
        return self.request("post", url, headers=headers, **kwargs)

    def patch(self, url: str, headers=None, **kwargs: Any):
        return self.request("patch", url, headers=headers, **kwargs)

    def delete(self, url: str, headers=None, **kwargs: Any):
        return self.request("delete", url, headers=headers, **kwargs)


@pytest.fixture
def client(require_postgres, loop_runner, pg_repo, pg_demo_repo, monkeypatch) -> ApiClient:
    import main as main_mod
    from pipeline import Pipeline

    monkeypatch.setattr(main_mod, "repo", pg_repo)
    monkeypatch.setattr(main_mod, "pipeline", Pipeline(repository=pg_repo))
    monkeypatch.setattr(main_mod, "demo_repo", pg_demo_repo)
    monkeypatch.setattr(main_mod, "demo_pipeline", Pipeline(repository=pg_demo_repo))
    return ApiClient(loop_runner)


@pytest.fixture
def auth(client: ApiClient, seed_users: Dict[str, str]):
    """auth("COURT") → {"Authorization": "Bearer <real /auth/login token>"}."""
    cache: Dict[str, Dict[str, str]] = {}

    def _auth(role: str) -> Dict[str, str]:
        key = role.upper()
        if key not in cache:
            r = client.post(
                "/auth/login",
                json={"email": seed_users[key], "password": DEV_SEED_PASSWORD},
            )
            assert r.status_code == 200, r.text
            cache[key] = {"Authorization": f"Bearer {r.json()['access_token']}"}
        return cache[key]

    return _auth


@pytest.fixture
def login_as(client: ApiClient):
    """login_as("someone@example.com") → Bearer header dict (for non-seed users)."""

    def _login(email: str, password: Optional[str] = None) -> Dict[str, str]:
        r = client.post(
            "/auth/login", json={"email": email, "password": password or DEV_SEED_PASSWORD}
        )
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _login
