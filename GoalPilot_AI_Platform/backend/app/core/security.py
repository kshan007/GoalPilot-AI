"""Password hashing and JWT issuing/verification.

bcrypt is used directly (``bcrypt`` package) rather than through ``passlib`` because
passlib's bcrypt backend emits spurious version warnings on modern bcrypt builds. The
hashing scheme is bcrypt with a per-password salt, and password input is truncated to
bcrypt's 72-byte limit explicitly and documented rather than silently.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets
from typing import Any

import bcrypt
import jwt

from app.config import get_settings

BCRYPT_MAX_BYTES = 72


def _normalise(password: str) -> bytes:
    """bcrypt only consumes the first 72 bytes. Truncate explicitly so behaviour is
    identical across implementations instead of raising or silently differing."""
    return password.encode("utf-8")[:BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    rounds = get_settings().bcrypt_rounds
    salt = bcrypt.gensalt(rounds=rounds)
    return bcrypt.hashpw(_normalise(password), salt).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_normalise(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, token_version: int = 0, extra: dict | None = None) -> str:
    settings = get_settings()
    now = dt.datetime.now(dt.timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tv": token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
        "iss": "goalpilot-ai",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer="goalpilot-ai",
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWTError:
        return None


# --- password reset -------------------------------------------------------------------
def generate_reset_token() -> tuple[str, str]:
    """Return (raw_token, token_hash). Only the hash is persisted."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_reset_token(raw)


def hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
