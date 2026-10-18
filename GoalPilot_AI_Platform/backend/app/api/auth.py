"""Authentication: register, login, logout, session, password recovery and reset."""
from __future__ import annotations

import datetime as dt
import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import current_user, enforce_auth_rate_limit
from app.core.errors import AuthError, ConflictError, ValidationFailure
from app.core.security import (
    create_access_token,
    generate_reset_token,
    hash_password,
    hash_reset_token,
    verify_password,
)
from app.db import get_db
from app.models import AuditEvent, PasswordResetToken, User, UserPreference
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
)
from app.schemas.common import MessageResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _log(db: Session, event: str, user_id: int | None, request: Request, detail: dict | None = None):
    db.add(
        AuditEvent(
            user_id=user_id,
            event_type=event,
            detail_json=json.dumps(detail or {}),
            ip=request.client.host if request.client else None,
        )
    )


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        is_admin=bool(user.is_admin),
    )


@router.post("/register", response_model=TokenResponse, dependencies=[Depends(enforce_auth_rate_limit)])
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    existing = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
    if existing is not None:
        # Do not disclose which accounts exist beyond the unavoidable registration conflict.
        raise ConflictError("An account with this email already exists.")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        last_login_at=dt.datetime.now(dt.timezone.utc),
    )
    db.add(user)
    db.flush()
    db.add(UserPreference(user_id=user.id))
    _log(db, "register", user.id, request)
    db.commit()
    db.refresh(user)
    return TokenResponse(
        user=_user_out(user),
        access_token=create_access_token(user.id, user.token_version),
    )


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(enforce_auth_rate_limit)])
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
    # Uniform failure: the same error whether the account is missing or the password is wrong.
    if user is None or not verify_password(payload.password, user.password_hash):
        _log(db, "login_failed", user.id if user else None, request)
        db.commit()
        raise AuthError("Incorrect email or password.")
    if not user.is_active:
        raise AuthError("This account is not active.")

    user.last_login_at = dt.datetime.now(dt.timezone.utc)
    _log(db, "login", user.id, request)
    db.commit()
    db.refresh(user)
    return TokenResponse(
        user=_user_out(user),
        access_token=create_access_token(user.id, user.token_version),
    )


@router.post(
    "/admin/login",
    response_model=TokenResponse,
    dependencies=[Depends(enforce_auth_rate_limit)],
)
def admin_login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Separate door for administrators.

    A normal account cannot use it even with a correct password, and the failure message never
    reveals whether the email exists. The session it issues is the same kind of token, but every
    admin-only route re-checks the account's flag, so removing access is immediate.
    """
    email = payload.email.strip().lower()
    user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        _log(db, "admin_login_failed", user.id if user else None, request)
        db.commit()
        raise AuthError("Incorrect email or password.")
    if not user.is_active:
        raise AuthError("This account is not active.")
    if not user.is_admin:
        _log(db, "admin_login_denied", user.id, request)
        db.commit()
        raise AuthError("This account does not have administrative access.")

    user.last_login_at = dt.datetime.now(dt.timezone.utc)
    _log(db, "admin_login", user.id, request)
    db.commit()
    db.refresh(user)
    return TokenResponse(
        user=_user_out(user),
        access_token=create_access_token(user.id, user.token_version),
    )


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Sign out.

    Revokes **all** sessions for the account by rotating the token version. This is a
    deliberate, documented choice: it is the safe failure mode (a leaked token cannot
    survive a sign-out) and it needs no server-side session store.
    """
    user.token_version += 1
    _log(db, "logout", user.id, request)
    db.commit()
    return MessageResponse(message="Signed out. All sessions for this account were revoked.")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return _user_out(user)


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    dependencies=[Depends(enforce_auth_rate_limit)],
)
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    email = payload.email.strip().lower()
    user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()

    generic = "If an account exists for that email, a password reset link has been issued."
    if user is None or not user.is_active:
        # Same response and same latency profile as the success path.
        _log(db, "reset_requested_unknown_email", None, request)
        db.commit()
        return ForgotPasswordResponse(message=generic, reset_token=None)

    raw, token_hash = generate_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=dt.datetime.now(dt.timezone.utc)
            + dt.timedelta(minutes=settings.reset_token_ttl_minutes),
        )
    )
    _log(db, "reset_requested", user.id, request)
    db.commit()
    return ForgotPasswordResponse(
        message=generic,
        reset_token=raw if settings.expose_reset_token else None,
    )


@router.post("/reset-password", response_model=MessageResponse, dependencies=[Depends(enforce_auth_rate_limit)])
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    token_hash = hash_reset_token(payload.token)
    row = db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    ).scalar_one_or_none()
    if row is None:
        raise ValidationFailure("This reset link is not valid.")
    now = dt.datetime.now(dt.timezone.utc)
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=dt.timezone.utc)
    if row.used_at is not None:
        raise ValidationFailure("This reset link has already been used.")
    if expires < now:
        raise ValidationFailure("This reset link has expired.")

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise ValidationFailure("This account is not available.")

    user.password_hash = hash_password(payload.new_password)
    user.token_version += 1  # every existing session is invalidated
    row.used_at = now
    _log(db, "password_reset", user.id, request)
    db.commit()
    return MessageResponse(message="Your password has been reset. Sign in with the new password.")


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise AuthError("The current password is incorrect.")
    if payload.current_password == payload.new_password:
        raise ValidationFailure("The new password must differ from the current password.")
    user.password_hash = hash_password(payload.new_password)
    user.token_version += 1
    _log(db, "password_changed", user.id, request)
    db.commit()
    return MessageResponse(message="Password changed. Please sign in again.")
