"""LP engine: feasibility, infeasibility, multi-goal, priorities, earmarks, financing,
no double allocation, and reproducible solver behaviour."""
from __future__ import annotations

import datetime as dt

import pytest

from app.engines import lp_engine, research_loader
from app.engines.common import validate_plan
from app.services.cashflow import build_cashflow
from tests.test_financial_calc import Ast, Goal, Liab, Src

pytestmark = pytest.mark.skipif(
    not research_loader.is_available(), reason="The research project is not reachable."
)


def make_cashflow(**overrides):
    kwargs = dict(
        income_sources=[Src(90_000)],
        liabilities=[Liab(emi=12_000, principal=600_000)],
        assets=[Ast(420_000)],
        expense_items=[
            {"category": "housing", "amount": 30_000},
            {"category": "entertainment", "amount": 6_000, "classification": "discretionary"},
        ],
        emergency_months=6,
        emi_income_ratio_cap=0.35,
        risk_capacity=0.55,
        earmarked_goal_funding=0.0,
    )
    kwargs.update(overrides)
    return build_cashflow(**kwargs)


def test_module_and_status_are_wired():
    status = research_loader.status()
    assert status.available is True
    assert status.modules["multi_goal_optimizer"] is True
    assert status.modules["goalpilot_constrained_lp"] is True


def test_constrained_solve_returns_feasible_multi_goal_plan():
    goals = [Goal(1, 90_000, 12, funded=10_000), Goal(2, 300_000, 36, funded=50_000)]
    result = lp_engine.solve(goals=goals, cashflow=make_cashflow())
    assert result.status == "optimal"
    assert result.feasible is True
    assert len(result.allocations) == 2
    assert result.objective_value is not None
    assert result.model_version.startswith("constrained_lp")


def test_plan_respects_every_mandatory_constraint():
    goals = [Goal(1, 400_000, 12, funded=0), Goal(2, 250_000, 24, funded=20_000)]
    cashflow = make_cashflow()
    result = lp_engine.solve(goals=goals, cashflow=cashflow)
    assert result.feasible, result.diagnostics
    validation = result.diagnostics["validation"]
    assert validation["clean"] is True
    assert validation["count"] == 0


def test_no_goal_is_funded_beyond_its_gap():
    goals = [Goal(1, 60_000, 24, funded=0), Goal(2, 80_000, 24, funded=0)]
    result = lp_engine.solve(goals=goals, cashflow=make_cashflow())
    for row in result.allocations:
        assert row["projected_new_funding"] <= row["funding_gap"] + 1e-6


def test_allocations_never_exceed_the_available_cash_pool():
    goals = [Goal(1, 900_000, 6, funded=0), Goal(2, 900_000, 6, funded=0)]
    cashflow = make_cashflow()
    result = lp_engine.solve(goals=goals, cashflow=cashflow)
    assert result.feasible, result.diagnostics
    total_cash = sum(r["initial_savings_allocated"] for r in result.allocations)
    assert total_cash <= cashflow.available_cash_for_goals + 1e-4


def test_contributions_never_exceed_the_monthly_surplus():
    goals = [Goal(1, 500_000, 6, funded=0), Goal(2, 500_000, 6, funded=0)]
    cashflow = make_cashflow()
    result = lp_engine.solve(goals=goals, cashflow=cashflow)
    total = sum(
        r["monthly_savings_contribution"] + r["monthly_investment_contribution"]
        for r in result.allocations
    )
    assert total <= max(0.0, cashflow.monthly_surplus) + 1e-4


def test_existing_earmark_is_not_double_counted():
    """The earmark is excluded from the shared pool, so it cannot be spent twice."""
    goals = [Goal(1, 300_000, 24, funded=150_000)]
    # liquid 600,000 - emergency reserve 6 x 30,000 - earmark 150,000 = 270,000 free
    cashflow = make_cashflow(earmarked_goal_funding=150_000, assets=[Ast(600_000)])
    assert cashflow.earmarked_goal_funding == 150_000
    assert cashflow.available_cash_for_goals == pytest.approx(600_000 - 180_000 - 150_000)

    result = lp_engine.solve(goals=goals, cashflow=cashflow)
    assert result.feasible
    total_cash = sum(r["initial_savings_allocated"] for r in result.allocations)
    assert total_cash <= cashflow.available_cash_for_goals + 1e-4
    # the earmark is NOT part of the pool that could be allocated a second time
    assert total_cash <= 270_000 + 1e-4


def test_earmark_that_exceeds_free_cash_leaves_no_pool():
    """The pool is floored at zero rather than going negative."""
    cashflow = make_cashflow(earmarked_goal_funding=150_000, assets=[Ast(300_000)])
    assert cashflow.available_cash_for_goals == 0.0


def test_infeasible_input_is_reported_not_faked():
    """A goal whose gap can never be closed must come back as a shortfall, not a plan."""
    goals = [Goal(1, 50_000_000, 360, funded=0)]
    result = lp_engine.solve(goals=goals, cashflow=make_cashflow())
    # The LP is always solvable here (shortfall is a variable), so it must report the
    # shortfall rather than claim success.
    assert result.status in ("optimal", "infeasible")
    if result.status == "optimal":
        assert float(result.summary["total_shortfall"]) > 0
        assert any("Not every goal can be met" in w for w in result.warnings)


def test_zero_surplus_and_zero_cash_still_solves_with_total_shortfall():
    cashflow = make_cashflow(
        income_sources=[Src(42_000)],
        liabilities=[Liab(emi=12_000, principal=100_000)],
        assets=[Ast(0)],
        expense_items=[{"category": "housing", "amount": 30_000}],
        emergency_months=0,
    )
    assert cashflow.monthly_surplus == pytest.approx(0.0)
    goals = [Goal(1, 200_000, 12, funded=0)]
    result = lp_engine.solve(goals=goals, cashflow=cashflow)
    assert result.status == "optimal"
    assert result.feasible is True
    assert float(result.summary["total_shortfall"]) == pytest.approx(200_000 * 1.03 ** 1, rel=1e-3)
    assert any("Not every goal can be met" in w for w in result.warnings)


def test_goal_priority_changes_how_shortfall_is_distributed():
    tight = make_cashflow(
        income_sources=[Src(50_000)],
        liabilities=[],
        assets=[Ast(0)],
        expense_items=[{"category": "housing", "amount": 30_000}],
        emergency_months=0,
    )
    high = Goal(1, 400_000, 12, funded=0, priority=5, criticality=5)
    low = Goal(2, 400_000, 12, funded=0, priority=1, criticality=1)
    result = lp_engine.solve(goals=[high, low], cashflow=tight)
    by_ref = {r["goal_id"]: r for r in result.allocations}
    assert result.feasible
    # the higher-priority goal must receive at least as much funding
    assert by_ref["G1"]["achievement_ratio"] >= by_ref["G2"]["achievement_ratio"]


def test_financing_is_bounded_and_carries_an_interest_cost():
    goals = [Goal(1, 400_000, 12, funded=0)]
    result = lp_engine.solve(goals=goals, cashflow=make_cashflow())
    loan = sum(r["loan_principal"] for r in result.allocations)
    assert loan <= 150_000 + 1e-4  # max_new_loan default
    for row in result.allocations:
        if row["loan_principal"] > 1e-6:
            assert row["estimated_loan_emi"] > 0
            assert row["estimated_loan_interest_cost"] >= 0


def test_financing_can_be_disabled_and_then_no_loan_is_taken():
    goals = [Goal(1, 400_000, 12, funded=0)]
    result = lp_engine.solve(
        goals=goals,
        cashflow=make_cashflow(),
        assumptions=lp_engine.LpAssumptions(allow_financing=False),
    )
    assert all(r["loan_principal"] <= 1e-6 for r in result.allocations)
    assert any("Financing is disabled" in w for w in result.warnings)


def test_new_emi_stays_within_the_emi_capacity():
    goals = [Goal(1, 900_000, 12, funded=0), Goal(2, 900_000, 12, funded=0)]
    cashflow = make_cashflow()
    result = lp_engine.solve(goals=goals, cashflow=cashflow)
    assert result.feasible
    total_emi = sum(r["estimated_loan_emi"] for r in result.allocations)
    assert total_emi <= float(result.constraints["emi_cap"]) + 1e-4


def test_investment_is_capped_by_the_derived_capacity():
    goals = [Goal(1, 600_000, 24, funded=0)]
    cashflow = make_cashflow()
    result = lp_engine.solve(goals=goals, cashflow=cashflow)
    assert result.feasible
    permitted = float(result.constraints["investment_permitted"])
    invested = sum(r["monthly_investment_contribution"] for r in result.allocations)
    assert invested <= permitted + 1e-4


def test_risk_capacity_zero_blocks_risky_investment():
    goals = [Goal(1, 600_000, 24, funded=0)]
    result = lp_engine.solve(
        goals=goals, cashflow=make_cashflow(risk_capacity=0.0)
    )
    assert result.feasible
    assert sum(r["monthly_investment_contribution"] for r in result.allocations) <= 0.0


def test_results_are_reproducible():
    goals = [Goal(1, 200_000, 18, funded=5_000), Goal(2, 320_000, 30, funded=10_000)]
    cashflow = make_cashflow()
    first = lp_engine.solve(goals=goals, cashflow=cashflow)
    second = lp_engine.solve(goals=goals, cashflow=cashflow)
    assert first.objective_value == second.objective_value
    assert first.allocations == second.allocations


def test_empty_goal_set_is_refused():
    result = lp_engine.solve(goals=[], cashflow=make_cashflow())
    assert result.status == "infeasible"
    assert result.feasible is False


def test_flow_only_plan_ignores_existing_cash():
    goals = [Goal(1, 300_000, 24, funded=0)]
    cashflow = make_cashflow()
    result = lp_engine.solve(goals=goals, cashflow=cashflow, flow_only=True)
    assert result.feasible
    assert sum(r["initial_savings_allocated"] for r in result.allocations) <= 1e-6
    assert any("Monthly-flow-only basis" in w for w in result.warnings)


def test_validation_catches_an_over_allocated_plan():
    """The validator is the safety net: prove it actually rejects a bad plan."""
    import pandas as pd

    bad = pd.DataFrame(
        [
            {
                "initial_savings_allocated": 10_000.0,
                "existing_assets_allocated": 0.0,
                "monthly_savings_contribution": 50_000.0,
                "monthly_investment_contribution": 0.0,
                "loan_principal": 0.0,
                "estimated_loan_emi": 0.0,
                "shortfall": 0.0,
                "projected_new_funding": 100.0,
                "funding_gap": 100.0,
            }
        ]
    )
    violations = validate_plan(
        bad,
        {},
        monthly_surplus=10_000.0,
        emi_cap=10_000.0,
        available_cash=5_000.0,
        usable_existing_assets=0.0,
    )
    codes = {v.code for v in violations}
    assert "surplus_exceeded" in codes
    assert "cash_pool_exceeded" in codes


def test_validation_catches_negative_and_overfunded_allocations():
    import pandas as pd

    bad = pd.DataFrame(
        [
            {
                "initial_savings_allocated": -1.0,
                "existing_assets_allocated": 0.0,
                "monthly_savings_contribution": 0.0,
                "monthly_investment_contribution": 0.0,
                "loan_principal": 0.0,
                "estimated_loan_emi": 0.0,
                "shortfall": 0.0,
                "projected_new_funding": 999.0,
                "funding_gap": 100.0,
            }
        ]
    )
    codes = {
        v.code
        for v in validate_plan(
            bad, {}, monthly_surplus=1_000.0, emi_cap=1_000.0,
            available_cash=1_000.0, usable_existing_assets=0.0,
        )
    }
    assert "negative_allocation" in codes
    assert "goal_overfunded" in codes
