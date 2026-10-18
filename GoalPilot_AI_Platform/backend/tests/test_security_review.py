"""Security controls that must hold regardless of what the UI offers.

Each test asserts a property of the running application rather than restating the implementation:
route dependencies are inspected directly, cross-account access is attempted for real, and the
audit payload is read back from the database.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.core.security import verify_password
from app.db import get_session_factory
from app.main import app
from app.models import User
from tests.conftest import seed_profile_and_goal

ADMIN_PATHS = (
    "/api/admin/overview",
    "/api/admin/runs",
    "/api/admin/users",
    "/api/admin/audit",
    "/api/admin/health",
    "/api/admin/data",
    "/api/models/registry",
    "/api/models/checkpoints",
    "/api/models/benchmarks",
)


def test_every_admin_route_declares_the_admin_dependency():
    admin_routes = [r for r in app.routes if getattr(r, "path", "").startswith("/api/admin")]
    assert admin_routes, "no admin routes found"
    for route in admin_routes:
        names = [dep.call.__name__ for dep in route.dependant.dependencies]
        assert "require_admin" in names, f"{route.path} does not require an administrator"


def test_admin_login_is_rate_limited():
    routes = [
        r
        for r in app.routes
        if getattr(r, "path", "") == "/api/auth/admin/login" and "POST" in getattr(r, "methods", set())
    ]
    assert routes, "admin login route missing"
    names = [dep.call.__name__ for dep in routes[0].dependant.dependencies]
    assert "enforce_auth_rate_limit" in names


def test_ordinary_users_are_refused_every_admin_surface(registered):
    for path in ADMIN_PATHS:
        response = registered["client"].get(path, headers=registered["headers"])
        assert response.status_code == 403, f"{path} returned {response.status_code}"

    me = registered["client"].get("/api/auth/me", headers=registered["headers"]).json()
    patch = registered["client"].patch(
        f"/api/admin/users/{me['id']}", headers=registered["headers"], json={"is_admin": True}
    )
    assert patch.status_code == 403
    # The attempt must not have granted anything.
    assert registered["client"].get("/api/auth/me", headers=registered["headers"]).json()[
        "is_admin"
    ] is False


def test_comparison_is_scoped_to_the_caller(registered, second_user):
    seed_profile_and_goal(registered, goals=1)
    seed_profile_and_goal(second_user, goals=1)

    first = registered["client"].post("/api/optimize/compare", headers=registered["headers"])
    assert first.status_code == 200, first.text
    first_run = first.json()["run_id"]

    own_runs = registered["client"].get(
        "/api/optimize/runs?kind=compare", headers=registered["headers"]
    ).json()["items"]
    assert [run["id"] for run in own_runs] == [first_run]

    other_runs = second_user["client"].get(
        "/api/optimize/runs?kind=compare", headers=second_user["headers"]
    ).json()["items"]
    assert first_run not in [run["id"] for run in other_runs]

    stolen = second_user["client"].get(
        f"/api/optimize/runs/{first_run}", headers=second_user["headers"]
    )
    assert stolen.status_code == 404


def test_admin_run_detail_carries_no_private_finances(admin):
    seed_profile_and_goal(admin, goals=1)
    plan = admin["client"].post(
        "/api/optimize/plan", headers=admin["headers"], json={"algorithm": "lp"}
    ).json()

    detail = admin["client"].get(
        f"/api/admin/runs/{plan['run_id']}", headers=admin["headers"]
    ).json()
    serialised = json.dumps(detail).lower()
    for forbidden in ("income_sources", "liabilities", "transactions", "password", "token"):
        assert forbidden not in serialised


def test_audit_records_hold_no_secrets_or_financial_payloads(admin, second_user):
    listing = admin["client"].get("/api/admin/users", headers=admin["headers"]).json()
    target = next(item for item in listing["items"] if item["email"] == second_user["email"])
    admin["client"].patch(
        f"/api/admin/users/{target['id']}",
        headers=admin["headers"],
        json={"is_admin": True},
    )

    audit = admin["client"].get("/api/admin/audit", headers=admin["headers"]).json()
    entry = next(e for e in audit["items"] if e["action"] == "user.update")
    assert set(entry["details"]) == {"before", "after"}
    assert set(entry["details"]["after"]) == {"is_admin", "is_active"}

    raw = json.dumps(audit).lower()
    for forbidden in ("password", "token", "secret", "api_key", "authorization"):
        assert forbidden not in raw


def test_audit_log_is_append_only(admin):
    # There is deliberately no mutation route; an uncommon verb must not fall through to one.
    assert admin["client"].patch("/api/admin/audit", headers=admin["headers"], json={}).status_code == 405
    assert admin["client"].delete("/api/admin/audit", headers=admin["headers"]).status_code == 405


def test_passwords_are_bcrypt_hashed(registered):
    with get_session_factory()() as db:
        user = db.execute(
            select(User).where(User.email == registered["email"])
        ).scalar_one()
        assert user.password_hash != registered["password"]
        assert user.password_hash.startswith("$2")
        assert verify_password(registered["password"], user.password_hash)
        assert not verify_password("definitely-not-the-password", user.password_hash)

def test_production_requires_a_secret_key(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("GOALPILOT_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        Settings()


def test_production_refuses_to_expose_reset_tokens(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("GOALPILOT_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 48)
    monkeypatch.setenv("EXPOSE_RESET_TOKEN", "true")
    with pytest.raises(RuntimeError, match="EXPOSE_RESET_TOKEN"):
        Settings()

