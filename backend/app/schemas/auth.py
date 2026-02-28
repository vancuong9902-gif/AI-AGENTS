from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=200)
    full_name: Optional[str] = None
    role: str = "student"  # student|teacher


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role: str = "student"
    is_active: bool = True


class AuthResponse(BaseModel):
    token: TokenResponse
    user: UserOut
