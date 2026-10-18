"""Administrative API: access control, real metrics, run history and audit trail."""
from __future__ import annotations

from tests.conftest import seed_profile_and_goal


def _plan(user: dict, algorithm: str = "lp") -> dict:
    response = user["client"].post(
        "/api/optimize/plan", headers=user["headers"], json={"algorithm": algorithm}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_admin_endpoints_require_authentication(client):
    assert client.get("/api/admin/overview").status_code == 401


def test_admin_endpoints_refuse_ordinary_users(registered):
    for path in ("/api/admin/overview", "/api/admin/runs", "/api/admin/users", "/api/admin/health"):
        response = registered["client"].get(path, headers=registered["headers"])
        assert response.status_code == 403, f"{path} returned {response.status_code}"


def test_overview_reports_measured_counts(admin):
    seed_profile_and_goal(admin)
    body = _plan(admin)

    response = admin["client"].get("/api/admin/overview", headers=admin["headers"])
    assert response.status_code == 200
    overview = response.json()

    assert overview["users"]["total"] >= 1
    assert overview["users"]["admins"] >= 1
    assert overview["runs"]["total"] >= 1
    assert overview["runs"]["by_algorithm"]["lp"] >= 1
    assert sum(point["runs"] for point in overview["activity"]) >= 1
    assert body["run_id"] >= 1


def test_run_history_paginates_and_filters(admin):
    seed_profile_and_goal(admin, goals=1)
    first = _plan(admin)
    _plan(admin)

    page = admin["client"].get(
        "/api/admin/runs?page=1&page_size=1", headers=admin["headers"]
    ).json()
    assert page["page_size"] == 1
    assert page["total"] >= 2
    assert page["pages"] >= 2
    assert len(page["items"]) == 1
    # Newest first.
    assert page["items"][0]["id"] >= first["run_id"]

    filtered = admin["client"].get(
        "/api/admin/runs?algorithm=rl", headers=admin["headers"]
    ).json()
    assert all(item["algorithm"] == "rl" for item in filtered["items"])

    # Search matches a run id OR an account email, so a numeric query can legitimately return
    # more than one row; the run itself must always be present.
    by_id = admin["client"].get(
        f"/api/admin/runs?search={first['run_id']}", headers=admin["headers"]
    ).json()
    assert by_id["total"] >= 1
    assert first["run_id"] in [item["id"] for item in by_id["items"]]


def test_run_detail_exposes_diagnostics_but_not_private_finances(admin):
    seed_profile_and_goal(admin, goals=1)
    plan = _plan(admin)

    response = admin["client"].get(
        f"/api/admin/runs/{plan['run_id']}", headers=admin["headers"]
    )
    assert response.status_code == 200
    detail = response.json()

    assert detail["allocations"]
    assert detail["summary"] is not None
    # The account's private financial data must never travel with the diagnostic view.
    for forbidden in ("income_sources", "assets", "liabilities", "transactions", "password_hash"):
        assert forbidden not in detail

    missing = admin["client"].get("/api/admin/runs/999999", headers=admin["headers"])
    assert missing.status_code == 422


def test_inspecting_a_run_is_audited(admin):
    seed_profile_and_goal(admin, goals=1)
    plan = _plan(admin)
    admin["client"].get(f"/api/admin/runs/{plan['run_id']}", headers=admin["headers"])

    audit = admin["client"].get("/api/admin/audit", headers=admin["headers"]).json()
    actions = [entry["action"] for entry in audit["items"]]
    assert "run.inspect" in actions

    # Opening the same run immediately again is one action, not two (React double-mounts in
    # development; the audit log must not double-count it). Count entries for *this* run only:
    # earlier tests in the same database have their own inspection rows.
    admin["client"].get(f"/api/admin/runs/{plan['run_id']}", headers=admin["headers"])
    again = admin["client"].get("/api/admin/audit", headers=admin["headers"]).json()
    for_this_run = [
        entry
        for entry in again["items"]
        if entry["action"] == "run.inspect" and entry["target_id"] == str(plan["run_id"])
    ]
    assert len(for_this_run) == 1


def test_user_listing_and_role_changes_are_audited(admin, second_user):
    listing = admin["client"].get("/api/admin/users", headers=admin["headers"])
    assert listing.status_code == 200
    assert listing.json()["total"] >= 2
    assert all("password_hash" not in item for item in listing.json()["items"])

    target = next(
        item for item in listing.json()["items"] if item["email"] == second_user["email"]
    )
    promoted = admin["client"].patch(
        f"/api/admin/users/{target['id']}",
        headers=admin["headers"],
        json={"is_admin": True},
    )
    assert promoted.status_code == 200
    assert promoted.json()["is_admin"] is True

    audit = admin["client"].get("/api/admin/audit", headers=admin["headers"]).json()
    update = next(entry for entry in audit["items"] if entry["action"] == "user.update")
    assert update["details"]["after"]["is_admin"] is True
    assert update["details"]["before"]["is_admin"] is False


def test_administrator_cannot_change_their_own_access(admin):
    me = admin["client"].get("/api/auth/me", headers=admin["headers"]).json()
    response = admin["client"].patch(
        f"/api/admin/users/{me['id']}",
        headers=admin["headers"],
        json={"is_admin": False},
    )
    assert response.status_code == 422
    assert "your own" in response.json()["error"]["message"].lower()


def test_data_and_assumptions_are_read_only(admin):
    body = admin["client"].get("/api/admin/data", headers=admin["headers"]).json()
    assert body["datasets"]
    assert body["defaults"]["annual_inflation"] >= 0
    assert body["editing"]["supported"] is False
    assert body["editing"]["reason"]


def test_health_reports_real_database_state(admin):
    body = admin["client"].get("/api/admin/health", headers=admin["headers"]).json()
    assert body["database"]["reachable"] is True
    assert "models" in body
    assert body["optimization"]["failed_runs"] >= 0

