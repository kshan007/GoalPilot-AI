"""Scenario simulation: presets, assumption changes, deltas, no side effects on stored data."""
from __future__ import annotations

import pytest

from app.services import scenarios as scenario_service
from tests.conftest import seed_profile_and_goal
from tests.test_financial_calc import Ast, Goal, Liab, Src


def make_cashflow():
    from app.services.cashflow import build_cashflow

    return build_cashflow(
        income_sources=[Src(90_000)],
        liabilities=[Liab(emi=12_000, principal=600_000)],
        assets=[Ast(300_000)],
        expense_items=[
            {"category": "housing", "amount": 30_000},
            {"category": "entertainment", "amount": 8_000, "classification": "discretionary"},
        ],
        emergency_months=6,
        earmarked_goal_funding=0.0,
    )


def test_presets_cover_every_scenario_the_brief_names():
    names = {p["preset"] for p in scenario_service.list_presets()}
    expected = {
        "expenses_up", "income_down", "unexpected_expense", "higher_inflation",
        "lower_returns", "higher_lending_rates", "improved_savings", "delayed_goals",
    }
    assert expected <= names
    for preset in scenario_service.list_presets():
        assert preset["assumption_note"]


def test_expense_increase_lowers_the_surplus():
    cf = make_cashflow()
    stressed, params, narrative = scenario_service.apply_to_cashflow(
        cf, "expenses_up", {"expense_increase_pct": 10}
    )
    assert stressed.essential_expenses == pytest.approx(cf.essential_expenses * 1.1)
    assert stressed.monthly_surplus < cf.monthly_surplus
    assert narrative


def test_income_reduction_lowers_the_surplus():
    cf = make_cashflow()
    stressed, _, _ = scenario_service.apply_to_cashflow(
        cf, "income_down", {"income_change_pct": -20}
    )
    assert stressed.monthly_income == pytest.approx(cf.monthly_income * 0.8)


def test_unexpected_expense_reduces_liquid_savings_only():
    cf = make_cashflow()
    stressed, _, _ = scenario_service.apply_to_cashflow(
        cf, "unexpected_expense", {"one_off_amount": 100_000}
    )
    assert stressed.liquid_savings == pytest.approx(cf.liquid_savings - 100_000)
    assert stressed.monthly_surplus == pytest.approx(cf.monthly_surplus)


def test_improved_savings_raises_the_surplus():
    cf = make_cashflow()
    stressed, _, _ = scenario_service.apply_to_cashflow(
        cf, "improved_savings", {"discretionary_reduction_pct": 50}
    )
    assert stressed.discretionary_expenses < cf.discretionary_expenses
    assert stressed.monthly_surplus > cf.monthly_surplus


def test_derived_fields_are_recomputed_consistently():
    cf = make_cashflow()
    stressed, _, _ = scenario_service.apply_to_cashflow(cf, "expenses_up", {})
    assert stressed.monthly_surplus == pytest.approx(
        stressed.monthly_income
        - stressed.essential_expenses
        - stressed.discretionary_expenses
        - stressed.existing_emi
    )
    assert stressed.emergency_fund_target == pytest.approx(
        stressed.emergency_months * stressed.essential_expenses
    )


def test_assumption_overrides_only_touch_the_named_parameter():
    base = {
        "annual_inflation": 0.03,
        "investment_return": 0.05,
        "loan_annual_rate": 0.12,
        "savings_return": 0.0,
    }
    inflation = scenario_service.assumption_overrides(
        "higher_inflation", {"inflation_delta_pct": 2.0}, base
    )
    assert inflation["annual_inflation"] == pytest.approx(0.05)
    assert inflation["investment_return"] == base["investment_return"]

    rates = scenario_service.assumption_overrides(
        "higher_lending_rates", {"loan_rate_delta_pct": 3.0}, base
    )
    assert rates["loan_annual_rate"] == pytest.approx(0.15)
    assert rates["annual_inflation"] == base["annual_inflation"]


def test_delaying_goals_only_moves_flexible_ones():
    class Fixed(Goal):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.date_flexible = False

    flexible = Goal(1, 100_000, 24)
    fixed = Fixed(2, 100_000, 24)
    moved = scenario_service.delay_goals([flexible, fixed], 12)
    assert 1 in moved and 2 not in moved
    assert moved[1] > flexible.target_date


def test_unknown_preset_is_rejected():
    with pytest.raises(ValueError):
        scenario_service.apply_to_cashflow(make_cashflow(), "not_a_preset", {})


def test_presets_and_run_endpoints(client, registered):
    seed_profile_and_goal(registered, goals=2)

    presets = client.get("/api/scenarios/presets", headers=registered["headers"])
    assert presets.status_code == 200
    assert len(presets.json()) >= 8

    run = client.post(
        "/api/scenarios/run",
        headers=registered["headers"],
        json={"preset": "expenses_up", "parameters": {"expense_increase_pct": 15}, "algorithm": "lp"},
    )
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["preset"] == "expenses_up"
    assert body["baseline"]["status"] == "optimal"
    assert body["stressed"]["status"] in ("optimal", "infeasible")
    assert body["deltas"]
    assert body["narrative"]

    again = client.get(
        f"/api/scenarios/runs/{body['id']}", headers=registered["headers"]
    )
    assert again.status_code == 200


def test_scenario_does_not_rewrite_stored_goal_dates(client, registered):
    seed_profile_and_goal(registered, goals=2)
    before = {
        g["id"]: g["target_date"]
        for g in client.get("/api/goals", headers=registered["headers"]).json()
    }
    response = client.post(
        "/api/scenarios/run",
        headers=registered["headers"],
        json={"preset": "delayed_goals", "parameters": {"delay_months": 24}, "algorithm": "lp"},
    )
    assert response.status_code == 200, response.text
    after = {
        g["id"]: g["target_date"]
        for g in client.get("/api/goals", headers=registered["headers"]).json()
    }
    assert before == after


def test_scenario_runs_are_isolated(client, registered, second_user):
    seed_profile_and_goal(registered, goals=1)
    seed_profile_and_goal(second_user, goals=1)

    mine = client.post(
        "/api/scenarios/run", headers=registered["headers"],
        json={"preset": "income_down", "algorithm": "lp"},
    ).json()

    assert client.get(
        f"/api/scenarios/runs/{mine['id']}", headers=second_user["headers"]
    ).status_code == 404
    assert client.get("/api/scenarios/runs", headers=second_user["headers"]).json()["items"] == []
