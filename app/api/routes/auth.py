"""
OWNER: Person A
POST /auth/register  (admin-only in practice, open for now to ease seeding)
POST /auth/login
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.auth import UserCreate, LoginRequest, TokenResponse

router = APIRouter()

@router.post("/register", status_code=201)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    # TODO(Person A): hash password, insert User, return id
    raise NotImplementedError

@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    # TODO(Person A): verify user + password, create_access_token({"sub": user.id, "role": user.role})
    raise NotImplementedError
