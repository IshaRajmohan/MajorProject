"""Login, current-user dependency, and /auth routes (Task 2).

RBAC / case-permission checks are Task 3 — this module only authenticates.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from db_models import User
from security import (
    create_access_token,
    decode_access_token,
    dummy_password_hash,
    verify_password,
)

router = APIRouter(tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid credentials",
    headers={"WWW-Authenticate": "Bearer"},
)
_NOT_AUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def user_public(user: User) -> Dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email,
        "system_role": user.system_role.value
        if hasattr(user.system_role, "value")
        else str(user.system_role),
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


async def _user_by_email(session: AsyncSession, email: str) -> Optional[User]:
    return (
        await session.execute(
            select(User).where(User.email == email.strip().lower())
        )
    ).scalar_one_or_none()


async def get_current_active_user(
    token: Optional[str] = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Reusable dependency: valid JWT + active PostgreSQL user. Never returns a hash."""
    if not token:
        raise _NOT_AUTHENTICATED
    try:
        payload = decode_access_token(token)
        sub = payload.get("sub")
        uid = UUID(str(sub))
    except Exception:
        raise _NOT_AUTHENTICATED from None
    user = await session.get(User, uid)
    if user is None or not user.is_active:
        raise _NOT_AUTHENTICATED
    return user


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_db)) -> TokenResponse:
    email = str(body.email).strip().lower()
    user = await _user_by_email(session, email)
    hashed = user.password_hash if user is not None else dummy_password_hash()
    ok = verify_password(body.password, hashed)
    if user is None or not ok or not user.is_active:
        raise _UNAUTHORIZED
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        system_role=user.system_role.value
        if hasattr(user.system_role, "value")
        else str(user.system_role),
    )
    return TokenResponse(access_token=token)


@router.get("/auth/me")
async def read_me(current: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    return user_public(current)
