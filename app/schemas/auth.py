"""OWNER: Person A"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

RoleLiteral = Literal["police", "court", "lawyer", "forensic", "citizen", "admin"]
VALID_ROLES = {"police", "court", "lawyer", "forensic", "citizen", "admin"}


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: RoleLiteral
    org: str | None = Field(default=None, max_length=120)

    @field_validator("role")
    @classmethod
    def role_must_be_known(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_ROLES)}")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: RoleLiteral
    org: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
