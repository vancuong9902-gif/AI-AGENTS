from __future__ import annotations

from typing import Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

ALLOWED_SELF_REGISTER_ROLES = {"student", "teacher"}


class RegisterRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255, validation_alias=AliasChoices("name", "full_name"))
    email: str
    password: str = Field(min_length=8, max_length=200)
    role: Literal["student", "teacher"] = "student"

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        v = str(value).strip().lower()
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("Invalid email format")
        local, domain = v.split("@", 1)
        if not local or "." not in domain:
            raise ValueError("Invalid email format")
        return v

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value: str) -> str:
        if value is None:
            return "student"
        return str(value).strip().lower()

    @model_validator(mode="after")
    def validate_name(self):
        self.name = str(self.name).strip()
        if not self.name:
            raise ValueError("Name is required")
        return self


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        v = str(value).strip().lower()
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("Invalid email format")
        local, domain = v.split("@", 1)
        if not local or "." not in domain:
            raise ValueError("Invalid email format")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        v = str(value)
        if not v.strip():
            raise ValueError("Password is required")
        return v


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
