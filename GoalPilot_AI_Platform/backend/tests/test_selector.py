"""RL readiness, the hybrid, and the algorithm-selection decision.

The RL tests load torch and run a real policy rollout, so they are marked ``slow`` and are
skipped when the research checkpoint is not reachable.
"""
from __future__ import annotations

import pytest

from app.engines import hybrid_engine, lp_engine, research_loader, rl_engine, selector
from app.services.money import months_between
from tests.test_financial_calc import Ast, Goal, Liab, Src

pytestmark = pytest.mark.skipif(
    not research_loader.is_available(), reason="The research project is not reachable."
)

RL_READY = rl_engine.readiness().get("available", False)
requires_rl = pytest.mark.skipif(not RL_READY, reason="No trained RL checkpoint available.")


def make_cashflow(**overrides):
    from app.services.cashflow import build_cashflow

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
    )
    kwargs.update(overrides)
    return build_cashflow(**kwargs)


def lookup(goals):
    import datetime as _dt

    today = _dt.date.today()
    return {g.id: max(1, months_between(today, g.target_date)) for g in goals}


# --------------------------------------------------------------------------------------
# environment wrapper
# --------------------------------------------------------------------------------------
def test_population_row_mapping_is_documented_and_correct():
    cf = make_cashflow()
    row = rl_engine.build_profile_row(cf, investment_capacity_ratio=0.4, risk_score=0.55)
    assert row.iloc[0]["monthly_income"] == 90_000
    assert row.iloc[0]["monthly_expenditure"] == 36_000  # essential + discretionary
    assert row.iloc[0]["monthly_emi"] == 12_000
    assert row.iloc[0]["initial_savings"] == 420_000
    assert row.iloc[0]["investment_capacity_ratio"] == 0.4
    notes = rl_engine.mapping_notes(cf, 0.4)
    assert any("monthly_emi" in n for n in notes)
    assert any("investment_capacity_ratio" in n for n in notes)


def test_capacity_derivation_separates_appetite_from_capacity():
    low, why_low = lp_engine.derive_investment_capacity_ratio(
        risk_capacity=0.9, liquidity_requirement="high", loss_ability="low"
    )
    high, _ = lp_engine.derive_investment_capacity_ratio(
        risk_capacity=0.9, liquidity_requirement="low", loss_ability="high"
    )
    assert low < high
    assert low <= 0.30  # the loss-ability ceiling binds
    assert "risk_capacity" in why_low


def test_env_refuses_more_goals_than_the_trained_action_width():
    goals = [Goal(i, 50_000, 12 * i, funded=0) for i in range(1, 8)]  # 7 goals > 5 slots
    result = rl_engine.solve(goals=goals, cashflow=make_cashflow(), months_lookup=lookup(goals))
    assert result.status == "unavailable"
    assert result.fallback_reason == "goal_slot_limit"
    assert result.feasible is False
    assert result.allocations == []


@requires_rl
@pytest.mark.slow
def test_rl_policy_produces_a_valid_trajectory():
    goals = [Goal(1, 90_000, 12, funded=10_000), Goal(2, 300_000, 36, funded=50_000)]
    result = rl_engine.solve(
        goals=goals, cashflow=make_cashflow(), months_lookup=lookup(goals)
    )
    assert result.status == "optimal", result.warnings
    assert result.feasible is True
    assert len(result.allocations) == 2
    metrics = result.summary
    assert 0.0 <= metrics["weighted_goal_achievement"] <= 1.0
    assert metrics["months_simulated"] > 0
    # every month satisfied the budget identity
    assert result.diagnostics["validation"]["clean"] is True


@requires_rl
@pytest.mark.slow
def test_rl_rollout_is_deterministic_for_the_same_inputs():
    goals = [Goal(1, 120_000, 24, funded=5_000)]
    first = rl_engine.solve(goals=goals, cashflow=make_cashflow(), months_lookup=lookup(goals))
    second = rl_engine.solve(goals=goals, cashflow=make_cashflow(), months_lookup=lookup(goals))
    assert first.summary == second.summary


@requires_rl
@pytest.mark.slow
def test_rollout_disables_financing_for_every_arm():
    goals = [Goal(1, 120_000, 24, funded=5_000)]
    result = rl_engine.solve(goals=goals, cashflow=make_cashflow(), months_lookup=lookup(goals))
    assert result.diagnostics["financing_disabled_in_rollout"] is True


def test_rl_reports_unavailable_rather_than_faking_a_policy(monkeypatch):
    original = rl_engine.get_settings

    class FakeSettings:
        enable_rl = False
        default_rl_checkpoint = "nope.zip"

        def rl_checkpoint_path(self, relative=None):
            return None

    monkeypatch.setattr(rl_engine, "get_settings", lambda: FakeSettings())
    goals = [Goal(1, 100_000, 12, funded=0)]
    result = rl_engine.solve(goals=goals, cashflow=make_cashflow(), months_lookup=lookup(goals))
    assert result.status == "unavailable"
    assert result.fallback_reason in ("checkpoint_missing", "rl_disabled")
    assert result.summary == {}
    monkeypatch.setattr(rl_engine, "get_settings", original)


# --------------------------------------------------------------------------------------
# hybrid
# --------------------------------------------------------------------------------------
@requires_rl
@pytest.mark.slow
def test_hybrid_executes_end_to_end_and_respects_constraints():
    goals = [Goal(1, 150_000, 18, funded=10_000), Goal(2, 260_000, 30, funded=20_000)]
    result = hybrid_engine.solve(
        goals=goals, cashflow=make_cashflow(), months_lookup=lookup(goals)
    )
    assert result.status == "optimal", result.warnings
    assert result.feasible is True
    theta = result.diagnostics["theta"]
    assert 0.0 <= theta["effective_capacity_ratio"] <= theta["base_capacity_ratio"] + 1e-9
    assert result.diagnostics["rl_component"]["status"] == "optimal"
    # the LP stage's plan passed platform validation
    assert result.diagnostics["lp_status"] == "optimal"


@requires_rl
@pytest.mark.slow
def test_hybrid_theta_can_only_tighten_never_loosen():
    """The safety property: theta cannot raise the ceiling or add financing."""
    goals = [Goal(1, 200_000, 24, funded=0)]
    cf = make_cashflow()
    base, _ = lp_engine.derive_investment_capacity_ratio(risk_capacity=cf.risk_capacity)
    result = hybrid_engine.solve(goals=goals, cashflow=cf, months_lookup=lookup(goals))
    theta = result.diagnostics["theta"]
    assert theta["effective_capacity_ratio"] <= base + 1e-9
    invested = sum(r["monthly_investment_contribution"] for r in result.allocations)
    assert invested <= float(result.constraints.get("investment_permitted", invested)) + 1e-4


def test_hybrid_falls_back_transparently_when_rl_is_unavailable():
    goals = [Goal(i, 60_000, 12 * i, funded=0) for i in range(1, 8)]  # too many goals for RL
    result = hybrid_engine.solve(
        goals=goals, cashflow=make_cashflow(), months_lookup=lookup(goals)
    )
    assert result.fallback_reason == "goal_slot_limit"
    assert result.status in ("optimal", "infeasible")
    assert any("fell back to the plain LP plan" in w for w in result.warnings)


# --------------------------------------------------------------------------------------
# selector
# --------------------------------------------------------------------------------------
@requires_rl
@pytest.mark.slow
def test_selector_compares_all_arms_on_one_basis_and_names_the_lp_by_default():
    goals = [Goal(1, 90_000, 12, funded=10_000), Goal(2, 300_000, 36, funded=50_000)]
    comparison = selector.compare(
        goals=goals, cashflow=make_cashflow(), months_lookup=lookup(goals)
    )
    algorithms = {a["algorithm"] for a in comparison["arms"]}
    assert {"lp", "rl", "hybrid", "rule_baseline"} <= algorithms
    assert comparison["recommended_algorithm"] in algorithms
    assert comparison["decision_rule"]["default"] == "lp"
    # every arm reports the basis it was scored on
    assert all(a["metric_basis"] in ("trajectory", "static_plan") for a in comparison["arms"])
    # the LP baseline is scored on the trajectory basis here, so arms are comparable
    lp = next(a for a in comparison["arms"] if a["algorithm"] == "lp")
    assert lp["metric_basis"] == "trajectory"
    # each non-selected arm carries a stated reason
    assert all(entry["reason"] for entry in comparison["not_selected"])
    assert len(comparison["notes"]) >= 3


@requires_rl
@pytest.mark.slow
def test_selector_does_not_promote_rl_without_a_real_margin():
    """The research found RL does not beat simple rules; the selector must not contradict it."""
    goals = [Goal(1, 90_000, 12, funded=10_000), Goal(2, 300_000, 36, funded=50_000)]
    comparison = selector.compare(
        goals=goals, cashflow=make_cashflow(), months_lookup=lookup(goals)
    )
    if comparison["recommended_algorithm"] != "lp":
        best = next(
            a for a in comparison["arms"] if a["algorithm"] == comparison["recommended_algorithm"]
        )
        lp = next(a for a in comparison["arms"] if a["algorithm"] == "lp")
        gain = (
            float(best["metrics"].get("weighted_goal_achievement", 0))
            - float(lp["metrics"].get("weighted_goal_achievement", 0))
        )
        assert gain >= comparison["decision_rule"]["min_achievement_gain"] - 1e-9
        assert comparison["sufficient_evidence_for_change"] is True
    else:
        assert comparison["sufficient_evidence_for_change"] is False
        assert "LP" in comparison["recommendation_reason"]


def test_selector_handles_a_goal_set_beyond_the_rl_width():
    goals = [Goal(i, 40_000, 12 * i, funded=0) for i in range(1, 8)]
    comparison = selector.compare(
        goals=goals, cashflow=make_cashflow(), months_lookup=lookup(goals)
    )
    rl = next(a for a in comparison["arms"] if a["algorithm"] == "rl")
    assert rl["available"] is False
    assert rl["metrics"] == {}  # no fabricated metric
    assert any("not evaluated" in n or "unavailable" in n for n in comparison["notes"])


def test_algorithm_availability_endpoint(client, registered):
    from tests.conftest import seed_profile_and_goal

    seed_profile_and_goal(registered)
    response = client.get("/api/optimize/algorithms", headers=registered["headers"])
    assert response.status_code == 200
    arms = {a["algorithm"]: a for a in response.json()}
    assert arms["lp"]["ready"] is True
    assert arms["lp"]["detail"]["model_version"].startswith("constrained_lp")
    # an unavailable arm must carry a reason rather than a silent omission
    for arm in arms.values():
        if not arm["ready"]:
            assert arm["reason"]
