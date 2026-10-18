"""Regression tests for the opt-in R-13 fix: reallocating cap-released budget.

Finding R-13 (measured in `outputs/reward_design/v2/P1_STRATEGY_SPACE_DIAGNOSIS.md`): the
per-goal cap releases budget that is then **discarded**, destroying 26-29% of the monthly budget
for the best simple policies and 36-51% for the trained RL policies. The fix redistributes that
money to goals that still have remaining need.

The behaviour is gated behind ``GoalPilotConfig.reallocate_capped_budget``, which is **False in
every existing preset**, so archived reproduction, every published result and every existing
checkpoint are unaffected. These tests pin both halves of that contract.
"""
from __future__ import annotations

import numpy as np
import pytest

import goalpilot_env
from goalpilot_config import GoalPilotConfig

NO_ACTION = (0.0, 0.0, 0.0)
SAVINGS_ONLY = (1.0, 0.0, 0.0)
INVEST_ONLY = (0.0, 1.0, 0.0)
MIXED = (0.5, 0.5, 0.0)

PRESETS = {
    "archived": GoalPilotConfig.archived,
    "corrected_accounting": GoalPilotConfig.corrected_accounting,
    "lp_parity": GoalPilotConfig.lp_parity,
    "recommended": GoalPilotConfig.recommended,
}


def _env(rl_data, user_ids, config):
    return goalpilot_env.GoalPilotEnv(
        profiles=rl_data["profiles"], goals=rl_data["goals"],
        market=rl_data["market"], user_ids=user_ids, config=config,
    )


def _roll(env, uid, policy):
    s, i, loan = policy
    env.reset(options={"user_id": uid})
    months = []
    while True:
        action = np.zeros(env.action_space.shape, dtype=np.float32)
        action[:, 0], action[:, 1], action[:, 2] = s, i, loan
        _, _, term, trunc, info = env.step(action)
        months.append(info)
        if term or trunc:
            break
    return months


def _feasible_users(rl_data, limit=3):
    profiles = rl_data["profiles"]
    surplus = (profiles["monthly_income"].astype(float)
               - profiles["monthly_expenditure"].astype(float)
               - profiles["monthly_emi"].astype(float))
    users = profiles.loc[surplus > 0.0, "user_id"].astype(str).tolist()
    assert users, "expected feasible users in the sample"
    return users[:limit]


# ---------------------------------------------------------------- the opt-in contract -----

def test_reallocation_is_off_in_every_existing_preset():
    """No published preset may silently acquire the new behaviour."""
    for name, factory in PRESETS.items():
        assert getattr(factory(), "reallocate_capped_budget") is False, name


def test_only_the_dedicated_preset_enables_reallocation():
    cfg = GoalPilotConfig.with_reallocation()
    assert cfg.reallocate_capped_budget is True
    # ...and it is otherwise identical to `recommended()`
    base = GoalPilotConfig.recommended().to_dict()
    derived = cfg.to_dict()
    differing = {k for k in base if base[k] != derived[k]}
    assert differing == {"reallocate_capped_budget"}


# ------------------------------------------------------------------- the fix works --------

@pytest.mark.parametrize("policy", [INVEST_ONLY, MIXED, SAVINGS_ONLY])
def test_reallocation_reduces_discarded_budget(rl_data, policy):
    """The released budget must shrink, and something must actually be reallocated."""
    users = _feasible_users(rl_data)

    def mean_idle(config):
        env = _env(rl_data, users, config)
        idle, released, moved, budget = 0.0, 0.0, 0.0, 0.0
        for uid in users:
            for m in _roll(env, uid, policy):
                ba = m["budget_audit"]
                idle += ba["unallocated_surplus"]
                budget += ba["discretionary_budget"]
                released += ba["released_by_goal_cap"]
                moved += ba["reallocated_from_cap"]
        return idle / max(budget, 1e-9), released, moved

    idle_off, released_off, moved_off = mean_idle(GoalPilotConfig.recommended())
    idle_on, released_on, moved_on = mean_idle(GoalPilotConfig.with_reallocation())

    assert moved_off == 0.0, "the flag is off, nothing may be reallocated"
    assert moved_on > 0.0, "the fix reallocated nothing - it is not working"
    # `released` is NOT invariant: reallocating money funds goals sooner, so they saturate
    # sooner and the cap subsequently releases *more*. That trajectory feedback is expected;
    # what must hold is that the released money is now used rather than discarded.
    assert moved_on <= released_on + 1e-6
    assert idle_on < idle_off - 1e-9, (
        f"discarded budget did not fall: {idle_off:.6f} -> {idle_on:.6f}"
    )


@pytest.mark.parametrize("policy", [INVEST_ONLY, MIXED])
def test_reallocation_does_not_reduce_goal_funding(rl_data, policy):
    """Handing away discarded money must not make any goal worse off."""
    users = _feasible_users(rl_data)

    def achievement(config):
        env = _env(rl_data, users, config)
        out = []
        for uid in users:
            months = _roll(env, uid, policy)
            target = env.goal_targets.astype(float)
            funded = env.goal_balances.astype(float)
            out.append(float(np.sum(funded) / max(float(np.sum(target)), 1e-9)))
        return float(np.mean(out))

    off = achievement(GoalPilotConfig.recommended())
    on = achievement(GoalPilotConfig.with_reallocation())
    assert on >= off - 1e-9, f"reallocation made funding worse: {off:.6f} -> {on:.6f}"


# ------------------------------------------------------- invariants must still hold --------

@pytest.mark.parametrize("policy", [NO_ACTION, SAVINGS_ONLY, INVEST_ONLY, MIXED])
def test_reallocation_preserves_every_accounting_invariant(rl_data, policy):
    users = _feasible_users(rl_data)
    env = _env(rl_data, users, GoalPilotConfig.with_reallocation())
    for uid in users:
        for m in _roll(env, uid, policy):
            ba = m["budget_audit"]
            # budget identity: nothing is created and nothing is dropped
            assert (ba["savings_contribution"] + ba["investment_contribution"]
                    + ba["unallocated_surplus"]) == pytest.approx(
                ba["discretionary_budget"], abs=1e-6)
            # never allocate more than was available
            assert (ba["savings_contribution"] + ba["investment_contribution"]
                    ) <= ba["discretionary_budget"] + 1e-6
            # never fund a goal beyond its target
            assert np.all(env.goal_balances <= env.goal_targets + 1e-6)
            # the memo account stays inside real assets
            ledger = m["ledger"]
            assert ledger["goal_balances_total"] <= (
                ledger["cash"] + ledger["portfolio"] - ledger["loan_balance"] + 1e-6)
            # the ledger identity still holds
            assert ba["net_worth_change"] == pytest.approx(
                ba["expected_net_worth_change"], abs=1e-4)
            assert ba["reallocated_from_cap"] <= ba["released_by_goal_cap"] + 1e-6
            assert ba["reallocated_from_cap"] >= 0.0
