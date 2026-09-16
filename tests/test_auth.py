"""OWNER: Person A — auth API tests."""
import pytest
from httpx import AsyncClient

from app.models.user import User
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, admin_user: User):
    resp = await client.post(
        "/auth/login",
        data={"username": "admin@example.com", "password": "AdminPass123!"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, admin_user: User):
    resp = await client.post(
        "/auth/login",
        data={"username": "admin@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user_without_password(client: AsyncClient, admin_user: User):
    resp = await client.get("/auth/me", headers=auth_header(admin_user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "admin@example.com"
    assert body["role"] == "admin"
    assert "password" not in body
    assert "hashed_password" not in body


@pytest.mark.asyncio
async def test_register_admin_only(
    client: AsyncClient, admin_user: User, citizen_user: User
):
    payload = {
        "name": "New Lawyer",
        "email": "new.lawyer@example.com",
        "password": "LawyerPass123!",
        "role": "lawyer",
        "org": "Bar Assoc",
    }
    forbidden = await client.post(
        "/auth/register", json=payload, headers=auth_header(citizen_user)
    )
    assert forbidden.status_code == 403

    created = await client.post(
        "/auth/register", json=payload, headers=auth_header(admin_user)
    )
    assert created.status_code == 201
    body = created.json()
    assert body["email"] == "new.lawyer@example.com"
    assert body["role"] == "lawyer"
    assert "hashed_password" not in body
    assert "password" not in body


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, admin_user: User):
    payload = {
        "name": "Dup",
        "email": "admin@example.com",
        "password": "AnotherPass123!",
        "role": "police",
    }
    resp = await client.post(
        "/auth/register", json=payload, headers=auth_header(admin_user)
    )
    assert resp.status_code == 409
