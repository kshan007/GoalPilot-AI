"""Create or promote an administrator account.

Usage::

    python scripts/create_admin.py --email you@example.com --password '...'
    python scripts/create_admin.py --email you@example.com --promote-only

Nothing is printed except the account's email and whether it was created or promoted; the
password is never echoed, stored in plain text or written to disk.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from pydantic import EmailStr, TypeAdapter, ValidationError  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db import get_session_factory  # noqa: E402
from app.models import User, UserPreference  # noqa: E402

MIN_PASSWORD_LENGTH = 10


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or promote a GoalPilot administrator.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", default="")
    parser.add_argument(
        "--password-env",
        default="",
        help=(
            "Read the password from this environment variable instead of --password, so it "
            "never appears in process arguments or shell history."
        ),
    )
    parser.add_argument(
        "--promote-only",
        action="store_true",
        help="Grant admin rights to an existing account without changing its password.",
    )
    args = parser.parse_args()

    # Validate with exactly the rule the sign-in endpoint applies. Without this, an address such
    # as ``admin@goalpilot.local`` was accepted here and then refused by the login form forever
    # (``.local`` is a special-use domain), which looked like a broken sign-in.
    try:
        email = str(TypeAdapter(EmailStr).validate_python(args.email.strip().lower()))
    except ValidationError:
        print(
            f"'{args.email}' cannot be used for sign-in: it is not a deliverable email address "
            "(special-use domains such as .local and .internal are rejected). Use a normal "
            "domain, for example admin@example.com.",
            file=sys.stderr,
        )
        return 2

    password = os.environ.get(args.password_env, "") if args.password_env else args.password
    if not args.promote_only and len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        return 2

    with get_session_factory()() as db:
        user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
        if user is None:
            if args.promote_only:
                print(f"No account exists for {email}.", file=sys.stderr)
                return 1
            user = User(
                email=email,
                password_hash=hash_password(password),
                full_name="Administrator",
                is_admin=True,
            )
            db.add(user)
            db.flush()
            db.add(UserPreference(user_id=user.id))
            action = "created"
        else:
            user.is_admin = True
            if not args.promote_only:
                user.password_hash = hash_password(password)
            action = "promoted"
        db.commit()
        print(f"Administrator {action}: {email}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


