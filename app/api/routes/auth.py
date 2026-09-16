"""
OWNER: Person A
POST /auth/register  — admin-only
POST /auth/login     — form: username=email, password
GET  /auth/me
"""
from fastapi import APIRouter, Depends, Form, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import TokenResponse, UserCreate, UserResponse

router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a user (admin only)",
)
async def register(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    existing = await db.execute(select(User).where(User.email == payload.email.lower()))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        name=payload.name,
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        role=payload.role,
        org=payload.org,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email (username field) and password",
)
async def login(
    username: str = Form(..., description="Your email address"),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == username.lower()))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user.id, "role": user.role})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse, summary="Current authenticated user")
async def me(user: User = Depends(get_current_user)):
    return user
