from __future__ import annotations

import random
import time
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_user
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    ConfirmUpdateEmailRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UpdateEmailRequest,
    UserOut,
    VerifyEmailRequest,
)


router = APIRouter(tags=["auth"])


@dataclass
class OTPRecord:
    code: str
    expires_at: float


class InMemoryOTPStore:
    def __init__(self) -> None:
        self._records: dict[str, OTPRecord] = {}

    def issue(self, key: str, ttl_seconds: int = 600) -> str:
        code = f"{random.randint(0, 999999):06d}"
        self._records[key] = OTPRecord(code=code, expires_at=time.monotonic() + ttl_seconds)
        return code

    def verify(self, key: str, code: str) -> bool:
        record = self._records.get(key)
        if not record:
            return False
        if record.expires_at < time.monotonic():
            self._records.pop(key, None)
            return False
        if record.code != code:
            return False
        self._records.pop(key, None)
        return True


class LoginGuard:
    def __init__(self, max_attempts: int = 5, lock_seconds: int = 300) -> None:
        self.max_attempts = max_attempts
        self.lock_seconds = lock_seconds
        self._attempts: dict[str, int] = {}
        self._locked_until: dict[str, float] = {}

    def assert_allowed(self, email: str) -> None:
        until = self._locked_until.get(email)
        if until and until > time.monotonic():
            raise HTTPException(status_code=429, detail="Too many failed attempts. Please retry later.")
        if until and until <= time.monotonic():
            self._locked_until.pop(email, None)
            self._attempts.pop(email, None)

    def record_failure(self, email: str) -> None:
        count = self._attempts.get(email, 0) + 1
        self._attempts[email] = count
        if count >= self.max_attempts:
            self._locked_until[email] = time.monotonic() + self.lock_seconds

    def record_success(self, email: str) -> None:
        self._attempts.pop(email, None)
        self._locked_until.pop(email, None)


otp_store = InMemoryOTPStore()
login_guard = LoginGuard()
pending_email_updates: dict[str, str] = {}
verified_emails: set[str] = set()


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "n/a")


def _normalize_role(role: str | None) -> str:
    r = (role or "student").strip().lower()
    if r not in {"student", "teacher"}:
        raise HTTPException(status_code=400, detail="Invalid role. Use 'student' or 'teacher'.")
    return r


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=int(u.id),
        email=str(u.email),
        full_name=u.full_name,
        role=getattr(u, "role", "student") or "student",
        is_active=bool(getattr(u, "is_active", True)),
    )


def _email_key(prefix: str, email: str) -> str:
    return f"{prefix}:{email.strip().lower()}"


def _send_security_email(email: str, subject: str, body: str) -> None:
    # Placeholder for SMTP integration; avoids exposing internals to clients.
    print(f"[EMAIL] to={email} subject={subject} body={body}")


@router.post("/auth/register")
def register(request: Request, payload: RegisterRequest, db: Session = Depends(get_db)):
    role = _normalize_role(payload.role)
    email = str(payload.email).strip().lower()

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    u = User(
        email=email,
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        major=payload.major,
        class_name=payload.class_name,
        role=role,
        password_hash=get_password_hash(payload.password),
        is_active=False,
    )
    db.add(u)
    db.commit()
    db.refresh(u)

    otp = otp_store.issue(_email_key("verify_email", email))
    _send_security_email(
        email,
        subject="Xác minh email đăng ký tài khoản",
        body=f"Mã OTP xác minh đăng ký của bạn là: {otp}. Mã hết hạn sau 10 phút.",
    )

    return {
        "request_id": _request_id(request),
        "data": {"message": "Registration successful. Please verify your email.", "email": email},
        "error": None,
    }


@router.post("/auth/verify-email")
def verify_email(request: Request, payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    if not otp_store.verify(_email_key("verify_email", email), payload.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = True
    db.add(user)
    db.commit()

    verified_emails.add(email)
    _send_security_email(
        email,
        subject="Đăng ký thành công",
        body="Chúc mừng bạn đã đăng ký tài khoản thành công. Bạn có thể đăng nhập ngay bây giờ.",
    )

    return {"request_id": _request_id(request), "data": {"message": "Email verified"}, "error": None}


@router.post("/auth/login-json")
def login_json(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    login_guard.assert_allowed(email)

    u = db.query(User).filter(User.email == email).first()
    if not u or not getattr(u, "password_hash", None):
        login_guard.record_failure(email)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(payload.password, str(u.password_hash)):
        login_guard.record_failure(email)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not bool(getattr(u, "is_active", True)):
        raise HTTPException(status_code=403, detail="Email is not verified")

    login_guard.record_success(email)
    token = TokenResponse(access_token=create_access_token(subject=str(u.id)))
    out = AuthResponse(token=token, user=_user_out(u)).model_dump()
    return {"request_id": _request_id(request), "data": out, "error": None}


@router.post("/auth/login")
def login_form(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = str(form_data.username).strip().lower()
    login_guard.assert_allowed(email)

    u = db.query(User).filter(User.email == email).first()
    if not u or not getattr(u, "password_hash", None):
        login_guard.record_failure(email)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(form_data.password, str(u.password_hash)):
        login_guard.record_failure(email)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not bool(getattr(u, "is_active", True)):
        raise HTTPException(status_code=403, detail="Email is not verified")

    login_guard.record_success(email)
    token = TokenResponse(access_token=create_access_token(subject=str(u.id)))
    out = {"access_token": token.access_token, "token_type": token.token_type}
    return {"request_id": _request_id(request), "data": out, "error": None}


@router.post("/auth/forgot-password")
def forgot_password(request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user:
        otp = otp_store.issue(_email_key("forgot_password", email))
        _send_security_email(
            email,
            subject="Yêu cầu đặt lại mật khẩu",
            body=f"Mã OTP đặt lại mật khẩu là: {otp}. Nếu không phải bạn, vui lòng bỏ qua email này.",
        )
    return {
        "request_id": _request_id(request),
        "data": {"message": "If the account exists, a reset OTP has been sent."},
        "error": None,
    }


@router.post("/auth/reset-password")
def reset_password(request: Request, payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not otp_store.verify(_email_key("forgot_password", email), payload.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    user.password_hash = get_password_hash(payload.new_password)
    db.add(user)
    db.commit()

    _send_security_email(
        email,
        subject="Mật khẩu đã được thay đổi",
        body="Mật khẩu tài khoản của bạn vừa được thay đổi. Nếu không phải bạn, hãy liên hệ quản trị viên ngay.",
    )

    return {"request_id": _request_id(request), "data": {"message": "Password reset successful"}, "error": None}


@router.post("/auth/change-password")
def change_password(request: Request, payload: ChangePasswordRequest, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(payload.old_password, str(user.password_hash)):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not otp_store.verify(_email_key("change_password", email), payload.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    user.password_hash = get_password_hash(payload.new_password)
    db.add(user)
    db.commit()

    _send_security_email(
        email,
        subject="Xác nhận thay đổi mật khẩu",
        body="Bạn đã thay đổi mật khẩu thành công. Nếu không phải bạn, vui lòng báo ngay cho quản trị viên.",
    )

    return {"request_id": _request_id(request), "data": {"message": "Password changed"}, "error": None}


@router.post("/auth/change-password/request-otp")
def request_change_password_otp(request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user:
        otp = otp_store.issue(_email_key("change_password", email))
        _send_security_email(email, "Mã OTP đổi mật khẩu", f"OTP đổi mật khẩu của bạn là: {otp}")

    return {"request_id": _request_id(request), "data": {"message": "OTP has been sent"}, "error": None}


@router.post("/auth/update-email")
def update_email(request: Request, payload: UpdateEmailRequest, db: Session = Depends(get_db)):
    current_email = str(payload.current_email).strip().lower()
    new_email = str(payload.new_email).strip().lower()

    user = db.query(User).filter(User.email == current_email).first()
    if not user or not user.password_hash or not verify_password(payload.password, str(user.password_hash)):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if db.query(User).filter(User.email == new_email).first():
        raise HTTPException(status_code=400, detail="New email already exists")

    otp = otp_store.issue(_email_key("update_email", new_email))
    pending_email_updates[current_email] = new_email
    _send_security_email(new_email, "Xác minh email mới", f"Mã OTP xác minh email mới là: {otp}")

    return {
        "request_id": _request_id(request),
        "data": {"message": "Verification OTP sent to new email"},
        "error": None,
    }


@router.post("/auth/update-email/confirm")
def confirm_update_email(request: Request, payload: ConfirmUpdateEmailRequest, db: Session = Depends(get_db)):
    current_email = str(payload.current_email).strip().lower()
    new_email = str(payload.new_email).strip().lower()

    if pending_email_updates.get(current_email) != new_email:
        raise HTTPException(status_code=400, detail="No pending email update request")
    if not otp_store.verify(_email_key("update_email", new_email), payload.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    user = db.query(User).filter(User.email == current_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.email = new_email
    db.add(user)
    db.commit()
    pending_email_updates.pop(current_email, None)

    _send_security_email(new_email, "Đổi email thành công", "Email đăng nhập của bạn đã được cập nhật thành công.")

    return {"request_id": _request_id(request), "data": {"message": "Email updated"}, "error": None}


@router.get("/auth/me")
def me(request: Request, user: User = Depends(require_user)):
    out = _user_out(user).model_dump()
    return {"request_id": _request_id(request), "data": out, "error": None}
