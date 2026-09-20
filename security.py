"""Password hashing and JWT access tokens (Task 2).

Uses bcrypt for hashes and PyJWT (HS256) for access tokens.
``JWT_SECRET_KEY`` is required to mint or verify tokens.
``JWT_EXPIRE_MINUTES`` defaults to 60.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

import bcrypt
import jwt
from dotenv import load_dotenv

load_dotenv()

JWT_ALGORITHM = "HS256"
_DUMMY_HASH: Optional[str] = None


def jwt_secret_key() -> str:
    key = os.getenv("JWT_SECRET_KEY")
    if not key:
        raise RuntimeError(
            "JWT_SECRET_KEY is not configured. Set it in .env (see .env.example)."
        )
    return key


def jwt_expire_minutes() -> int:
    raw = os.getenv("JWT_EXPIRE_MINUTES") or os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES") or "60"
    try:
        return max(1, int(raw))
    except ValueError:
        return 60


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def dummy_password_hash() -> str:
    """Constant-time-ish probe when the email does not exist."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("not-a-real-user")
    return _DUMMY_HASH


def create_access_token(
    *,
    user_id: UUID,
    email: str,
    system_role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    now = datetime.now(timezone.utc)
    exp = now + (expires_delta or timedelta(minutes=jwt_expire_minutes()))
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "system_role": system_role,
        "iat": int(now.timestamp()),
        "exp": exp,
    }
    return jwt.encode(payload, jwt_secret_key(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, jwt_secret_key(), algorithms=[JWT_ALGORITHM])
