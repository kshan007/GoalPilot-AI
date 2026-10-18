"""Cross-user isolation: one user must not read, modify or delete another's data."""
from __future__ import annotations

import datetime as dt

from tests.conftest import seed_profile_and_goal


def test_goals_are_not_visible_across_users(client, registered, second_user):
    seed_profile_and_goal(registered, goals=2)
    seed_profile_and_goal(second_user, goals=1)

    mine = client.get("/api/goals", headers=registered["headers"]).json()
    theirs = client.get("/api/goals", headers=second_user["headers"]).json()
    assert len(mine) == 2
    assert len(theirs) == 1
    assert {g["id"] for g in mine}.isdisjoint({g["id"] for g in theirs})


def test_reading_another_users_goal_is_404(client, registered, second_user):
    seed_profile_and_goal(second_user, goals=1)
    victim_goal = client.get("/api/goals", headers=second_user["headers"]).json()[0]

    response = client.get(f"/api/goals/{victim_goal['id']}", headers=registered["headers"])
    # 404 rather than 403: the platform does not disclose that the row exists.
    assert response.status_code == 404


def test_cannot_modify_or_delete_another_users_goal(client, registered, second_user):
    seed_profile_and_goal(second_user, goals=1)
    victim_goal = client.get("/api/goals", headers=second_user["headers"]).json()[0]
    goal_id = victim_goal["id"]

    assert client.put(
        f"/api/goals/{goal_id}", headers=registered["headers"], json={"name": "hijacked"}
    ).status_code == 404
    assert client.delete(
        f"/api/goals/{goal_id}", headers=registered["headers"]
    ).status_code == 404

    # unchanged for the real owner
    still_there = client.get(f"/api/goals/{goal_id}", headers=second_user["headers"])
    assert still_there.status_code == 200
    assert still_there.json()["name"] == victim_goal["name"]


def test_cannot_touch_another_users_income_asset_or_liability(client, registered, second_user):
    seed_profile_and_goal(second_user)
    income = client.get("/api/income-sources", headers=second_user["headers"]).json()[0]
    asset = client.get("/api/assets", headers=second_user["headers"]).json()[0]
    liability = client.get("/api/liabilities", headers=second_user["headers"]).json()[0]

    assert client.delete(
        f"/api/income-sources/{income['id']}", headers=registered["headers"]
    ).status_code == 404
    assert client.delete(
        f"/api/assets/{asset['id']}", headers=registered["headers"]
    ).status_code == 404
    assert client.delete(
        f"/api/liabilities/{liability['id']}", headers=registered["headers"]
    ).status_code == 404


def test_monthly_records_are_isolated(client, registered, second_user):
    seed_profile_and_goal(registered)
    seed_profile_and_goal(second_user)
    period = dt.date.today().strftime("%Y-%m")

    assert client.post(
        f"/api/months/{period}/open", headers=registered["headers"]
    ).status_code == 200
    # the other user has not opened the month, so it does not exist for them
    assert client.get(
        f"/api/months/{period}", headers=second_user["headers"]
    ).status_code == 422

    mine = client.get("/api/months", headers=registered["headers"]).json()
    theirs = client.get("/api/months", headers=second_user["headers"]).json()
    assert len(mine) == 1 and len(theirs) == 0


def test_cannot_use_another_users_goal_as_an_asset_earmark(client, registered, second_user):
    seed_profile_and_goal(second_user, goals=1)
    victim_goal = client.get("/api/goals", headers=second_user["headers"]).json()[0]

    response = client.post(
        "/api/assets",
        headers=registered["headers"],
        json={
            "asset_type": "investment",
            "label": "Sneaky",
            "current_value": 1000,
            "earmarked_goal_id": victim_goal["id"],
        },
    )
    assert response.status_code == 404


def test_optimisation_runs_are_isolated(client, registered, second_user):
    seed_profile_and_goal(registered)
    seed_profile_and_goal(second_user)

    mine = client.post("/api/optimize/plan", headers=registered["headers"], json={"algorithm": "lp"})
    assert mine.status_code == 200, mine.text
    run_id = mine.json()["run_id"]

    assert client.get(f"/api/optimize/runs/{run_id}", headers=registered["headers"]).status_code == 200
    assert client.get(f"/api/optimize/runs/{run_id}", headers=second_user["headers"]).status_code == 404

    other_runs = client.get("/api/optimize/runs", headers=second_user["headers"]).json()
    assert other_runs["items"] == []


def test_account_export_contains_only_owned_records(client, registered, second_user):
    seed_profile_and_goal(registered, goals=2)
    seed_profile_and_goal(second_user, goals=3)

    export = client.get("/api/account/export", headers=registered["headers"]).json()
    assert len(export["goals"]) == 2
    assert export["account"]["email"] == registered["email"]
    assert "password_hash" not in str(export)


def test_account_deletion_requires_confirmation_and_cascades(client, registered, second_user):
    seed_profile_and_goal(registered)

    guarded = client.delete("/api/account", headers=registered["headers"])
    assert guarded.status_code == 422
    assert client.get("/api/auth/me", headers=registered["headers"]).status_code == 200

    deleted = client.delete("/api/account?confirm=DELETE", headers=registered["headers"])
    assert deleted.status_code == 200
    assert client.get("/api/auth/me", headers=registered["headers"]).status_code == 401
    # the other account is untouched
    assert client.get("/api/auth/me", headers=second_user["headers"]).status_code == 200
