"""Auth schemas."""
from __future__ import annotations

import datetime as dt

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import ApiModel

PASSWORD_MIN = 8


def _check_password(value: str) -> str:
    if len(value) < PASSWORD_MIN:
        raise ValueError(f"Password must be at least {PASSWORD_MIN} characters.")
    if value.strip() != value:
        raise ValueError("Password must not start or end with whitespace.")
    if value.isdigit() or value.isalpha():
        raise ValueError("Password must mix letters with digits or symbols.")
    return value


class RegisterRequest(ApiModel):
    email: EmailStr
    password: str
    full_name: str = Field(default="", max_length=160)

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return _check_password(v)


class LoginRequest(ApiModel):
    email: EmailStr
    password: str


class UserOut(ApiModel):
    id: int
    email: str
    full_name: str
    created_at: dt.datetime
    last_login_at: dt.datetime | None = None
    is_admin: bool = False


class TokenResponse(ApiModel):
    user: UserOut
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(ApiModel):
    email: EmailStr


class ForgotPasswordResponse(ApiModel):
    message: str
    # Only populated when EXPOSE_RESET_TOKEN=true (development). In production the token is
    # delivered out of band and this stays null.
    reset_token: str | None = None


class ResetPasswordRequest(ApiModel):
    token: str = Field(min_length=10)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return _check_password(v)


class ChangePasswordRequest(ApiModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return _check_password(v)
