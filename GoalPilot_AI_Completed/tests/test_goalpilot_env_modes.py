"""Behaviour-of-the-fixes tests: action semantics (F-02) and the mix degeneracy (F-01).

F-02: the archived action vector acted as a *magnitude*. ``budget_scale = min(1, budget/total)``
      never scales up, so a policy emitting below the saturation point silently underfunded
      goals, and above it the reward was flat. ``action_mode="share"`` normalises the action
      into shares so the whole available budget is always allocated.

F-01: savings-only and mixed-allocation produced *identical* goal funding because a rupee
      was credited at face value whichever vehicle carried it. ``goal_credit_mode=
      "growth_weighted"`` breaks that identity.
"""
from __future__ import annotations

import numpy as np
import pytest

import goalpilot_env
from goalpilot_config import (
    ACTION_MODE_MAGNITUDE,
    ACTION_MODE_SHARE,
    GOAL_CREDIT_FACE_VALUE,
    GOAL_CREDIT_GROWTH_WEIGHTED,
    GoalPilotConfig,
)

FLAT_SAVINGS = [0.25, 0.50, 0.75, 1.00]


def _make_env(rl_data, user_ids, config):
    return goalpilot_env.GoalPilotEnv(
        profiles=rl_data["profiles"], goals=rl_data["goals"],
        market=rl_data["market"], user_ids=user_ids, config=config,
    )


def _rollout(env, user_id, policy):
    s, i, loan = policy
    env.reset(options={"user_id": user_id})
    while True:
        action = np.zeros(env.action_space.shape, dtype=np.float32)
        action[:, 0] = s
        action[:, 1] = i
        action[:, 2] = loan
        obs, reward, term, trunc, info = env.step(action)
        if term or trunc:
            break
    return float(np.minimum(env.goal_balances, env.goal_targets).sum())


# --------------------------------------------------------------------------- F-02 -----

def test_magnitude_mode_has_a_saturation_plateau(small_slice):
    """Archived behaviour: 0.5 / 0.75 / 1.0 are indistinguishable, 0.25 is worse."""
    env = _make_env(small_slice, small_slice["user_ids"],
                    GoalPilotConfig.archived().replace(action_mode=ACTION_MODE_MAGNITUDE))
    per_user = {}
    for level in FLAT_SAVINGS:
        per_user[level] = [
            _rollout(env, uid, (level, 0.0, 0.0)) for uid in small_slice["user_ids"]
        ]
    np.testing.assert_allclose(per_user[0.50], per_user[0.75], rtol=1e-12, atol=1e-6)
    np.testing.assert_allclose(per_user[0.75], per_user[1.00], rtol=1e-12, atol=1e-6)
    # the low end must never do better, and must genuinely underfund for some users
    assert all(a <= b + 1e-6 for a, b in zip(per_user[0.25], per_user[1.00]))
    underfunded = sum(1 for a, b in zip(per_user[0.25], per_user[1.00]) if a < b - 1e-6)
    assert underfunded > 0, "F-02 handicap not reproduced on this slice"


def test_share_mode_makes_action_magnitude_irrelevant(small_slice):
    """F-02 fix: with share semantics every non-zero constant action allocates the budget."""
    env = _make_env(small_slice, small_slice["user_ids"],
                    GoalPilotConfig.archived().replace(action_mode=ACTION_MODE_SHARE))
    per_user = {}
    for level in FLAT_SAVINGS:
        per_user[level] = [
            _rollout(env, uid, (level, 0.0, 0.0)) for uid in small_slice["user_ids"]
        ]
    for level in FLAT_SAVINGS[1:]:
        np.testing.assert_allclose(
            per_user[level], per_user[FLAT_SAVINGS[0]], rtol=1e-12, atol=1e-6,
            err_msg=f"share mode still discriminates action magnitude at {level}",
        )


def test_share_mode_allocates_more_than_magnitude_mode_at_low_actions(small_slice):
    """The concrete benefit: a policy emitting 0.25 no longer loses 6% of goal funding."""
    mag = _make_env(small_slice, small_slice["user_ids"],
                    GoalPilotConfig.archived().replace(action_mode=ACTION_MODE_MAGNITUDE))
    sha = _make_env(small_slice, small_slice["user_ids"],
                    GoalPilotConfig.archived().replace(action_mode=ACTION_MODE_SHARE))
    mag_vals = [_rollout(mag, uid, (0.25, 0.0, 0.0)) for uid in small_slice["user_ids"]]
    sha_vals = [_rollout(sha, uid, (0.25, 0.0, 0.0)) for uid in small_slice["user_ids"]]
    assert all(s >= m - 1e-9 for m, s in zip(mag_vals, sha_vals))
    assert any(s > m + 1e-6 for m, s in zip(mag_vals, sha_vals))


def test_share_mode_never_exceeds_the_budget(small_slice):
    """Allocating the full budget must still respect the monthly cash-flow guard."""
    env = _make_env(small_slice, small_slice["user_ids"],
                    GoalPilotConfig.archived().replace(action_mode=ACTION_MODE_SHARE))
    for policy in [(1.0, 1.0, 0.0), (1.0, 1.0, 1.0), (0.3, 0.7, 0.5)]:
        for uid in small_slice["user_ids"]:
            env.reset(options={"user_id": uid})
            while True:
                action = np.zeros(env.action_space.shape, dtype=np.float32)
                action[:, 0], action[:, 1], action[:, 2] = policy
                obs, reward, term, trunc, info = env.step(action)
                assert info["budget_audit"]["budget_check"] == pytest.approx(0.0, abs=1e-6)
                assert info["combined_monthly_commitment"] <= info["monthly_surplus"] + 1e-4
                assert info["unallocated_surplus"] >= -1e-9
                if term or trunc:
                    break


# --------------------------------------------------------------------------- F-01 -----

def test_face_value_crediting_keeps_savings_and_mixed_identical(small_slice):
    """F-01 on the record: this identity is a property of the *env*, not of the policy."""
    env = _make_env(small_slice, small_slice["user_ids"],
                    GoalPilotConfig.archived().replace(
                        action_mode=ACTION_MODE_SHARE,
                        goal_credit_mode=GOAL_CREDIT_FACE_VALUE,
                    ))
    for uid in small_slice["user_ids"]:
        savings = _rollout(env, uid, (1.0, 0.0, 0.0))
        mixed = _rollout(env, uid, (0.5, 0.5, 0.0))
        assert mixed == pytest.approx(savings, rel=0, abs=1e-6), (
            "the savings/mixed degeneracy has changed; update the audit report"
        )


def test_growth_weighted_crediting_breaks_the_degeneracy(small_slice):
    """F-01 fix: once each channel is compounded at its own rate, the mix matters."""
    env = _make_env(small_slice, small_slice["user_ids"],
                    GoalPilotConfig.archived().replace(
                        action_mode=ACTION_MODE_SHARE,
                        goal_credit_mode=GOAL_CREDIT_GROWTH_WEIGHTED,
                        investment_return_assumption=0.10,
                        annual_savings_return=0.0,
                    ))
    capacity = small_slice["profiles"].set_index("user_id")["investment_capacity_ratio"]
    comparable, differs = 0, 0
    for uid in small_slice["user_ids"]:
        savings = _rollout(env, uid, (1.0, 0.0, 0.0))
        mixed = _rollout(env, uid, (0.5, 0.5, 0.0))
        if float(capacity.loc[uid]) <= 0.0:
            continue            # no investment capacity -> the mix cannot change anything
        comparable += 1
        if abs(mixed - savings) > 1e-6:
            differs += 1
    assert comparable > 0, "fixture has no investable user"
    assert differs == comparable, (
        f"growth_weighted crediting only differentiated {differs}/{comparable} "
        "investable users"
    )


def test_growth_weighted_never_overshoots_goal_targets(small_slice):
    env = _make_env(small_slice, small_slice["user_ids"],
                    GoalPilotConfig.archived().replace(
                        action_mode=ACTION_MODE_SHARE,
                        goal_credit_mode=GOAL_CREDIT_GROWTH_WEIGHTED,
                        investment_return_assumption=0.12,
                    ))
    for uid in small_slice["user_ids"]:
        env.reset(options={"user_id": uid})
        while True:
            action = np.ones(env.action_space.shape, dtype=np.float32)
            obs, reward, term, trunc, info = env.step(action)
            assert np.max(env.goal_balances - env.goal_targets) <= 1e-6
            if term or trunc:
                break


# ---------------------------------------------------------------- target basis F-06 -----

def test_inflated_target_basis_raises_goal_targets(small_slice):
    nominal = _make_env(small_slice, small_slice["user_ids"],
                        GoalPilotConfig.archived())
    inflated = _make_env(small_slice, small_slice["user_ids"],
                         GoalPilotConfig.archived().replace(
                             target_basis="inflated", annual_inflation=0.03))
    uid = small_slice["user_ids"][0]
    nominal.reset(options={"user_id": uid}); inflated.reset(options={"user_id": uid})
    assert np.all(inflated.goal_targets >= nominal.goal_targets - 1e-9)
    assert np.any(inflated.goal_targets > nominal.goal_targets + 1e-6)
