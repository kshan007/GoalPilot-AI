"""Regression tests for the defects found in the 2026-10-18 audit.

Each test fails on the code as it stood before the fix it covers. They are grouped by the
defect, not by module, because the defects crossed module boundaries.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from app.engines import hybrid_engine, lp_engine, research_loader, rl_engine
from app.engines.common import OBJECTIVE_DEFINITION, ArmResult
from app.services.goals import project_goals
from tests.conftest import seed_profile_and_goal
from tests.test_financial_calc import Ast, Goal, Liab, Src
from app.services.cashflow import build_cashflow

pytestmark = pytest.mark.skipif(
    not research_loader.is_available(), reason="The research project is not reachable."
)


# --------------------------------------------------------------------------------------
# A. goal-slot ordering in the shared trajectory
# --------------------------------------------------------------------------------------
def _cashflow():
    return build_cashflow(
        income_sources=[Src(100_000)],
        liabilities=[Liab(emi=12_000, principal=600_000)],
        assets=[Ast(200_000)],
        expense_items=[
            {"category": "housing", "amount": 30_000},
            {"category": "food_groceries", "amount": 12_000},
            {"category": "entertainment", "amount": 6_000, "classification": "discretionary"},
        ],
        emergency_months=6,
        emi_income_ratio_cap=0.35,
        risk_capacity=0.55,
        savings_target=15_000,
        preferred_cash_buffer=8_000,
    )


def _goals():
    # The helper names goals "Goal <id>"; the order here is the database order (by id), which
    # deliberately differs from the environment's horizon order.
    return [
        Goal(1, 200_000, 18, priority=3, criticality=3),
        Goal(2, 800_000, 48, priority=2, criticality=2),
        Goal(3, 2_000_000, 84, priority=5, criticality=5),
    ]


def test_plan_is_encoded_into_the_environment_slot_order_by_goal_id():
    """The environment sorts goals by horizon; a positional encode funds the wrong goal."""
    goals = _goals()
    lookup = {g.id: max(1, (g.target_date - dt.date.today()).days // 30) for g in goals}
    profile = rl_engine.build_profile_row(
        _cashflow(), investment_capacity_ratio=0.4125, risk_score=0.55
    )
    frame = rl_engine.build_goal_frame(goals, lookup, profile["user_id"].iloc[0])
    env = rl_engine.make_env(
        profile=profile, goals=frame, market=research_loader.market_frame()
    )

    # Deliberately supply the allocations in the OPPOSITE order to the env's slots.
    allocations = [
        {"goal_ref": "G3", "monthly_savings_contribution": 0.0, "monthly_investment_contribution": 0.0},
        {"goal_ref": "G2", "monthly_savings_contribution": 0.0, "monthly_investment_contribution": 0.0},
        {"goal_ref": "G1", "monthly_savings_contribution": 5_000.0, "monthly_investment_contribution": 1_000.0},
    ]
    encoded = rl_engine.encode_plan_for_env(env, allocations)

    # Expected: G1 is the first slot (18 months), so its money lands on row 0.
    expected = rl_engine.encode_plan_action(
        savings_per_goal=[5_000.0, 0.0, 0.0],
        investments_per_goal=[1_000.0, 0.0, 0.0],
        n_slots=rl_engine.RL_GOAL_SLOTS,
    )
    assert np.allclose(encoded, expected), (
        f"slot order was ignored: encoded={encoded.tolist()} expected={expected.tolist()}"
    )


def test_lp_replay_credits_the_plan_instead_of_leaking_it_as_unallocated():
    """A plan replayed through the simulator must actually reach the goal it named."""
    from app.engines import selector

    goals = sorted(_goals(), key=lambda g: (-g.priority, g.target_date))
    lookup = {g.id: max(1, (g.target_date - dt.date.today()).days // 30) for g in goals}
    lp = lp_engine.solve(goals=goals, cashflow=_cashflow(), flow_only=True)
    metrics = selector._trajectory_metrics(
        goals=goals,
        cashflow=_cashflow(),
        months_lookup=lookup,
        allocations=lp.allocations,
        capacity_ratio=0.4125,
        label="regression",
    )
    assert metrics is not None
    planned = float(lp.summary["monthly_contributions_allocated"])
    credited = float(metrics["monthly_contribution_credited_avg"])
    # Before the fix the credited figure collapsed to ~6% of the plan because the budget was
    # routed to an already-funded goal and the remainder became unallocated.
    assert credited > 0.5 * planned, (
        f"only {credited:,.0f} of a {planned:,.0f}/month plan was credited; "
        "the plan is being replayed against the wrong goal slots"
    )


def test_replayed_balance_sheet_reconciles():
    """cash + portfolio - loan = net worth, and earmarked money is a memo subset of assets."""
    goals = _goals()
    lookup = {g.id: max(1, (g.target_date - dt.date.today()).days // 30) for g in goals}
    profile = rl_engine.build_profile_row(
        _cashflow(), investment_capacity_ratio=0.4125, risk_score=0.55
    )
    frame = rl_engine.build_goal_frame(goals, lookup, profile["user_id"].iloc[0])
    env = rl_engine.make_env(
        profile=profile, goals=frame, market=research_loader.market_frame()
    )
    lp = lp_engine.solve(goals=goals, cashflow=_cashflow(), flow_only=True)
    action = rl_engine.encode_plan_for_env(env, lp.allocations)
    outcome = rl_engine.rollout(
        env=rl_engine.make_env(profile=profile, goals=frame, market=research_loader.market_frame()),
        action_provider=lambda _env, _month: action,
        label="reconciliation",
    )
    m = outcome.metrics
    assert m["final_cash"] + m["final_portfolio"] - m["final_loan_balance"] == pytest.approx(
        m["net_worth"], abs=0.01
    )
    assert 0 <= m["earmarked_goal_funding"] <= m["final_cash"] + m["final_portfolio"] + 0.01
    assert m["final_unearmarked_cash"] == pytest.approx(
        max(0.0, m["final_cash"] - m["earmarked_goal_funding"]), abs=0.01
    )
    assert m["accounting_mode"] in {"ledger", "legacy"}
    # The budget identity: every rupee of the monthly budget was allocated or left unallocated.
    assert m["unallocated_budget_total"] >= 0


# --------------------------------------------------------------------------------------
# B. hybrid theta
# --------------------------------------------------------------------------------------
def test_hybrid_theta_reads_the_requested_mix_not_the_censored_realised_fraction():
    """The realised investment fraction is capped by the ceiling it is used to set."""
    summary = {
        "monthly_savings_contribution": 100.0,
        "monthly_investment_contribution": 5.0,      # realised ≈ 0.048 (post-cap)
        "requested_investment_fraction": 0.30,        # what the policy asked for
        "loan_principal": 0.0,
    }
    theta = hybrid_engine.derive_theta(
        ArmResult(algorithm="rl", status="optimal", feasible=True, summary=summary),
        base_capacity_ratio=0.40,
    )
    assert theta.theta_source == "policy_requested_mix"
    assert theta.rl_requested_investment_fraction == pytest.approx(0.30)
    assert theta.rl_observed_investment_fraction == pytest.approx(5.0 / 105.0)
    assert theta.effective_capacity_ratio == pytest.approx(0.30)


def test_hybrid_theta_falls_back_and_says_so_when_the_request_is_absent():
    summary = {
        "monthly_savings_contribution": 100.0,
        "monthly_investment_contribution": 20.0,
        "loan_principal": 0.0,
    }
    theta = hybrid_engine.derive_theta(
        ArmResult(algorithm="rl", status="optimal", feasible=True, summary=summary),
        base_capacity_ratio=0.40,
    )
    assert theta.theta_source == "realized_credit_fallback"
    assert theta.effective_capacity_ratio == pytest.approx(20.0 / 120.0)


# --------------------------------------------------------------------------------------
# C. feasibility basis
# --------------------------------------------------------------------------------------
def test_goal_feasibility_uses_the_goal_budget_not_gross_surplus():
    """A goal the buffer has already claimed the money for is not 'feasible'."""
    goal = Goal(1, 900_000, 24)
    projection = project_goals(
        [goal],
        inflation=0.03,
        savings_return=0.0,
        investment_return=0.05,
        monthly_surplus=40_000,   # gross
        goal_budget=10_000,       # after a large protected buffer
        available_cash=0.0,
    )[0]
    assert projection.goal_budget == pytest.approx(10_000)
    assert projection.required_monthly_contribution > 10_000
    assert projection.feasibility == "infeasible_on_current_cashflow"
    assert "available for goals" in " ".join(projection.notes)


# --------------------------------------------------------------------------------------
# D. risk profile wiring
# --------------------------------------------------------------------------------------
def test_capacity_ratio_uses_declared_liquidity_and_loss_ability():
    high, _ = lp_engine.derive_investment_capacity_ratio(
        risk_capacity=0.8, liquidity_requirement="high", loss_ability="low"
    )
    low, _ = lp_engine.derive_investment_capacity_ratio(
        risk_capacity=0.8, liquidity_requirement="low", loss_ability="high"
    )
    assert high < low
    assert high == pytest.approx(0.30)  # 0.8 x 0.5, capped by the low loss-ability ceiling 0.30
    assert low == pytest.approx(0.80)   # 0.8 x 1.0, no further cap under high loss ability


# --------------------------------------------------------------------------------------
# E. API-level regressions
# --------------------------------------------------------------------------------------
def test_run_detail_returns_a_payload_instead_of_null(registered):
    seed_profile_and_goal(registered, goals=1)
    created = registered["client"].post(
        "/api/optimize/plan", headers=registered["headers"], json={"algorithm": "lp"}
    )
    assert created.status_code == 200, created.text
    run_id = created.json()["run_id"]

    detail = registered["client"].get(
        f"/api/optimize/runs/{run_id}", headers=registered["headers"]
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body is not None, "the run detail endpoint returned null"
    assert body["run_id"] == run_id
    assert body["allocations"], "the detail payload lost its allocations"
    assert body["objective_definition"]


def test_objective_survives_a_reload_without_money_rounding(registered):
    seed_profile_and_goal(registered, goals=2)
    created = registered["client"].post(
        "/api/optimize/plan", headers=registered["headers"], json={"algorithm": "lp"}
    )
    assert created.status_code == 200, created.text
    fresh = created.json()["objective_value"]
    latest = registered["client"].get(
        "/api/optimize/plan/latest", headers=registered["headers"]
    ).json()["objective_value"]
    assert fresh == pytest.approx(latest, abs=1e-6), (
        f"create returned {fresh!r} and a reload returned {latest!r}"
    )
    assert fresh is not None and fresh != round(fresh, 2), (
        "the objective was rounded to two decimals, which is the money formatter"
    )
    assert "NOT a cash amount" in created.json()["objective_definition"]


def test_plan_reports_readiness_separately_from_goal_feasibility(registered):
    """Emergency fund at 0% must not be hidden by 'every goal funded'."""
    seed_profile_and_goal(registered, goals=1, cash=0)
    body = registered["client"].get("/api/profile/summary", headers=registered["headers"]).json()
    assert body["emergency_fund_progress"] == 0.0

    plan = registered["client"].post(
        "/api/optimize/plan", headers=registered["headers"], json={"algorithm": "lp"}
    )
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["readiness"]["emergency_fund"]["progress"] == 0.0
    assert payload["readiness"]["status"] in {
        "emergency_fund_incomplete",
        "buffer_shortfall",
        "debt_stressed",
        "deficit",
    }
    assert any("Emergency fund" in warning for warning in payload["warnings"]), (
        "the emergency-fund warning never reached the plan's warnings"
    )


def test_scenario_runs_are_kept_out_of_the_plan_history(registered):
    seed_profile_and_goal(registered, goals=1)
    headers = registered["headers"]
    client = registered["client"]

    scenario = client.post(
        "/api/scenarios/run",
        headers=headers,
        json={"preset": "income_down", "parameters": {"income_reduction_pct": 0.2}},
    )
    assert scenario.status_code == 200, scenario.text

    runs = client.get("/api/optimize/runs?kind=plan", headers=headers).json()["items"]
    assert all(row["kind"] == "plan" for row in runs)
    assert runs == [], "scenario baseline/stressed runs leaked into the plan history"

    history = client.get("/api/scenarios/runs", headers=headers).json()["items"]
    assert history and history[0]["preset"] == "income_down"


def test_editing_a_goal_into_the_past_is_rejected(registered):
    seeded = seed_profile_and_goal(registered, goals=1)
    goal_id = seeded["goals"][0]["id"]
    response = registered["client"].put(
        f"/api/goals/{goal_id}",
        headers=registered["headers"],
        json={"target_date": (dt.date.today() - dt.timedelta(days=30)).isoformat()},
    )
    assert response.status_code == 422, response.text


def test_public_education_endpoint_separates_teaching_from_advice(registered):
    body = registered["client"].get("/api/meta/education").json()
    assert len(body["items"]) >= 5
    topics = {item["topic"].lower() for item in body["items"]}
    assert {"inflation", "investment risk", "diversification"} <= topics
    assert "uncited" in body["citation_policy"].lower()
    assert "text only" in body["separation_note"].lower()
    assert "cannot override a financial constraint" in body["separation_note"].lower()


def test_compare_labels_the_hybrid_basis_truthfully(registered):
    seed_profile_and_goal(registered, goals=2)
    body = registered["client"].post(
        "/api/optimize/compare", headers=registered["headers"]
    ).json()
    by_arm = {arm["algorithm"]: arm for arm in body["arms"]}
    assert body["metric_definitions"], "the comparison carries no metric definitions"
    for arm in body["arms"]:
        if arm["metric_basis"] == "trajectory":
            assert arm["metrics_comparable"].get("pct_goals_met_by_deadline") is not None, (
                f"{arm['algorithm']} is labelled trajectory but has no deadline metric"
            )
    # The hybrid must never be ranked on its static summary while claiming to be a replay.
    if by_arm.get("hybrid", {}).get("metric_basis") == "static_plan":
        assert by_arm["hybrid"]["ranked"] is False
