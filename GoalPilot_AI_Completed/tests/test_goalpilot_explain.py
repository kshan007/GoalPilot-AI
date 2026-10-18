"""Tests for the Phase-I explainability layer (goalpilot_explain / goalpilot_knowledge).

These protect three properties:
  1. the knowledge layer is grounded (retrieval returns real entries; unknown -> empty),
  2. every number in an explanation is traceable to simulator state (no invention),
  3. explanations distinguish computed facts from general principles and make no guarantee.
"""
from __future__ import annotations

import numpy as np
import pytest

import goalpilot_explain as ge
import goalpilot_env
from goalpilot_config import GoalPilotConfig
from goalpilot_knowledge import DEFAULT_KB, PRINCIPLES, UNCITED


def savings_only(env):
    a = np.zeros(env.action_space.shape, dtype=np.float32)
    a[:, 0] = 1.0
    return a


def investment_only(env):
    a = np.zeros(env.action_space.shape, dtype=np.float32)
    a[:, 1] = 1.0
    return a


def make_env(small_slice, config=None):
    cfg = config or GoalPilotConfig.recommended()
    return goalpilot_env.GoalPilotEnv(
        profiles=small_slice["profiles"], goals=small_slice["goals"],
        market=small_slice["market"], user_ids=small_slice["user_ids"], config=cfg)


# ---- knowledge layer -------------------------------------------------------------------
def test_retrieval_returns_relevant_entries():
    assert DEFAULT_KB.retrieve("how big should my emergency fund be")[0].id == "emergency_fund"
    assert "debt_service_first" in [p.id for p in DEFAULT_KB.retrieve("loan emi interest")]


def test_retrieval_unknown_query_is_empty_not_a_guess():
    assert DEFAULT_KB.retrieve("zzzz qqqq unrelated topic") == []
    assert DEFAULT_KB.retrieve("") == []


def test_every_principle_is_marked_uncited():
    assert PRINCIPLES, "the knowledge base must not be empty"
    assert all(p["status"] == UNCITED for p in PRINCIPLES)


# ---- facts are grounded in simulator state ---------------------------------------------
def test_facts_match_simulator_state(small_slice):
    env = make_env(small_slice)
    res = ge.rollout(env, savings_only, small_slice["user_ids"][0])
    facts = ge.build_facts(env, res)

    n = len(env.user_goals)
    target = np.asarray(env.goal_targets, dtype=float)[:n]
    funded = np.asarray(env.goal_balances, dtype=float)[:n]

    assert facts["totals"]["total_target"] == pytest.approx(float(target.sum()), rel=1e-12)
    assert facts["totals"]["total_shortfall"] == pytest.approx(
        float(np.maximum(0.0, target - funded).sum()), rel=1e-12)
    assert facts["balance_sheet"]["net_worth"] == pytest.approx(float(env.net_worth), rel=1e-12)
    assert facts["balance_sheet"]["earmarked_goal_funding"] == pytest.approx(
        float(env.earmarked_goal_funding), rel=1e-12)
    # the earmark is a subset of assets, never added on top of net worth
    assert facts["balance_sheet"]["earmarked_goal_funding"] <= (
        facts["balance_sheet"]["cash"] + facts["balance_sheet"]["portfolio"] + 1e-6)


def test_budget_identity_holds_during_lineaged_rollout(small_slice):
    env = make_env(small_slice)
    res = ge.rollout(env, investment_only, small_slice["user_ids"][0])
    facts = ge.build_facts(env, res)
    assert facts["execution"]["max_budget_residual"] < 1e-6
    assert facts["execution"]["affordability_violations"] == 0


# ---- explanation structure and tone ----------------------------------------------------
def test_explanation_has_all_sections_and_is_grounded(small_slice):
    env = make_env(small_slice)
    ex = ge.explain(env, small_slice["user_ids"][0], savings_only)
    for key in ("goals_and_constraints", "why_this_allocation", "why_others_received_less",
                "expected_shortfalls_and_deadline_risk", "role_of_savings_returns_and_borrowing",
                "sensitivity", "what_could_change_the_result"):
        assert ex["sections"][key], f"section {key} must be non-empty"
    assert ex["grounding"]["numbers_are"] == "computed, not forecast"
    assert ex["grounding"]["principles"], "at least one principle should be cited"
    assert all(p["status"] == UNCITED for p in ex["grounding"]["principles"])


def test_no_return_guarantee_language(small_slice):
    env = make_env(small_slice)
    text = ge.render_markdown(ge.explain(env, small_slice["user_ids"][0], savings_only)).lower()
    for banned in ("guarantee", "guaranteed", "will earn", "risk-free", "assured return"):
        assert banned not in text


def test_structurally_infeasible_user_is_reported(rl_data):
    """A user with non-positive investable surplus must be flagged as structurally infeasible."""
    p = rl_data["profiles"]
    surplus = (p["monthly_income"] - p["monthly_expenditure"] - p["monthly_emi"])
    uid = str(p.loc[surplus <= 0, "user_id"].iloc[0])
    env = goalpilot_env.GoalPilotEnv(
        profiles=p, goals=rl_data["goals"], market=rl_data["market"],
        user_ids=[uid], config=GoalPilotConfig.recommended())
    ex = ge.explain(env, uid, savings_only)
    joined = " ".join(ex["sections"]["expected_shortfalls_and_deadline_risk"])
    assert "structurally infeasible" in joined
    assert ex["facts"]["profile"]["investable_surplus"] <= 0


# ---- sensitivity -----------------------------------------------------------------------
def test_sensitivity_is_deterministic_and_capacity_zero_stops_investment(small_slice):
    variants = [ge.Variant("capacity x0", capacity_multiplier=0.0),
                ge.Variant("market x0.5", nifty_multiplier=0.5)]
    a = ge.sensitivity(small_slice["profiles"], small_slice["goals"], small_slice["market"],
                       small_slice["user_ids"][0], GoalPilotConfig.recommended(),
                       investment_only, variants)
    b = ge.sensitivity(small_slice["profiles"], small_slice["goals"], small_slice["market"],
                       small_slice["user_ids"][0], GoalPilotConfig.recommended(),
                       investment_only, variants)
    assert a == b, "sensitivity must be deterministic"
    by_name = {v["name"]: v for v in a["variants"]}
    assert by_name["capacity x0"]["total_invest_executed"] == pytest.approx(0.0, abs=1e-6)
    assert by_name["capacity x0"]["total_shortfall"] >= a["baseline"]["total_shortfall"] - 1e-6
    assert by_name["market x0.5"]["total_invest_executed"] > 0


def test_explanation_can_carry_sensitivity(small_slice):
    env = make_env(small_slice)
    variants = [ge.Variant("capacity x0.5", capacity_multiplier=0.5)]
    sens = ge.sensitivity(small_slice["profiles"], small_slice["goals"], small_slice["market"],
                          small_slice["user_ids"][0], GoalPilotConfig.recommended(),
                          savings_only, variants)
    ex = ge.explain(env, small_slice["user_ids"][0], savings_only, sensitivity=sens)
    joined = " ".join(ex["sections"]["sensitivity"])
    assert "capacity x0.5" in joined
    assert "what-if" in joined
