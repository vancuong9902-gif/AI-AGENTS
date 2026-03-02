from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator

ALLOWED_SELF_REGISTER_ROLES = {"student", "teacher"}


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=200)
    full_name: Optional[str] = None
    role: str = "student"
    student_code: Optional[str] = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_role_and_student_code(self):
        if self.role not in ALLOWED_SELF_REGISTER_ROLES:
            raise ValueError("Invalid role")
        if self.role == "student" and not self.student_code:
            raise ValueError("student_code is required for student role")
        return self


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
    student_code: Optional[str] = None
    is_active: bool = True


class AuthResponse(BaseModel):
    token: TokenResponse
    user: UserOut


class AdminCreateTeacherRequest(BaseModel):
    email: str
    full_name: Optional[str] = None
    password: str = Field(min_length=6, max_length=200)


class AdminCreateStudentRequest(BaseModel):
    email: str
    full_name: Optional[str] = None
    password: str = Field(min_length=6, max_length=200)
    student_code: str = Field(min_length=1, max_length=64)


class AdminUserPatchRequest(BaseModel):
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=200)
    role: Optional[str] = None
    student_code: Optional[str] = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_role(self):
        if self.role is not None and self.role not in {"student", "teacher", "admin"}:
            raise ValueError("Invalid role")
        return self
