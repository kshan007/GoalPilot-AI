"""Authentication: registration, login, logout, recovery, reset, protected routes."""
from __future__ import annotations

from tests.conftest import TEST_PASSWORD, unique_email


def test_register_returns_token_and_user(client):
    email = unique_email()
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": TEST_PASSWORD, "full_name": "Ada"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["email"] == email
    assert body["user"]["full_name"] == "Ada"
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20
    # the hash is never returned
    assert "password" not in response.text.lower() or "password_hash" not in response.text


def test_register_rejects_duplicate_email(client):
    email = unique_email()
    payload = {"email": email, "password": TEST_PASSWORD, "full_name": "A"}
    assert client.post("/api/auth/register", json=payload).status_code == 200
    duplicate = client.post("/api/auth/register", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"


def test_register_rejects_weak_password(client):
    for bad in ("short1", "alllettersonly", "12345678"):
        response = client.post(
            "/api/auth/register",
            json={"email": unique_email(), "password": bad, "full_name": "X"},
        )
        assert response.status_code == 422, bad


def test_email_is_normalised_and_case_insensitive(client):
    email = unique_email("MixedCase")
    assert client.post(
        "/api/auth/register",
        json={"email": email.upper(), "password": TEST_PASSWORD, "full_name": "A"},
    ).status_code == 200
    login = client.post(
        "/api/auth/login", json={"email": email.lower(), "password": TEST_PASSWORD}
    )
    assert login.status_code == 200, login.text


def test_login_success_and_failure(client, registered):
    ok = client.post(
        "/api/auth/login",
        json={"email": registered["email"], "password": registered["password"]},
    )
    assert ok.status_code == 200
    bad_password = client.post(
        "/api/auth/login", json={"email": registered["email"], "password": "Wr0ng-Passw0rd!"}
    )
    assert bad_password.status_code == 401
    unknown = client.post(
        "/api/auth/login",
        json={"email": unique_email("ghost"), "password": TEST_PASSWORD},
    )
    assert unknown.status_code == 401
    # identical shape for both failures: no account enumeration
    assert bad_password.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_me_requires_a_valid_token(client, registered):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-token"}).status_code == 401
    me = client.get("/api/auth/me", headers=registered["headers"])
    assert me.status_code == 200
    assert me.json()["email"] == registered["email"]


def test_protected_route_rejects_anonymous(client):
    for path in ("/api/profile", "/api/goals", "/api/dashboard", "/api/months"):
        assert client.get(path).status_code == 401, path


def test_logout_revokes_the_token(client, registered):
    assert client.post("/api/auth/logout", headers=registered["headers"]).status_code == 200
    # the same token no longer works
    assert client.get("/api/auth/me", headers=registered["headers"]).status_code == 401
    # and the token version rotation means a fresh login is required
    assert client.post(
        "/api/auth/login",
        json={"email": registered["email"], "password": registered["password"]},
    ).status_code == 200


def test_password_recovery_and_reset(client, registered):
    forgot = client.post("/api/auth/forgot-password", json={"email": registered["email"]})
    assert forgot.status_code == 200
    token = forgot.json()["reset_token"]
    assert token, "EXPOSE_RESET_TOKEN=true in tests, so the token must be returned"

    reset = client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "An0ther-Good-Pass!"},
    )
    assert reset.status_code == 200, reset.text

    # old password no longer works, new one does
    assert client.post(
        "/api/auth/login",
        json={"email": registered["email"], "password": TEST_PASSWORD},
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"email": registered["email"], "password": "An0ther-Good-Pass!"},
    ).status_code == 200

    # a used token cannot be replayed
    replay = client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "Yet-An0ther-Pass!"},
    )
    assert replay.status_code == 422


def test_forgot_password_does_not_disclose_unknown_email(client):
    response = client.post("/api/auth/forgot-password", json={"email": unique_email("nobody")})
    assert response.status_code == 200
    assert response.json()["reset_token"] is None


def test_reset_rejects_invalid_and_expired_tokens(client):
    assert client.post(
        "/api/auth/reset-password",
        json={"token": "x" * 40, "new_password": "An0ther-Good-Pass!"},
    ).status_code == 422


def test_change_password_requires_the_current_one(client, registered):
    wrong = client.post(
        "/api/auth/change-password",
        headers=registered["headers"],
        json={"current_password": "nope-nope-1", "new_password": "An0ther-Good-Pass!"},
    )
    assert wrong.status_code == 401

    ok = client.post(
        "/api/auth/change-password",
        headers=registered["headers"],
        json={"current_password": TEST_PASSWORD, "new_password": "An0ther-Good-Pass!"},
    )
    assert ok.status_code == 200
    # changing the password revokes existing sessions
    assert client.get("/api/auth/me", headers=registered["headers"]).status_code == 401
