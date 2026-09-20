"""Task 4 — ADMIN user management (users_api.py).

Covers: 403 for every non-ADMIN role, 401 without a token, no password
material in any response, duplicate/invalid input handling, deactivation
kills login + already-issued tokens, password reset changes login, and the
invariant that /users cannot grant case access (case_access stays the only
way in, enforced by rbac.py).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict

import pytest

pytestmark = pytest.mark.usefixtures("require_postgres")

NON_ADMIN_ROLES = ("COURT", "POLICE", "LAWYER", "FORENSIC", "CITIZEN")
PASSWORD = "Task4-pass-2026!"
USER_PUBLIC_KEYS = {"id", "email", "system_role", "is_active", "created_at"}


# ---- helpers ----


def _uniq_email(prefix: str = "t4user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@nyayaos.dev"


def _create_user(
    client, admin: Dict[str, str], *, role: str = "POLICE", email: str = "", password: str = PASSWORD
) -> Dict[str, Any]:
    email = email or _uniq_email()
    r = client.post(
        "/users",
        json={"email": email, "password": password, "system_role": role},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return {"email": email, "password": password, "user": r.json()["user"]}


def _login_header(client, created: Dict[str, Any], password: str = "") -> Dict[str, str]:
    r = client.post(
        "/auth/login",
        json={"email": created["email"], "password": password or created["password"]},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _password_key_hits(text: str) -> list:
    low = text.lower()
    return [line for line in low.splitlines() if "password" in line]


# ---- authorization ----


def test_users_list_requires_admin(client, auth):
    assert client.get("/users").status_code == 401
    for role in NON_ADMIN_ROLES:
        assert client.get("/users", headers=auth(role)).status_code == 403


def test_non_admin_cannot_create_or_patch_users(client, auth):
    admin = auth("ADMIN")
    denied_email = _uniq_email("t4denied")
    payload = {"email": denied_email, "password": PASSWORD, "system_role": "POLICE"}
    for role in NON_ADMIN_ROLES:
        r = client.post("/users", json=payload, headers=auth(role))
        assert r.status_code == 403, (role, r.text)
    assert denied_email not in {
        u["email"] for u in client.get("/users", headers=admin).json()["users"]
    }

    target = _create_user(client, admin, role="POLICE")
    for role in NON_ADMIN_ROLES:
        r = client.patch(
            f"/users/{target['user']['id']}", json={"is_active": False}, headers=auth(role)
        )
        assert r.status_code == 403, (role, r.text)
    # still usable after the denied PATCH attempts
    assert client.post(
        "/auth/login", json={"email": target["email"], "password": PASSWORD}
    ).status_code == 200


# ---- listing / response shape ----


def test_admin_list_users_is_hash_free(client, auth, seed_users):
    r = client.get("/users", headers=auth("ADMIN"))
    assert r.status_code == 200, r.text
    users = r.json()["users"]
    emails = {u["email"] for u in users}
    for email in seed_users.values():
        assert email in emails
    for u in users:
        assert set(u) == USER_PUBLIC_KEYS
    assert _password_key_hits(r.text) == []


# ---- create ----


def test_admin_creates_user_who_can_log_in(client, auth):
    admin = auth("ADMIN")
    created = _create_user(client, admin, role="POLICE")
    assert created["user"]["system_role"] == "POLICE"
    assert created["user"]["is_active"] is True
    assert _password_key_hits(str(created["user"])) == []

    h = _login_header(client, created)
    me = client.get("/auth/me", headers=h)
    assert me.status_code == 200
    assert me.json()["email"] == created["email"]
    assert me.json()["system_role"] == "POLICE"
    assert _password_key_hits(me.text) == []


def test_create_user_normalizes_email_case(client, auth):
    admin = auth("ADMIN")
    email = _uniq_email("t4case")
    created = _create_user(client, admin, role="LAWYER", email=email.upper())
    assert created["user"]["email"] == email  # stored + echoed lowercase
    assert client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    ).status_code == 200


def test_create_user_rejects_duplicate_email(client, auth):
    admin = auth("ADMIN")
    created = _create_user(client, admin, role="LAWYER")
    dup = client.post(
        "/users",
        json={"email": created["email"], "password": PASSWORD, "system_role": "LAWYER"},
        headers=admin,
    )
    assert dup.status_code == 409
    dup_upper = client.post(
        "/users",
        json={"email": created["email"].upper(), "password": PASSWORD, "system_role": "POLICE"},
        headers=admin,
    )
    assert dup_upper.status_code == 409


def test_create_user_validates_input(client, auth):
    admin = auth("ADMIN")

    def post(**body):
        return client.post("/users", json=body, headers=admin)

    assert post(email=_uniq_email(), password=PASSWORD, system_role="SUPERUSER").status_code == 422
    assert post(email=_uniq_email(), password="short", system_role="COURT").status_code == 422
    assert post(email="not-an-email", password=PASSWORD, system_role="COURT").status_code == 422
    assert post(email=_uniq_email(), system_role="COURT").status_code == 422
    assert post(password=PASSWORD, system_role="COURT").status_code == 422


# ---- is_active lifecycle ----

def test_deactivation_blocks_login_and_invalidates_existing_tokens(client, auth):
    admin = auth("ADMIN")
    created = _create_user(client, admin, role="FORENSIC")
    h = _login_header(client, created)
    assert client.get("/auth/me", headers=h).status_code == 200

    r = client.patch(
        f"/users/{created['user']['id']}", json={"is_active": False}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["is_active"] is False

    assert client.post(
        "/auth/login", json={"email": created["email"], "password": PASSWORD}
    ).status_code == 401
    assert client.get("/auth/me", headers=h).status_code == 401
    assert client.get("/cases", headers=h).status_code == 401

    r = client.patch(
        f"/users/{created['user']['id']}", json={"is_active": True}, headers=admin
    )
    assert r.status_code == 200
    assert r.json()["user"]["is_active"] is True
    assert client.post(
        "/auth/login", json={"email": created["email"], "password": PASSWORD}
    ).status_code == 200


def test_deactivated_user_loses_case_access_even_with_access_row(client, auth, case_id):
    admin = auth("ADMIN")
    court = auth("COURT")
    assert client.post(
        "/cases", json={"case_id": case_id, "title": "t4 active flag"}, headers=court
    ).status_code == 200

    created = _create_user(client, admin, role="POLICE")
    assert client.post(
        f"/cases/{case_id}/access",
        json={"email": created["email"], "case_role": "POLICE"},
        headers=court,
    ).status_code == 200
    h = _login_header(client, created)
    assert client.get(f"/cases/{case_id}", headers=h).status_code == 200

    assert client.patch(
        f"/users/{created['user']['id']}", json={"is_active": False}, headers=admin
    ).status_code == 200
    assert client.get(f"/cases/{case_id}", headers=h).status_code == 401


# ---- password reset ----


def test_password_reset_changes_login(client, auth):
    admin = auth("ADMIN")
    created = _create_user(client, admin, role="COURT")
    new_password = "Task4-reset-2026!"
    r = client.patch(
        f"/users/{created['user']['id']}", json={"password": new_password}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert _password_key_hits(r.text) == []
    assert client.post(
        "/auth/login", json={"email": created["email"], "password": PASSWORD}
    ).status_code == 401
    assert client.post(
        "/auth/login", json={"email": created["email"], "password": new_password}
    ).status_code == 200


# ---- patch errors ----


def test_patch_user_error_paths(client, auth):
    admin = auth("ADMIN")
    me = client.get("/auth/me", headers=admin).json()

    unknown = str(uuid.uuid4())
    assert client.patch(
        f"/users/{unknown}", json={"is_active": False}, headers=admin
    ).status_code == 404
    assert client.patch(
        "/users/not-a-uuid", json={"is_active": False}, headers=admin
    ).status_code == 422
    # no fields supplied
    assert client.patch(f"/users/{unknown}", json={}, headers=admin).status_code == 422
    # cannot deactivate your own account
    r = client.patch(f"/users/{me['id']}", json={"is_active": False}, headers=admin)
    assert r.status_code == 409
    assert client.get("/auth/me", headers=admin).status_code == 200
    # short password rejected
    assert client.patch(
        f"/users/{unknown}", json={"password": "short"}, headers=admin
    ).status_code == 422


# ---- /users must not bypass case_access ----


def test_users_api_cannot_grant_or_bypass_case_access(client, auth, case_id):
    admin = auth("ADMIN")
    court = auth("COURT")
    assert client.post(
        "/cases", json={"case_id": case_id, "title": "t4 users-vs-access"}, headers=court
    ).status_code == 200

    created = _create_user(client, admin, role="COURT")
    h = _login_header(client, created)

    listed = {c["case_id"] for c in client.get("/cases", headers=h).json()}
    assert case_id not in listed
    assert client.get(f"/cases/{case_id}", headers=h).status_code == 403

    # only the case access API can grant visibility; then the same token works
    assert client.post(
        f"/cases/{case_id}/access",
        json={"email": created["email"], "case_role": "COURT"},
        headers=court,
    ).status_code == 200
    assert client.get(f"/cases/{case_id}", headers=h).status_code == 200
