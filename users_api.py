"""
ADMIN-only system user management (Task 4).

These endpoints administer *system accounts* (email, password, system_role,
is_active). They never touch case scoping: assigning a user to a case remains
exclusively in /cases/{case_id}/access (rbac.py), so this API cannot be used
to bypass case_access — a user created here sees no case until a COURT/ADMIN
grants them a case_role.

Security invariants (tested in tests/test_users_api.py):
- All routes require a valid JWT for an active ADMIN account (403 otherwise).
- Passwords are hashed with the same bcrypt helper as /auth/login.
- Responses never include password or password_hash (auth.user_public only).
- Duplicate emails are rejected (409); DB unique constraint backs this up.
- An admin cannot deactivate their own account (409), avoiding lockout
  mid-session; another ADMIN must do it.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_active_user, user_public
from db import get_db
from db_models import SystemRole, User
from security import hash_password

router = APIRouter(tags=["users"])


async def require_admin(user: User = Depends(get_current_active_user)) -> User:
    """Reusable dependency: active ADMIN account. Non-ADMIN callers get 403."""
    role = user.system_role.value if hasattr(user.system_role, "value") else str(user.system_role)
    if role != SystemRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="ADMIN role required"
        )
    return user


class UserCreateIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    system_role: SystemRole

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise ValueError("enter a valid email address")
        return email


class UserPatchIn(BaseModel):
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)


@router.get("/users")
async def list_users(
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    rows = (
        await session.execute(select(User).order_by(User.created_at, User.email))
    ).scalars().all()
    return {"users": [user_public(u) for u in rows]}


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    existing = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalars().first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")
    row = User(
        email=body.email,
        password_hash=hash_password(body.password),
        system_role=body.system_role,
        is_active=True,
    )
    session.add(row)
    await session.commit()
    return {"user": user_public(row)}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: UUID,
    body: UserPatchIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if body.is_active is None and body.password is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="no fields supplied (is_active and/or password required)",
        )
    row = await session.get(User, user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if body.is_active is False and row.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot deactivate your own account",
        )
    if body.is_active is not None:
        row.is_active = body.is_active
    if body.password is not None:
        row.password_hash = hash_password(body.password)
    await session.commit()
    return {"user": user_public(row)}
