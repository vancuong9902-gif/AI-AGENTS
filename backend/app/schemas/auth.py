from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


GMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@gmail\.com$")
PHONE_PATTERN = re.compile(r"^(?:\+84|0)\d{9,10}$")
PASSWORD_HAS_UPPER = re.compile(r"[A-Z]")
PASSWORD_HAS_LOWER = re.compile(r"[a-z]")
PASSWORD_HAS_NUMBER = re.compile(r"\d")


def _validate_gmail(email: str) -> str:
    normalized = email.strip().lower()
    if not GMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Email must be a valid Gmail address")
    return normalized


def _validate_password_strength(password: str) -> str:
    if not PASSWORD_HAS_UPPER.search(password):
        raise ValueError("Password must include at least 1 uppercase letter")
    if not PASSWORD_HAS_LOWER.search(password):
        raise ValueError("Password must include at least 1 lowercase letter")
    if not PASSWORD_HAS_NUMBER.search(password):
        raise ValueError("Password must include at least 1 number")
    return password


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=2, max_length=255)
    phone_number: str
    major: str = Field(min_length=2, max_length=120)
    class_name: str = Field(min_length=2, max_length=120)
    role: str = "student"  # student|teacher

    @field_validator("email")
    @classmethod
    def validate_gmail(cls, value: str) -> str:
        return _validate_gmail(str(value))

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        phone = value.strip().replace(" ", "")
        if not PHONE_PATTERN.fullmatch(phone):
            raise ValueError("Phone number is invalid")
        return phone

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_gmail(cls, value: str) -> str:
        return _validate_gmail(str(value))


class VerifyEmailRequest(BaseModel):
    email: str
    otp: str = Field(min_length=6, max_length=6)


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    otp: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8, max_length=200)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)


class ChangePasswordRequest(BaseModel):
    email: str
    old_password: str
    new_password: str = Field(min_length=8, max_length=200)
    otp: str = Field(min_length=6, max_length=6)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)


class UpdateEmailRequest(BaseModel):
    current_email: str
    password: str
    new_email: str

    @field_validator("current_email", "new_email")
    @classmethod
    def validate_gmail(cls, value: str) -> str:
        return _validate_gmail(str(value))


class ConfirmUpdateEmailRequest(BaseModel):
    current_email: str
    new_email: str
    otp: str = Field(min_length=6, max_length=6)

    @field_validator("current_email", "new_email")
    @classmethod
    def validate_gmail(cls, value: str) -> str:
        return _validate_gmail(str(value))


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
