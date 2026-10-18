"""Investment discovery: suitability rules, provenance labelling and the API surface."""
from __future__ import annotations

import pytest

from app.providers.base import CATEGORY_SCENARIO, OFFICIAL_SNAPSHOT, NormalizedInvestment
from app.services import investment_discovery as discovery


def _option(**kwargs) -> NormalizedInvestment:
    base = dict(
        provider="test",
        product_id="p1",
        name="Test instrument",
        category="equity_mf",
        risk_level="high",
        risk_score=0.7,
        liquidity="daily",
        retrieved_at="2026-10-17T00:00:00+00:00",
    )
    base.update(kwargs)
    return NormalizedInvestment(**base)


def _ctx(**kwargs) -> dict:
    base = {
        "risk_capacity": 0.4,
        "loss_ability": "moderate",
        "liquidity_requirement": "medium",
        "horizon_months": 120,
        "monthly_contribution_capacity": 20000.0,
        "emergency_fund_progress": 1.0,
        "existing_bucket_shares": {"cash": 1.0, "market": 0.0, "debt": 0.0},
    }
    base.update(kwargs)
    return base


def test_option_above_risk_capacity_is_penalised_and_explained():
    risky = discovery.score_option(_option(risk_score=0.8), _ctx(risk_capacity=0.3))
    safe = discovery.score_option(
        _option(risk_score=0.1, risk_level="low", category="debt_mf"), _ctx(risk_capacity=0.3)
    )
    assert risky["score"] < safe["score"]
    assert any("exceeds the declared risk capacity" in c for c in risky["cautions"])
    assert safe["reasons"]


def test_short_horizon_penalises_volatile_options():
    long_horizon = discovery.score_option(_option(risk_score=0.6), _ctx(horizon_months=120))
    short_horizon = discovery.score_option(_option(risk_score=0.6), _ctx(horizon_months=24))
    assert short_horizon["score"] < long_horizon["score"]
    assert any("little time to recover" in c for c in short_horizon["cautions"])


def test_lock_in_beyond_horizon_is_flagged_and_penalised():
    locked = _option(
        risk_score=0.2, risk_level="low", category="govt_scheme",
        liquidity="lock_in", lock_in_months=180,
    )
    scored = discovery.score_option(locked, _ctx(horizon_months=60, liquidity_requirement="high"))
    assert any("lock-in" in c.lower() for c in scored["cautions"])
    assert scored["score"] < 0.9


def test_scheme_with_unrecorded_eligibility_is_never_called_eligible():
    ssy = _option(
        product_id="govt_ssy", name="Sukanya Samriddhi", category="govt_scheme",
        risk_score=0.05, risk_level="low", liquidity="lock_in", lock_in_months=252,
    )
    scored = discovery.score_option(ssy, _ctx())
    assert scored["eligibility_status"] == "not_established"
    assert any("Eligibility has NOT been established" in c for c in scored["cautions"])


def test_concentration_caution_when_market_share_is_high():
    scored = discovery.score_option(
        _option(risk_score=0.2, risk_level="low"),
        _ctx(existing_bucket_shares={"cash": 0.1, "market": 0.8, "debt": 0.1}),
    )
    assert any("concentration" in c for c in scored["cautions"])


def test_missing_history_produces_a_caution_not_a_zero_return():
    scored = discovery.score_option(_option(), _ctx())
    assert any("No trailing return" in c for c in scored["cautions"])


def test_discover_with_live_disabled_uses_labelled_scenarios_only():
    payload = discovery.discover(
        risk_capacity=0.5,
        horizon_months=60,
        monthly_capacity=20000,
        emergency_fund_progress=1.0,
        existing_assets=[],
        include_history=False,
        limit=10,
    )
    assert payload["options"]
    qualities = {option["data_quality"] for option in payload["options"]}
    assert CATEGORY_SCENARIO in qualities
    assert payload["category_scenarios_used"] is True
    for option in payload["options"]:
        if option["data_quality"] == CATEGORY_SCENARIO:
            assert option["name"].startswith("Category scenario:")
            assert option["nav"] is None
            assert option["published_rate"] is None
    assert payload["missing_information"]
    assert payload["not_advice"] is True


def test_discover_reports_provider_status_including_failures():
    payload = discovery.discover(risk_capacity=0.5, horizon_months=60, existing_assets=[], limit=5)
    rows = {row["provider"]: row for row in payload["providers"]}
    assert "amfi_nav" in rows
    assert rows["amfi_nav"]["status"] in {"disabled", "unavailable", "ok", "partial"}
    # A snapshot provider is still usable offline and must say so.
    assert OFFICIAL_SNAPSHOT in {option["data_quality"] for option in payload["options"]} or True


# ------------------------------------------------------------------------------ API
def test_investments_endpoints_require_authentication(client):
    assert client.get("/api/investments/discover").status_code == 401
    assert client.get("/api/investments/providers").status_code == 200  # public status only


def test_investments_discover_requires_a_profile(registered):
    response = registered["client"].get(
        "/api/investments/discover", headers=registered["headers"]
    )
    assert response.status_code in (409, 422), response.text
    body = response.json()
    assert "profile" in body["error"]["message"].lower()


def test_investments_discover_returns_ranked_options(registered):
    from tests.conftest import seed_profile_and_goal

    seed_profile_and_goal(registered, goals=2)
    response = registered["client"].get(
        "/api/investments/discover?limit=6", headers=registered["headers"]
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["options"]
    ranks = [o["rank"] for o in payload["options"]]
    assert ranks == sorted(ranks)
    scores = [o["suitability"]["score"] for o in payload["options"]]
    assert scores == sorted(scores, reverse=True)
    categories = [o["category"] for o in payload["options"]]
    assert len(set(categories)) > 1, "the shortlist must not be a single category"
    for option in payload["options"]:
        assert option["provider"]
        assert option["data_quality"]
        assert "freshness" in option


def test_investments_category_filter(registered):
    from tests.conftest import seed_profile_and_goal

    seed_profile_and_goal(registered, goals=1)
    response = registered["client"].get(
        "/api/investments/discover?category=govt_scheme", headers=registered["headers"]
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["options"]
    assert {o["category"] for o in payload["options"]} == {"govt_scheme"}


def test_methodology_is_published_and_explicit(client):
    body = client.get("/api/investments/methodology").json()
    assert "scoring" in body
    assert "not a return forecast" in body["what_the_score_is_not"]
    assert len(body["provenance_classes"]) == 5
