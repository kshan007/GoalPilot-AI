"""LP vs RL parity tests (audit finding F-06).

The audit found the two sides of the project were compared while using *different* goal
targets and *different* assumptions:

    LP : future_goal_cost = current_cost * (1 + annual_inflation) ** (months / 12)
    RL : goal_targets     = current_cost

`GoalPilotConfig.lp_parity()` removes that discrepancy. These tests assert the two agree.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import goalpilot_env
from goalpilot_config import GoalPilotConfig

EXTENSION = Path(__file__).resolve().parents[1] / "GoalPilot_MultiGoal_Extension"
if str(EXTENSION) not in sys.path:
    sys.path.insert(0, str(EXTENSION))

lp = pytest.importorskip(
    "src.multi_goal_optimizer",
    reason="GoalPilot_MultiGoal_Extension is required for the LP parity tests",
)


def test_lp_inflates_and_rl_can_match_it(rl_data):
    """rl env with target_basis='inflated' must reproduce the LP's future_goal_cost."""
    goals = rl_data["goals"]
    prepared = lp.prepare_goals(
        goals[["goal_id", "goal_name", "current_cost", "target_date",
               "time_horizon_months", "priority", "criticality", "existing_funding"]],
        annual_inflation=0.03,
    )

    env = goalpilot_env.GoalPilotEnv(
        profiles=rl_data["profiles"], goals=goals, market=rl_data["market"],
        config=GoalPilotConfig.lp_parity(),
    )
    uid = rl_data["profiles"]["user_id"].astype(str).iloc[0]
    env.reset(options={"user_id": uid})

    expected = prepared.loc[
        goals["user_id"].astype(str) == uid
    ].sort_values("time_horizon_months")["future_goal_cost"].to_numpy()
    np.testing.assert_allclose(env.goal_targets, expected, rtol=1e-12, atol=1e-8)


def test_archived_rl_target_is_nominal(rl_data):
    """The archived RL behaviour must still be nominal (so archived numbers reproduce)."""
    goals = rl_data["goals"]
    env = goalpilot_env.GoalPilotEnv(
        profiles=rl_data["profiles"], goals=goals, market=rl_data["market"],
        config=GoalPilotConfig.archived(),
    )
    uid = rl_data["profiles"]["user_id"].astype(str).iloc[0]
    env.reset(options={"user_id": uid})
    nominal = goals.loc[
        goals["user_id"].astype(str) == uid
    ].sort_values("time_horizon_months")["current_cost"].to_numpy()
    np.testing.assert_allclose(env.goal_targets, nominal, rtol=1e-12, atol=1e-8)


def test_parity_removes_the_target_basis_gap(rl_data):
    """The gap the audit reported is material, and the fix closes it."""
    goals = rl_data["goals"]
    uid = rl_data["profiles"]["user_id"].astype(str).iloc[0]

    nominal_env = goalpilot_env.GoalPilotEnv(
        profiles=rl_data["profiles"], goals=goals, market=rl_data["market"],
        config=GoalPilotConfig.archived(),
    )
    parity_env = goalpilot_env.GoalPilotEnv(
        profiles=rl_data["profiles"], goals=goals, market=rl_data["market"],
        config=GoalPilotConfig.lp_parity(),
    )
    nominal_env.reset(options={"user_id": uid})
    parity_env.reset(options={"user_id": uid})

    ratio = parity_env.goal_targets / nominal_env.goal_targets
    assert ratio.min() >= 1.0 - 1e-12
    assert ratio.max() > 1.05, "expected a material inflation gap to be closed"


def test_lp_still_solves_under_the_parity_basis(rl_data):
    """The LP must remain functional on the RL panel (regression guard)."""
    goals = rl_data["goals"]
    profiles = rl_data["profiles"]
    uid = profiles["user_id"].astype(str).iloc[0]
    p = profiles.loc[profiles["user_id"].astype(str) == uid].iloc[0]
    user_goals = goals.loc[goals["user_id"].astype(str) == uid].copy()

    state = lp.FinancialState(
        monthly_income=float(p["monthly_income"]),
        essential_expenses=float(p["monthly_expenditure"]),
        existing_emi=float(p["monthly_emi"]),
        liquid_savings=float(p["initial_savings"]),
        existing_investments=float(p["initial_investment"]),
        usable_existing_investments=0.0,
        emergency_months=6.0,
        emi_income_ratio_cap=0.35,
        risk_capacity=float(p["risk_score"]),
    )
    result = lp.optimize_multi_goal(
        user_goals, state,
        annual_inflation=0.03, savings_return=0.0, investment_return=0.05,
        investment_risk_score=0.4, loan_annual_rate=0.12, loan_tenure_months=60,
        max_loan_per_goal=150000.0,
    )
    assert result["status"] == "optimal"
    summary = result["summary"]
    assert summary["monthly_surplus_respected"]
    assert summary["emi_cap_respected"]
    assert summary["combined_monthly_cashflow_respected"]
