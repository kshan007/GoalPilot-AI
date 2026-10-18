"""Financial calculations: normalisation, surplus, debt accounting, emergency fund,
goal projections, rounding and negative surplus."""
from __future__ import annotations

import datetime as dt

import pytest

from app.core.errors import ValidationFailure
from app.services.cashflow import build_cashflow, classification_for
from app.services.goals import project_goals, suggest_alternatives
from app.services.money import (
    months_between,
    normalise_annual,
    normalise_monthly,
    round_money,
)


class Src:
    def __init__(self, amount, frequency="monthly", monthly_equivalent=None, active=True):
        self.amount = amount
        self.frequency = frequency
        self.monthly_equivalent = (
            monthly_equivalent if monthly_equivalent is not None else normalise_monthly(amount, frequency)
        )
        self.is_active = active


class Liab:
    def __init__(self, emi, principal):
        self.emi_amount = emi
        self.outstanding_principal = principal


class Ast:
    def __init__(self, value, liquid=True, usable=True, kind="liquid_savings"):
        self.current_value = value
        self.is_liquid = liquid
        self.usable_for_goals = usable
        self.asset_type = kind


# --------------------------------------------------------------------------------------
# money
# --------------------------------------------------------------------------------------
def test_round_money_is_half_up_to_two_decimals():
    assert str(round_money(0.005)) == "0.01"
    assert str(round_money(2.675)) == "2.68"
    assert str(round_money("10.994")) == "10.99"
    assert str(round_money(0)) == "0.00"


def test_round_money_avoids_binary_float_noise():
    # 0.1 + 0.2 must not surface as 0.30000000000000004
    assert str(round_money(0.1 + 0.2)) == "0.30"


def test_income_normalisation():
    assert normalise_monthly(1200, "monthly") == 1200
    assert normalise_monthly(1200, "quarterly") == pytest.approx(400.0)
    assert normalise_monthly(120_000, "annual") == pytest.approx(10_000.0)
    assert normalise_monthly(1000, "weekly") == pytest.approx(4333.3333, rel=1e-4)
    assert normalise_monthly(5000, "one_time") == 0.0
    assert normalise_annual(10_000, "monthly") == pytest.approx(120_000)


def test_unsupported_frequency_is_rejected():
    with pytest.raises(ValidationFailure):
        normalise_monthly(1000, "fortnightly")


def test_months_between():
    assert months_between(dt.date(2026, 1, 1), dt.date(2026, 1, 1)) == 0
    assert months_between(dt.date(2026, 1, 1), dt.date(2026, 2, 1)) == 1
    assert months_between(dt.date(2026, 1, 15), dt.date(2026, 2, 10)) == 0
    assert months_between(dt.date(2026, 1, 1), dt.date(2025, 1, 1)) == 0  # floored at zero


# --------------------------------------------------------------------------------------
# cash flow
# --------------------------------------------------------------------------------------
def test_surplus_excludes_nothing_and_nets_out_emi():
    cf = build_cashflow(
        income_sources=[Src(90_000)],
        liabilities=[Liab(emi=12_000, principal=600_000)],
        assets=[Ast(420_000)],
        expense_items=[
            {"category": "housing", "amount": 30_000},
            {"category": "entertainment", "amount": 6_000, "classification": "discretionary"},
        ],
        emergency_months=6,
        emi_income_ratio_cap=0.35,
        risk_capacity=0.5,
    )
    assert cf.monthly_income == 90_000
    assert cf.essential_expenses == 30_000
    assert cf.discretionary_expenses == 6_000
    assert cf.existing_emi == 12_000
    # 90000 - 30000 - 6000 - 12000
    assert cf.monthly_surplus == pytest.approx(42_000)


def test_principal_is_never_added_to_the_emi():
    """The EMI already contains principal and interest. Adding the balance double-counts."""
    cf = build_cashflow(
        income_sources=[Src(50_000)],
        liabilities=[Liab(emi=5_000, principal=1_000_000)],
        assets=[Ast(100_000)],
        expense_items=[{"category": "housing", "amount": 20_000}],
    )
    assert cf.existing_emi == 5_000
    assert cf.outstanding_debt == 1_000_000
    assert cf.monthly_surplus == pytest.approx(25_000)  # not 50000-20000-5000-1000000


def test_negative_surplus_is_reported_as_a_deficit_not_clamped():
    cf = build_cashflow(
        income_sources=[Src(30_000)],
        liabilities=[Liab(emi=10_000, principal=100_000)],
        assets=[Ast(50_000)],
        expense_items=[{"category": "housing", "amount": 28_000}],
    )
    assert cf.monthly_surplus == pytest.approx(-8_000)
    assert cf.is_deficit is True
    assert any("deficit" in w for w in cf.warnings)


def test_emergency_fund_metrics():
    cf = build_cashflow(
        income_sources=[Src(60_000)],
        liabilities=[],
        assets=[Ast(100_000)],
        expense_items=[{"category": "housing", "amount": 20_000}],
        emergency_months=6,
    )
    assert cf.emergency_fund_target == pytest.approx(120_000)
    assert cf.emergency_fund_gap == pytest.approx(20_000)
    assert cf.emergency_fund_progress == pytest.approx(100_000 / 120_000)


def test_zero_emergency_months_warns_and_frees_all_cash():
    cf = build_cashflow(
        income_sources=[Src(60_000)],
        liabilities=[],
        assets=[Ast(200_000)],
        expense_items=[{"category": "housing", "amount": 20_000}],
        emergency_months=0,
    )
    assert cf.emergency_fund_target == 0
    assert cf.available_cash_for_goals == pytest.approx(200_000)
    assert any("Emergency-fund reserve is set to 0" in w for w in cf.warnings)


def test_goal_earmarks_are_removed_from_the_cash_pool_exactly_once():
    cf = build_cashflow(
        income_sources=[Src(60_000)],
        liabilities=[],
        assets=[Ast(500_000)],
        expense_items=[{"category": "housing", "amount": 20_000}],
        emergency_months=0,
        earmarked_goal_funding=150_000,
    )
    assert cf.earmarked_goal_funding == 150_000
    assert cf.available_cash_for_goals == pytest.approx(350_000)


def test_non_liquid_assets_are_excluded_from_usable_capital():
    cf = build_cashflow(
        income_sources=[Src(60_000)],
        liabilities=[],
        assets=[Ast(200_000), Ast(900_000, liquid=False, usable=False, kind="fixed_deposit")],
        expense_items=[{"category": "housing", "amount": 20_000}],
        emergency_months=0,
    )
    assert cf.total_assets == pytest.approx(1_100_000)
    assert cf.liquid_savings == pytest.approx(200_000)
    assert cf.usable_existing_investments == pytest.approx(200_000)
    assert cf.non_liquid_assets == pytest.approx(900_000)


def test_inactive_income_is_excluded():
    cf = build_cashflow(
        income_sources=[Src(50_000), Src(30_000, active=False)],
        liabilities=[],
        assets=[Ast(10_000)],
        expense_items=[{"category": "housing", "amount": 10_000}],
    )
    assert cf.monthly_income == 50_000


def test_zero_income_is_rejected():
    with pytest.raises(ValidationFailure):
        build_cashflow(
            income_sources=[Src(0)],
            liabilities=[],
            assets=[],
            expense_items=[],
        )


def test_emi_ceiling_warning():
    cf = build_cashflow(
        income_sources=[Src(40_000)],
        liabilities=[Liab(emi=20_000, principal=500_000)],
        assets=[Ast(10_000)],
        expense_items=[{"category": "housing", "amount": 5_000}],
        emi_income_ratio_cap=0.35,
    )
    assert cf.emi_income_ratio == pytest.approx(0.5)
    assert any("EMI obligations" in w for w in cf.warnings)


def test_savings_target_is_distinct_from_surplus():
    cf = build_cashflow(
        income_sources=[Src(60_000)],
        liabilities=[],
        assets=[Ast(10_000)],
        expense_items=[{"category": "housing", "amount": 20_000}],
        savings_target=25_000,
    )
    # surplus is 40000, the *desired* target is 25000 -> attainable, but they are separate fields
    assert cf.monthly_surplus == pytest.approx(40_000)
    assert cf.savings_target == 25_000
    assert cf.savings_target_attainment == 1.0


def test_classification_defaults():
    assert classification_for("housing") == "essential"
    assert classification_for("entertainment") == "discretionary"
    assert classification_for("whatever", "essential") == "essential"


def test_loan_payment_lines_are_not_double_counted_with_the_emi():
    """A `loan_payments` transaction and the liability EMI are the same money."""
    cf = build_cashflow(
        income_sources=[Src(90_000)],
        liabilities=[Liab(emi=12_000, principal=600_000)],
        assets=[Ast(100_000)],
        expense_items=[
            {"category": "housing", "amount": 30_000},
            {"category": "loan_payments", "amount": 12_000},  # the same EMI as a transaction
        ],
    )
    assert cf.existing_emi == 12_000
    assert cf.essential_expenses == 30_000  # the loan line was NOT added again
    assert cf.loan_payment_lines_skipped == 1
    assert cf.monthly_surplus == pytest.approx(90_000 - 30_000 - 12_000)
    assert any("double-count" in w for w in cf.warnings)


def test_expense_basis_is_recorded_and_warned():
    via_profile = build_cashflow(
        income_sources=[Src(90_000)],
        liabilities=[],
        assets=[Ast(0)],
        expense_items=None,
    )
    assert via_profile.expense_basis == "profile"

    via_month = build_cashflow(
        income_sources=[Src(90_000)],
        liabilities=[],
        assets=[Ast(0)],
        expense_items=[
            {"category": "housing", "amount": 30_000},
            {"category": "shopping", "amount": 5_000, "classification": "discretionary"},
        ],
    )
    assert via_month.expense_basis == "month_actuals"
    assert via_month.expense_categories_used == 2
    assert any("recorded actual transactions" in w for w in via_month.warnings)


# --------------------------------------------------------------------------------------
# goal projections
# --------------------------------------------------------------------------------------
class Goal:
    def __init__(self, gid, cost, months, funded=0.0, priority=3, criticality=3,
                 date_flexible=True, amount_flexible=False):
        self.id = gid
        self.name = f"Goal {gid}"
        self.goal_type = "custom"
        self.current_cost = cost
        self.target_date = dt.date.today() + dt.timedelta(days=int(months * 30.44))
        self.current_funded_amount = funded
        self.priority = priority
        self.criticality = criticality
        self.date_flexible = date_flexible
        self.amount_flexible = amount_flexible


def test_future_goal_cost_uses_the_inflation_assumption():
    goal = Goal(1, 100_000, 12)
    projections = project_goals(
        [goal], inflation=0.03, savings_return=0.0, investment_return=0.05,
        monthly_surplus=30_000, available_cash=0,
    )
    p = projections[0]
    # 100000 * 1.03 ** (months/12)
    expected = 100_000 * (1.03) ** (p.months_remaining / 12)
    assert p.future_target == pytest.approx(expected, rel=1e-6)
    assert p.remaining_gap == pytest.approx(expected - 0)


def test_zero_inflation_leaves_the_cost_unchanged():
    goal = Goal(1, 100_000, 24, funded=25_000)
    p = project_goals(
        [goal], inflation=0.0, savings_return=0.0, investment_return=0.0,
        monthly_surplus=10_000, available_cash=0,
    )[0]
    assert p.future_target == pytest.approx(100_000)
    assert p.remaining_gap == pytest.approx(75_000)
    assert p.required_monthly_contribution == pytest.approx(75_000 / p.months_remaining)


def test_already_funded_goal():
    goal = Goal(1, 50_000, 12, funded=80_000)
    p = project_goals(
        [goal], inflation=0.0, savings_return=0.0, investment_return=0.0,
        monthly_surplus=10_000, available_cash=0,
    )[0]
    assert p.remaining_gap == 0
    assert p.feasibility == "funded"


def test_infeasible_when_required_exceeds_surplus():
    goal = Goal(1, 1_000_000, 6)
    p = project_goals(
        [goal], inflation=0.0, savings_return=0.0, investment_return=0.0,
        monthly_surplus=10_000, available_cash=0,
    )[0]
    assert p.feasibility == "infeasible_on_current_cashflow"
    assert p.notes


def test_infeasible_when_there_is_no_surplus():
    goal = Goal(1, 100_000, 12)
    p = project_goals(
        [goal], inflation=0.0, savings_return=0.0, investment_return=0.0,
        monthly_surplus=0.0, available_cash=0,
    )[0]
    assert p.feasibility == "infeasible"


def test_at_risk_when_one_goal_consumes_most_of_the_surplus():
    goal = Goal(1, 120_000, 12)
    p = project_goals(
        [goal], inflation=0.0, savings_return=0.0, investment_return=0.0,
        monthly_surplus=10_000, available_cash=0,
    )[0]
    assert p.feasibility == "at_risk"


def test_projection_leaves_planned_fields_null_without_a_plan():
    p = project_goals(
        [Goal(1, 100_000, 12)], inflation=0.03, savings_return=0.0, investment_return=0.05,
        monthly_surplus=20_000, available_cash=0,
    )[0]
    assert p.planned_monthly_contribution is None
    assert p.projected_funding is None
    assert p.achievement_ratio is None


def test_alternatives_are_withheld_when_the_date_is_inflexible():
    goal = Goal(1, 5_000_000, 12, date_flexible=False, amount_flexible=False)
    p = project_goals(
        [goal], inflation=0.0, savings_return=0.0, investment_return=0.0,
        monthly_surplus=5_000, available_cash=0,
    )[0]
    options = suggest_alternatives(
        p, monthly_surplus=5_000, available_cash=0, emergency_months=6
    )
    kinds = {o["option"] for o in options}
    assert not any(k.startswith("extend_deadline") for k in kinds)
    assert "reduce_target" not in kinds
    assert "financing" in kinds
