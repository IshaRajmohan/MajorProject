"""Auth: login, JWT, /auth/me, invalid credentials, inactive user, seed roles."""

from __future__ import annotations

import uuid

from seed import SEED_USERS, seed_password
from security import hash_password, verify_password


def test_password_hash_not_plaintext():
    raw = "NyayaOS-dev-2026!"
    hashed = hash_password(raw)
    assert hashed != raw
    assert verify_password(raw, hashed)
    assert not verify_password("wrong", hashed)


def test_login_jwt_me_and_seeded_roles(require_postgres, loop_runner):
    from httpx import ASGITransport, AsyncClient
    import main as main_mod
    from seed import seed_dev_users

    async def run():
        await seed_dev_users()
        transport = ASGITransport(app=main_mod.app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            password = seed_password()
            roles = {}
            for email, role in SEED_USERS:
                r = await ac.post("/auth/login", json={"email": email, "password": password})
                assert r.status_code == 200, r.text
                body = r.json()
                assert "access_token" in body
                assert body["token_type"] == "bearer"
                assert "password_hash" not in body
                me = await ac.get(
                    "/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
                )
                assert me.status_code == 200, me.text
                data = me.json()
                assert data["email"] == email
                assert data["system_role"] == role
                assert data["is_active"] is True
                assert "password_hash" not in data
                assert "password" not in data
                roles[email] = data["system_role"]
            assert set(roles.values()) == {r for _, r in SEED_USERS}

            bad = await ac.post(
                "/auth/login", json={"email": "admin@nyayaos.dev", "password": "wrong-password"}
            )
            assert bad.status_code == 401
            assert bad.json()["detail"] == "Invalid credentials"

            missing = await ac.post(
                "/auth/login",
                json={"email": "nobody@nyayaos.dev", "password": password},
            )
            assert missing.status_code == 401
            assert missing.json()["detail"] == "Invalid credentials"

            unauth = await ac.get("/auth/me")
            assert unauth.status_code == 401

            garbage = await ac.get(
                "/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
            )
            assert garbage.status_code == 401

    loop_runner.run(run())


def test_inactive_user_cannot_authenticate(require_postgres, loop_runner):
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select
    import main as main_mod
    from db import AsyncSessionLocal
    from db_models import SystemRole, User

    email = f"inactive-{uuid.uuid4().hex[:8]}@nyayaos.dev"
    password = "Inactive-dev-2026!"

    async def run():
        async with AsyncSessionLocal() as session:
            session.add(
                User(
                    email=email,
                    password_hash=hash_password(password),
                    system_role=SystemRole.CITIZEN,
                    is_active=False,
                )
            )
            await session.commit()
        try:
            transport = ASGITransport(app=main_mod.app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                r = await ac.post("/auth/login", json={"email": email, "password": password})
                assert r.status_code == 401
                assert r.json()["detail"] == "Invalid credentials"
        finally:
            async with AsyncSessionLocal() as session:
                row = (
                    await session.execute(select(User).where(User.email == email))
                ).scalar_one_or_none()
                if row is not None:
                    await session.delete(row)
                    await session.commit()

    loop_runner.run(run())


def test_seed_is_idempotent(require_postgres, loop_runner):
    from sqlalchemy import select
    from db import AsyncSessionLocal
    from db_models import User
    from seed import seed_dev_users

    async def run():
        await seed_dev_users()
        n2 = await seed_dev_users()
        assert n2 == 0
        async with AsyncSessionLocal() as session:
            emails = set(
                (
                    await session.execute(
                        select(User.email).where(
                            User.email.in_([e for e, _ in SEED_USERS])
                        )
                    )
                ).scalars()
            )
        assert emails == {e for e, _ in SEED_USERS}

    loop_runner.run(run())
