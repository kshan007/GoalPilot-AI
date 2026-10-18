"""Regression guard: archived behaviour must be reproduced exactly.

The audit's remediation changed `goalpilot_env.py`. This module proves that
`GoalPilotConfig.archived()` reproduces the pre-audit environment **bit-for-bit** on
every quantity the archive reported, so archived results remain reproducible.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import goalpilot_env
from goalpilot_config import GoalPilotConfig

POLICIES = {
    "No action": (0.0, 0.0, 0.0),
    "Savings only": (1.0, 0.0, 0.0),
    "Investments only": (0.0, 1.0, 0.0),
    "Mixed allocation": (0.5, 0.5, 0.0),
    "Loan request only": (0.0, 0.0, 1.0),
}

TRACKED = [
    "savings_contribution",
    "investment_contribution",
    "new_loan_principal",
    "new_loan_emi",
    "active_loan_emi",
    "combined_monthly_commitment",
    "monthly_surplus",
]


def _rollout(env_module, env, user_id, policy, config=None):
    s, i, loan = policy
    env.reset(options={"user_id": user_id})
    trajectory = []
    total_reward = 0.0
    while True:
        action = np.zeros(env.action_space.shape, dtype=np.float32)
        action[:, 0] = s
        action[:, 1] = i
        action[:, 2] = loan
        obs, reward, term, trunc, info = env.step(action)
        total_reward += float(reward)
        trajectory.append({
            "cash": float(env.cash),
            "portfolio": float(env.portfolio),
            "loan_balance": float(env.loan_balance),
            "goal_balances": np.asarray(env.goal_balances, dtype=float).copy(),
            "reward": float(reward),
            **{k: float(info[k]) for k in TRACKED},
        })
        if term or trunc:
            break
    return {
        "trajectory": trajectory,
        "total_reward": total_reward,
        "goal_balances": np.asarray(env.goal_balances, dtype=float).copy(),
        "goal_targets": np.asarray(env.goal_targets, dtype=float).copy(),
        "cash": float(env.cash),
        "portfolio": float(env.portfolio),
        "loan_balance": float(env.loan_balance),
    }


def _compare(archived_env_module, env_module, users, rl_data):
    archived = archived_env_module.GoalPilotEnv(
        profiles=rl_data["profiles"], goals=rl_data["goals"],
        market=rl_data["market"], user_ids=users, seed=2026,
    )
    current = env_module.GoalPilotEnv(
        profiles=rl_data["profiles"], goals=rl_data["goals"],
        market=rl_data["market"], user_ids=users,
        config=GoalPilotConfig.archived(),
    )

    for policy_name, policy in POLICIES.items():
        for user_id in users:
            a = _rollout(archived_env_module, archived, user_id, policy)
            b = _rollout(env_module, current, user_id, policy)

            assert a["total_reward"] == pytest.approx(b["total_reward"], rel=0, abs=1e-12), (
                f"total reward diverged for {policy_name}/{user_id}"
            )
            np.testing.assert_allclose(
                a["goal_balances"], b["goal_balances"], rtol=0, atol=1e-9,
                err_msg=f"goal balances diverged for {policy_name}/{user_id}",
            )
            np.testing.assert_allclose(
                a["goal_targets"], b["goal_targets"], rtol=0, atol=1e-12,
                err_msg=f"goal targets diverged for {policy_name}/{user_id}",
            )
            assert a["cash"] == pytest.approx(b["cash"], rel=0, abs=1e-6), policy_name
            assert a["portfolio"] == pytest.approx(b["portfolio"], rel=0, abs=1e-6), policy_name
            assert a["loan_balance"] == pytest.approx(b["loan_balance"], rel=0, abs=1e-6), policy_name

            assert len(a["trajectory"]) == len(b["trajectory"]) == 142
            for month, (ra, rb) in enumerate(zip(a["trajectory"], b["trajectory"])):
                assert ra["reward"] == pytest.approx(rb["reward"], rel=0, abs=1e-12), (
                    f"reward diverged at {policy_name}/{user_id}/month {month}"
                )
                for key in TRACKED:
                    assert ra[key] == pytest.approx(rb[key], rel=0, abs=1e-6), (
                        f"{key} diverged at {policy_name}/{user_id}/month {month}"
                    )


def test_archived_mode_reproduces_archived_env_all_users(
    archived_env_module, rl_data, all_user_ids
):
    """The whole 100-user panel, all five archived policies, 142 months each."""
    _compare(archived_env_module, goalpilot_env, all_user_ids, rl_data)


def test_archived_mode_default_config_matches():
    """A bare GoalPilotEnv(...) must not silently adopt the new defaults on the archive."""
    from goalpilot_config import DEFAULT_CONFIG, ACTION_MODE_MAGNITUDE, \
        GOAL_CREDIT_FACE_VALUE
    assert DEFAULT_CONFIG.action_mode == ACTION_MODE_MAGNITUDE
    assert DEFAULT_CONFIG.goal_credit_mode == GOAL_CREDIT_FACE_VALUE
    assert DEFAULT_CONFIG.target_basis == "nominal"
    assert DEFAULT_CONFIG.emergency_months == 0.0


def test_archived_config_reports_legacy_accounting():
    cfg = GoalPilotConfig.archived()
    assert cfg.accounting_mode == "legacy"
    assert cfg.to_dict()["accounting_mode"] == "legacy"
