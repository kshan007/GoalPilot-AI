"""Unhandled errors must reach the browser as readable JSON, not as a network failure."""
from __future__ import annotations

import pytest


def test_unhandled_error_returns_json_with_cors_headers(registered, monkeypatch):
    from app.api import profile as profile_api

    def boom(*_args, **_kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("app.services.planner.get_profile_or_none", boom)

    response = registered["client"].get(
        "/api/profile/summary",
        headers={**registered["headers"], "Origin": "http://localhost:5173"},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "not applied" in body["error"]["message"]
    # Without this header the browser discards the body and reports a network error, which is
    # how a real 500 was misdiagnosed as "the API is down".
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_unhandled_error_has_no_cors_header_for_an_unlisted_origin(registered, monkeypatch):
    from app.api import profile as profile_api

    def boom(*_args, **_kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("app.services.planner.get_profile_or_none", boom)

    response = registered["client"].get(
        "/api/profile/summary",
        headers={**registered["headers"], "Origin": "http://evil.example"},
    )
    assert response.status_code == 500
    assert response.headers.get("access-control-allow-origin") is None


def test_error_body_never_leaks_internals(registered, monkeypatch):
    from app.api import profile as profile_api

    def boom(*_args, **_kwargs):
        raise RuntimeError("connection string postgres://user:secret@host/db")

    monkeypatch.setattr("app.services.planner.get_profile_or_none", boom)

    response = registered["client"].get(
        "/api/profile/summary", headers=registered["headers"]
    )
    assert response.status_code == 500
    serialized = response.text
    assert "secret" not in serialized
    assert "postgres://" not in serialized
    assert response.json()["error"]["detail"] == "RuntimeError"

