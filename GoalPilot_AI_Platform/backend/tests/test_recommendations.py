"""Structured recommendations: grounding checks, fallback, persistence and isolation.

The central claim under test is that **the language model cannot change a number**. The tests
attack that claim from three sides: valid text is merged but never trusted for amounts, invalid
text is rejected outright, and with no model at all the response is still complete.
"""
from __future__ import annotations

import json

import pytest

from app.llm import gemini_client
from app.llm.gemini_client import LLMResult, LLMUnavailable
from app.models import RecommendationRun
from app.schemas.recommendations import LLMText
from app.services import recommendations as service
from tests.conftest import seed_profile_and_goal

REQUIRED_KEYS = {
    "schema_version",
    "financial_summary",
    "cash_flow_status",
    "protected_buffer",
    "available_goal_budget",
    "goal_recommendations",
    "investment_options",
    "loan_options",
    "recommended_plan",
    "alternative_scenarios",
    "risks_and_warnings",
    "data_sources",
    "assumptions",
    "missing_information",
    "monthly_actions",
    "explanation",
    "disclaimer",
    "llm",
    "validation",
}


def _text(**overrides) -> LLMText:
    base = {
        "financial_summary": "Your plan is described below.",
        "cash_flow_explanation": "Surplus is income minus committed spending.",
        "plan_explanation": "The optimiser allocated the available goal budget.",
    }
    base.update(overrides)
    return LLMText.model_validate(base)


FACTS = {"cash_flow": {"monthly_surplus": 50000, "protected_buffer": 15000}}


# --------------------------------------------------------------------- grounding checks
def test_grounded_text_passes():
    text = _text(financial_summary="Your surplus is Rs 50,000 and the buffer is Rs 15,000.")
    ok, problems = service.validate_llm_text(
        text, facts=FACTS, goal_refs={"G1"}, product_ids={"p1"}
    )
    assert ok, problems


def test_guarantee_language_is_rejected():
    text = _text(financial_summary="Your returns are guaranteed at 12%.")
    ok, problems = service.validate_llm_text(text, facts=FACTS, goal_refs=set(), product_ids=set())
    assert not ok
    assert any(p.startswith("banned_phrase") for p in problems)


def test_risk_free_phrasing_is_rejected():
    text = _text(plan_explanation="This is a risk-free way to reach the goal.")
    ok, problems = service.validate_llm_text(text, facts=FACTS, goal_refs=set(), product_ids=set())
    assert not ok
    assert any("risk-free" in p for p in problems)


def test_invented_amount_is_rejected():
    text = _text(financial_summary="You will have Rs 99,999 spare each month.")
    ok, problems = service.validate_llm_text(text, facts=FACTS, goal_refs=set(), product_ids=set())
    assert not ok
    assert any(p.startswith("ungrounded_amount") for p in problems)


def test_unknown_goal_and_product_references_are_rejected():
    text = _text(
        goal_reasons=[{"goal_ref": "G99", "reason": "This goal matters."}],
        investment_commentary=[{"product_id": "made-up", "commentary": "Good fit."}],
    )
    ok, problems = service.validate_llm_text(
        text, facts=FACTS, goal_refs={"G1"}, product_ids={"p1"}
    )
    assert not ok
    assert any("unknown_goal_ref" in p for p in problems)
    assert any("unknown_product_id" in p for p in problems)


def test_numbers_inside_text_without_currency_are_tolerated():
    # "in 3 years" is not a money claim and must not be treated as one.
    text = _text(plan_explanation="The plan covers 3 goals over 5 years.")
    ok, _ = service.validate_llm_text(text, facts=FACTS, goal_refs=set(), product_ids=set())
    assert ok


# ------------------------------------------------------------------------- generation
def test_generation_without_a_model_still_returns_a_complete_response(registered):
    seed_profile_and_goal(registered, goals=3)
    response = registered["client"].post(
        "/api/recommendations/generate",
        headers=registered["headers"],
        json={"include_investments": True, "include_loans": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert REQUIRED_KEYS <= set(body)
    assert body["llm"]["used"] is False
    assert body["llm"]["status"] == "fallback"
    assert body["llm"]["reason"] in {"gemini_not_configured", "llm_disabled", "sdk_unavailable"}
    assert body["validation"]["model_supplied_numbers"] is False
    assert body["disclaimer"]
    assert len(body["goal_recommendations"]) == 3


def test_response_numbers_are_internally_consistent(registered):
    seed_profile_and_goal(registered, goals=3)
    body = registered["client"].post(
        "/api/recommendations/generate", headers=registered["headers"], json={}
    ).json()

    cf = body["cash_flow_status"]
    # buffer + goal budget can never exceed the surplus that exists.
    assert cf["protected_buffer"] + cf["available_goal_budget"] <= max(0.0, cf["monthly_surplus"]) + 0.01
    assert body["available_goal_budget"] == pytest.approx(cf["available_goal_budget"])

    planned = sum(
        g["planned_savings_contribution"] + g["planned_investment_contribution"]
        for g in body["goal_recommendations"]
    )
    assert planned <= cf["available_goal_budget"] + 1.0

    for goal in body["goal_recommendations"]:
        assert goal["funding_status"] in {"fully_funded", "underfunded", "already_funded"}
        if goal["funding_status"] == "underfunded":
            assert goal["expected_shortfall"] > 0
        assert goal["reason"]


def test_a_goal_is_never_called_funded_when_it_is_short(registered):
    seed_profile_and_goal(registered, goals=3)
    body = registered["client"].post(
        "/api/recommendations/generate", headers=registered["headers"], json={}
    ).json()
    for goal in body["goal_recommendations"]:
        if goal["funding_status"] == "fully_funded":
            assert goal["expected_shortfall"] <= 1.0
            assert goal["achievement_ratio"] >= 0.99 or goal["funding_gap"] <= 0


def test_engine_disclosures_are_not_listed_as_risks(registered):
    seed_profile_and_goal(registered, goals=2)
    body = registered["client"].post(
        "/api/recommendations/generate", headers=registered["headers"], json={}
    ).json()
    for risk in body["risks_and_warnings"]:
        assert "capacity is capped" not in risk.lower()
    for note in body["technical_notes"]:
        assert isinstance(note, str) and note


# ------------------------------------------------------------------- mocked model paths
def _patch_model(monkeypatch, raw: dict):
    monkeypatch.setattr(gemini_client, "available", lambda: True)
    monkeypatch.setattr(
        gemini_client,
        "generate_json",
        lambda *_a, **_k: LLMResult(text=json.dumps(raw), model="test-model", latency_ms=12, raw=raw),
    )


def test_valid_model_text_is_used_but_cannot_change_numbers(registered, monkeypatch):
    seed_profile_and_goal(registered, goals=2)
    baseline = registered["client"].post(
        "/api/recommendations/generate",
        headers=registered["headers"],
        json={"include_investments": False, "include_loans": False},
    ).json()

    _patch_model(
        monkeypatch,
        {
            "financial_summary": "A model wrote this summary.",
            "cash_flow_explanation": "A model wrote this cash-flow note.",
            "plan_explanation": "A model wrote this plan note.",
            "risks": ["A model-authored risk."],
            "monthly_actions": ["Transfer the buffer first."],
        },
    )
    body = registered["client"].post(
        "/api/recommendations/generate",
        headers=registered["headers"],
        json={"include_investments": False, "include_loans": False},
    ).json()

    assert body["llm"]["used"] is True
    assert body["llm"]["status"] == "ok"
    assert body["financial_summary"] == "A model wrote this summary."
    assert "A model-authored risk." in body["risks_and_warnings"]
    # Numbers must be identical to the run the model never touched.
    assert body["cash_flow_status"] == baseline["cash_flow_status"]
    assert body["available_goal_budget"] == baseline["available_goal_budget"]
    assert [g["planned_savings_contribution"] for g in body["goal_recommendations"]] == [
        g["planned_savings_contribution"] for g in baseline["goal_recommendations"]
    ]


def test_model_text_with_a_guarantee_is_discarded(registered, monkeypatch):
    seed_profile_and_goal(registered, goals=1)
    _patch_model(
        monkeypatch,
        {
            "financial_summary": "Your returns are guaranteed.",
            "cash_flow_explanation": "x",
            "plan_explanation": "y",
        },
    )
    body = registered["client"].post(
        "/api/recommendations/generate", headers=registered["headers"], json={}
    ).json()
    assert body["llm"]["used"] is False
    assert body["llm"]["status"] == "rejected"
    assert body["llm"]["reason"] == "validation_failed"
    assert "guaranteed" not in body["financial_summary"].lower()


def test_model_timeout_falls_back_cleanly(registered, monkeypatch):
    seed_profile_and_goal(registered, goals=1)
    monkeypatch.setattr(gemini_client, "available", lambda: True)

    def boom(*_a, **_k):
        raise LLMUnavailable("timeout", "deadline exceeded")

    monkeypatch.setattr(gemini_client, "generate_json", boom)
    response = registered["client"].post(
        "/api/recommendations/generate", headers=registered["headers"], json={}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["llm"]["status"] == "fallback"
    assert body["llm"]["reason"] == "timeout"
    assert body["financial_summary"]


def test_model_schema_violation_falls_back(registered, monkeypatch):
    seed_profile_and_goal(registered, goals=1)
    _patch_model(monkeypatch, {"unexpected": "shape"})
    body = registered["client"].post(
        "/api/recommendations/generate", headers=registered["headers"], json={}
    ).json()
    assert body["llm"]["status"] == "rejected"
    assert body["llm"]["reason"] == "schema_invalid"


# ------------------------------------------------------------------ persistence / ask
def test_persisted_payload_round_trips_without_type_corruption(registered):
    seed_profile_and_goal(registered, goals=2)
    created = registered["client"].post(
        "/api/recommendations/generate", headers=registered["headers"], json={}
    ).json()
    assert created["run_id"]

    stored = registered["client"].get(
        "/api/recommendations/latest", headers=registered["headers"]
    ).json()
    assert isinstance(stored["cash_flow_status"], dict), "nested models must not be stringified"
    assert isinstance(stored["protected_buffer"], dict)
    assert stored["cash_flow_status"] == created["cash_flow_status"]
    assert stored["financial_summary"] == created["financial_summary"]

    by_id = registered["client"].get(
        f"/api/recommendations/{created['run_id']}", headers=registered["headers"]
    )
    assert by_id.status_code == 200
    assert by_id.json()["run_id"] == created["run_id"]


def test_history_lists_runs(registered):
    seed_profile_and_goal(registered, goals=1)
    registered["client"].post("/api/recommendations/generate", headers=registered["headers"], json={})
    body = registered["client"].get(
        "/api/recommendations/history", headers=registered["headers"]
    ).json()
    assert body["items"]
    assert body["items"][0]["schema_version"] == service.SCHEMA_VERSION
    assert body["items"][0]["fallback_used"] is True


def test_ask_answers_from_computed_data_without_a_model(registered):
    seed_profile_and_goal(registered, goals=1)
    created = registered["client"].post(
        "/api/recommendations/generate", headers=registered["headers"], json={}
    ).json()
    buffer = created["protected_buffer"]["protected_monthly_buffer"]

    response = registered["client"].post(
        "/api/recommendations/ask",
        headers=registered["headers"],
        json={"question": "What is my savings buffer?"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["llm"]["used"] is False
    assert f"{buffer:,.0f}" in body["answer"]
    assert body["disclaimer"]


def test_ask_requires_a_stored_recommendation(registered):
    seed_profile_and_goal(registered, goals=1)
    response = registered["client"].post(
        "/api/recommendations/ask",
        headers=registered["headers"],
        json={"question": "What is my buffer?"},
    )
    assert response.status_code in (409, 422), response.text


def test_recommendations_are_isolated_between_users(registered):
    seed_profile_and_goal(registered, goals=1)
    created = registered["client"].post(
        "/api/recommendations/generate", headers=registered["headers"], json={}
    ).json()

    other = registered["client"].post(
        "/api/auth/register",
        json={"email": "other-rec@example.com", "password": "Str0ng-Passw0rd!", "full_name": "Other"},
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    assert registered["client"].get(
        f"/api/recommendations/{created['run_id']}", headers=other_headers
    ).status_code in (403, 404)


def test_generate_requires_authentication(client):
    assert client.post("/api/recommendations/generate", json={}).status_code == 401


def test_status_reports_fallback_configuration(client):
    body = client.get("/api/recommendations/status").json()
    assert body["fallback_available"] is True
    assert body["llm"]["key_env_var"] == "GEMINI_API_KEY"
    assert "sk-" not in json.dumps(body).lower()

# ------------------------------------------------------- prose sanitation (live path)
def test_ungrounded_sentence_is_dropped_but_the_rest_survives():
    from app.services.recommendations import sanitize_ungrounded

    text = _text(
        financial_summary=(
            "Your surplus is Rs 50,000 each month. "
            "Over the horizon this becomes Rs 3,60,000. "
            "The buffer is Rs 15,000."
        )
    )
    cleaned, removed = sanitize_ungrounded(text, facts=FACTS)
    assert "Rs 50,000" in cleaned.financial_summary
    assert "Rs 15,000" in cleaned.financial_summary
    assert "3,60,000" not in cleaned.financial_summary
    assert len(removed) == 1
    assert all("3,60,000" not in sentence for sentence in [cleaned.financial_summary])


def test_grounded_text_is_left_untouched():
    from app.services.recommendations import sanitize_ungrounded

    original = _text(financial_summary="Your surplus is Rs 50,000. The buffer is Rs 15,000.")
    cleaned, removed = sanitize_ungrounded(original, facts=FACTS)
    assert removed == []
    assert cleaned.financial_summary == original.financial_summary


def test_list_items_with_invented_amounts_are_dropped():
    from app.services.recommendations import sanitize_ungrounded

    text = _text(monthly_actions=["Move Rs 15,000 to the buffer.", "Invest Rs 99,999 this month."])
    cleaned, removed = sanitize_ungrounded(text, facts=FACTS)
    assert cleaned.monthly_actions == ["Move Rs 15,000 to the buffer."]
    assert len(removed) == 1
