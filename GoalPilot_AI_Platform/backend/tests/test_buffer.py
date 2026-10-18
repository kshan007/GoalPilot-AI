"""The protected savings buffer must be real, not a stored number nobody reads.

These tests pin the behaviour the product requires:

* the buffer is the **maximum** of the savings target and the preferred cash reserve, never
  their sum (no double counting);
* a non-mandatory buffer is capped at the surplus and the shortfall is reported;
* a mandatory buffer is honoured even when it creates a deficit;
* the optimiser's budget is ``surplus - protected_buffer`` and the plan cannot exceed it;
* the RL profile row uses the same reduced surplus.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.cashflow import build_cashflow


def _income(amount: float = 100_000) -> SimpleNamespace:
    return SimpleNamespace(amount=amount, frequency="monthly", monthly_equivalent=amount, is_active=True)


def _profile(**kwargs) -> SimpleNamespace:
    base = dict(
        essential_expenses=40_000,
        discretionary_expenses=10_000,
        emergency_months=6,
        emi_income_ratio_cap=0.35,
        risk_capacity=0.5,
        monthly_savings_target=0,
        preferred_cash_buffer=0,
        savings_target_is_mandatory=False,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _build(**kwargs):
    return build_cashflow(
        income_sources=kwargs.pop("income_sources", [_income()]),
        liabilities=kwargs.pop("liabilities", []),
        assets=kwargs.pop("assets", []),
        profile=kwargs.pop("profile", _profile()),
        **kwargs,
    )


def test_buffer_is_the_max_of_target_and_reserve_not_the_sum():
    cf = _build(profile=_profile(monthly_savings_target=15_000, preferred_cash_buffer=8_000))
    assert cf.savings_target == 15_000
    assert cf.preferred_cash_buffer == 8_000
    assert cf.protected_buffer == 15_000
    assert cf.desired_buffer == 15_000


def test_available_goal_budget_excludes_the_buffer():
    cf = _build(profile=_profile(monthly_savings_target=20_000))
    assert cf.monthly_surplus == pytest.approx(50_000)
    assert cf.protected_buffer == pytest.approx(20_000)
    assert cf.available_goal_budget == pytest.approx(30_000)


def test_non_mandatory_buffer_is_capped_at_the_surplus_and_reported():
    cf = _build(
        income_sources=[_income(60_000)],
        profile=_profile(monthly_savings_target=90_000),
    )
    assert cf.monthly_surplus == pytest.approx(10_000)
    assert cf.protected_buffer == pytest.approx(10_000)
    assert cf.buffer_deficit == pytest.approx(80_000)
    assert cf.buffer_sustained is False
    assert cf.available_goal_budget == 0
    assert any("cannot be met" in w for w in cf.warnings)


def test_mandatory_buffer_is_honoured_even_when_it_exceeds_the_surplus():
    cf = _build(
        income_sources=[_income(60_000)],
        profile=_profile(monthly_savings_target=90_000, savings_target_is_mandatory=True),
    )
    assert cf.protected_buffer == pytest.approx(90_000)
    assert cf.available_goal_budget == 0
    # The buffer is honoured, but 80,000 of it cannot come from this month's surplus. That gap
    # is a real funding requirement and must be reported, not netted away.
    assert cf.buffer_deficit == pytest.approx(80_000)
    assert any("exceeds the" in w and "monthly surplus" in w for w in cf.warnings)


def test_deficit_household_has_no_goal_budget():
    cf = _build(
        income_sources=[_income(40_000)],
        profile=_profile(monthly_savings_target=5_000),
    )
    assert cf.monthly_surplus < 0
    assert cf.protected_buffer == 0
    assert cf.available_goal_budget == 0
    assert cf.is_deficit is True


def test_solver_discretionary_includes_the_buffer_only():
    cf = _build(profile=_profile(monthly_savings_target=12_000))
    assert cf.solver_discretionary() == pytest.approx(cf.discretionary_expenses + 12_000)


def test_surplus_basis_is_projected_without_actuals():
    cf = _build(profile=_profile(monthly_savings_target=1_000))
    assert cf.surplus_basis == "projected"


def test_surplus_basis_is_actual_with_recorded_transactions():
    cf = _build(
        profile=_profile(monthly_savings_target=1_000),
        expense_items=[
            {"category": "housing", "amount": 30_000, "classification": "essential"},
            {"category": "shopping", "amount": 5_000, "classification": "discretionary"},
        ],
    )
    assert cf.surplus_basis == "actual"
    assert cf.essential_expenses == 30_000
    assert cf.discretionary_expenses == 5_000


def test_emergency_fund_is_not_added_to_the_monthly_buffer():
    cf = _build(
        profile=_profile(monthly_savings_target=10_000),
        assets=[SimpleNamespace(current_value=100_000, is_liquid=True, asset_type="liquid_savings",
                                usable_for_goals=True)],
    )
    # The emergency-fund target is a stock (6 x 40,000), not a monthly flow.
    assert cf.emergency_fund_target == pytest.approx(240_000)
    assert cf.protected_buffer == pytest.approx(10_000)
    assert cf.available_cash_for_goals == pytest.approx(0)


# ---------------------------------------------------------------------- API / engine
def test_plan_respects_the_protected_buffer(registered):
    from tests.conftest import seed_profile_and_goal

    seed_profile_and_goal(registered, goals=2)
    summary = registered["client"].get("/api/profile/summary", headers=registered["headers"]).json()
    assert summary["protected_buffer"] == pytest.approx(15_000)
    assert summary["available_goal_budget"] == pytest.approx(15_000)
    assert summary["buffer_sustained"] is True

    plan = registered["client"].post(
        "/api/optimize/plan", headers=registered["headers"], json={"algorithm": "lp"}
    )
    assert plan.status_code == 200, plan.text
    body = plan.json()
    contributions = sum(
        a["monthly_savings_contribution"] + a["monthly_investment_contribution"]
        for a in body["allocations"]
    )
    assert contributions <= summary["available_goal_budget"] + 1e-6
    assert body["constraints"]["protected_buffer"] == pytest.approx(15_000)
    assert body["constraints"]["gross_monthly_surplus"] == pytest.approx(30_000)
    assert body["constraints"]["monthly_surplus"] == pytest.approx(15_000)


def test_rl_profile_row_excludes_the_buffer(registered):
    from app.engines import rl_engine
    from tests.conftest import seed_profile_and_goal
    from app.services.planner import load_cashflow
    from app.db import get_session_factory
    from app.models import User

    seed_profile_and_goal(registered, goals=1)
    with get_session_factory()() as db:
        user = db.get(User, registered["user"]["id"])
        cf = load_cashflow(db, user.id)
        row = rl_engine.build_profile_row(cf, investment_capacity_ratio=0.4, risk_score=0.5)
        assert row["monthly_expenditure"].iloc[0] == pytest.approx(
            cf.essential_expenses + cf.discretionary_expenses + cf.protected_buffer
        )
        assert any("protected buffer" in note for note in rl_engine.mapping_notes(cf, 0.4))
