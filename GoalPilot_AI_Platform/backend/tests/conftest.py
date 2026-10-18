"""Shared test fixtures.

The suite runs against a throwaway SQLite database so it needs no server. Every test gets
its own freshly-registered user, so ownership tests are meaningful and no test depends on
another test's state.
"""
from __future__ import annotations

import datetime as dt
import os
import tempfile
import uuid
from pathlib import Path

import pytest

# Configuration must be in place BEFORE the application modules are imported, because
# settings and the engine are cached on first use.
_TMP = Path(tempfile.mkdtemp(prefix="goalpilot-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["GOALPILOT_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production-use-only-0123456789"
os.environ["EXPOSE_RESET_TOKEN"] = "true"
os.environ["BCRYPT_ROUNDS"] = "4"  # keep hashing fast in tests
os.environ["RATE_LIMIT_AUTH_PER_MINUTE"] = "0"  # the limiter has its own unit test
os.environ["RATE_LIMIT_OPTIMIZE_PER_MINUTE"] = "0"
# The suite must be deterministic and offline. Providers are exercised against recorded
# fixtures in test_providers.py, which re-enables them per test via monkeypatch.
os.environ["GOALPILOT_ENABLE_LIVE_PROVIDERS"] = "false"
os.environ["GOALPILOT_ENABLE_MFAPI_HISTORY"] = "false"
os.environ["GOALPILOT_ENABLE_LLM"] = "false"
# Never load a developer's real backend/.env during tests: it would make the suite depend on
# local state and could leak a key into a test process.
os.environ["GOALPILOT_SKIP_DOTENV"] = "1"
os.environ.pop("GEMINI_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.db import create_all, get_engine, get_session_factory, reset_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    reset_engine()
    create_all()
    yield
    get_engine().dispose()


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


TEST_PASSWORD = "Str0ng-Passw0rd!"


@pytest.fixture()
def registered(client: TestClient) -> dict:
    """A registered, authenticated user. Returns a bundle of client, token and user."""
    email = unique_email()
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": TEST_PASSWORD, "full_name": "Test User"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return {
        "client": client,
        "email": email,
        "password": TEST_PASSWORD,
        "token": body["access_token"],
        "user": body["user"],
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
    }


@pytest.fixture()
def admin(registered) -> dict:
    """The same registered user, promoted to administrator.

    Promotion happens in the database, which is what the authorisation dependency reads, so the
    existing token keeps working and the test exercises the real check.
    """
    with get_session_factory()() as db:
        user = db.execute(select(User).where(User.email == registered["email"])).scalar_one()
        user.is_admin = True
        db.commit()
    registered["user"]["is_admin"] = True
    return registered


@pytest.fixture()
def second_user(client: TestClient) -> dict:
    email = unique_email("other")
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": TEST_PASSWORD, "full_name": "Other User"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return {
        "client": client,
        "email": email,
        "password": TEST_PASSWORD,
        "token": body["access_token"],
        "user": body["user"],
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
    }


# --------------------------------------------------------------------------------------
# domain fixtures
# --------------------------------------------------------------------------------------
def seed_profile_and_goal(user: dict, *, goals: int = 2, cash: float = 420_000) -> dict:
    """Create a complete, ready-to-plan financial profile for a user."""
    headers = user["headers"]
    client = user["client"]

    profile = client.put(
        "/api/profile",
        headers=headers,
        json={
            "monthly_income": 90_000,
            "essential_expenses": 42_000,
            "discretionary_expenses": 6_000,
            "monthly_savings_target": 15_000,
            "emergency_months": 6,
            "emi_income_ratio_cap": 0.35,
            "risk_capacity": 0.55,
            "inflation_assumption": 0.03,
            "investment_return_assumption": 0.05,
            "savings_return_assumption": 0.0,
            "loan_interest_assumption": 0.12,
        },
    )
    assert profile.status_code == 200, profile.text

    income = client.post(
        "/api/income-sources",
        headers=headers,
        json={
            "source_type": "salary",
            "label": "Primary salary",
            "amount": 90_000,
            "frequency": "monthly",
            "stability": "stable",
            "is_recurring": True,
        },
    )
    assert income.status_code == 201, income.text

    asset = client.post(
        "/api/assets",
        headers=headers,
        json={
            "asset_type": "liquid_savings",
            "label": "Savings account",
            "current_value": cash,
            "is_liquid": True,
            "usable_for_goals": True,
        },
    )
    assert asset.status_code == 201, asset.text

    liability = client.post(
        "/api/liabilities",
        headers=headers,
        json={
            "liability_type": "personal_loan",
            "label": "Personal loan",
            "outstanding_principal": 600_000,
            "annual_interest_rate": 0.12,
            "emi_amount": 12_000,
            "remaining_tenure_months": 60,
        },
    )
    assert liability.status_code == 201, liability.text

    today = dt.date.today()
    created = []
    specs = [
        ("Professional certification", 90_000, 365, 4, 5),
        ("Vehicle down payment", 300_000, 1095, 3, 3),
        ("Emergency fund top-up", 200_000, 730, 5, 5),
        ("Family holiday", 150_000, 1460, 2, 2),
    ]
    for i in range(min(goals, len(specs))):
        name, cost, days, priority, criticality = specs[i]
        response = client.post(
            "/api/goals",
            headers=headers,
            json={
                "name": name,
                "purpose": f"Planned {name.lower()}",
                "goal_type": "custom",
                "current_cost": cost,
                "target_date": (today + dt.timedelta(days=days)).isoformat(),
                "current_funded_amount": 10_000,
                "priority": priority,
                "criticality": criticality,
                "date_flexible": True,
                "amount_flexible": False,
            },
        )
        assert response.status_code == 201, response.text
        created.append(response.json())
    return {"profile": profile.json(), "goals": created}
