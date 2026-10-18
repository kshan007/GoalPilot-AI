"""Administrative access is a property of the account, not of knowing the URL."""
from __future__ import annotations


def test_admin_login_rejects_a_normal_account(registered):
    response = registered["client"].post(
        "/api/auth/admin/login",
        json={"email": registered["email"], "password": registered["password"]},
    )
    assert response.status_code == 401
    assert "administrative" in response.json()["error"]["message"].lower()


def test_admin_login_refuses_a_wrong_password(registered):
    response = registered["client"].post(
        "/api/auth/admin/login",
        json={"email": registered["email"], "password": "definitely-not-it"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Incorrect email or password."


def test_promoted_account_can_use_the_admin_door(admin):
    response = admin["client"].post(
        "/api/auth/admin/login",
        json={"email": admin["email"], "password": admin["password"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["is_admin"] is True


def test_admin_flag_is_visible_on_the_session(admin):
    me = admin["client"].get("/api/auth/me", headers=admin["headers"]).json()
    assert me["is_admin"] is True


def test_normal_account_is_refused_admin_only_data(registered):
    response = registered["client"].get("/api/models/registry", headers=registered["headers"])
    assert response.status_code == 403


def test_administrator_can_read_admin_only_data(admin):
    response = admin["client"].get("/api/models/registry", headers=admin["headers"])
    assert response.status_code == 200
    assert "entries" in response.json()


def test_unauthenticated_callers_cannot_read_admin_only_data(client):
    assert client.get("/api/models/registry").status_code == 401

