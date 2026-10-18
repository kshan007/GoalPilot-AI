"""Shared FastAPI dependencies: the DB session, the authenticated user, and owned-row
lookups.

Ownership is enforced *here*, once, so no route can forget it. ``owned_or_404`` never
distinguishes "does not exist" from "belongs to someone else" — both are 404.
"""
from __future__ import annotations

from typing import TypeVar

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AuthError, NotFoundError, PermissionDenied
from app.core.ratelimit import limiter
from app.core.security import decode_access_token
from app.db import get_db
from app.models import User

T = TypeVar("T")

_UNAUTHENTICATED = "Not authenticated"


def _bearer(request: Request, authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    # Fall back to a cookie so the browser can hold a session without JS-managed storage.
    return request.cookies.get("gp_access_token")


def current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = _bearer(request, authorization)
    if not token:
        raise AuthError(_UNAUTHENTICATED)
    payload = decode_access_token(token)
    if not payload:
        raise AuthError("Invalid or expired session")
    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise AuthError("Invalid session subject") from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthError("Account is not available")
    # Token revocation: a password change or logout-all bumps token_version.
    if int(payload.get("tv", 0)) != int(user.token_version):
        raise AuthError("Session has been revoked")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    """Administrative access, checked against the account on every request.

    Deliberately not derived from the token: revoking the flag takes effect on the next call
    rather than when the current session happens to expire.
    """
    if not bool(user.is_admin):
        raise PermissionDenied("Administrative access is required.")
    return user


def client_identity(request: Request, user: User | None = None) -> str:
    if user is not None:
        return f"user:{user.id}"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


def enforce_auth_rate_limit(request: Request) -> None:
    settings = get_settings()
    limiter.check("auth", client_identity(request), settings.rate_limit_auth_per_minute)


def enforce_optimize_rate_limit(request: Request, user: User = Depends(current_user)) -> User:
    settings = get_settings()
    limiter.check("optimize", client_identity(request, user), settings.rate_limit_optimize_per_minute)
    return user


def owned_or_404(db: Session, model: type[T], user: User, row_id: int) -> T:
    """Load a user-owned row by id **scoped to the caller**. 404 on mismatch."""
    stmt = select(model).where(model.id == row_id, model.user_id == user.id)  # type: ignore[attr-defined]
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"{model.__name__} {row_id} was not found")
    return row
