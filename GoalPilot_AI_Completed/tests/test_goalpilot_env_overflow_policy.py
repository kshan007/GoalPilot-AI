"""Investment-overflow policy regressions (Change 2).

`investment_overflow_policy` decides what happens to investment demand above the user's
capacity. The default is ``legacy``, which reproduces the historical behaviour and is
*mode dependent*: ``share`` returns the excess to the savings channel, ``mix`` leaves it
unallocated. ``retain_as_cash`` and ``redirect_to_savings`` are the two explicit opt-in modes.
"""
from __future__ import annotations

import numpy as np
import pytest

import goalpilot_env
from goalpilot_config import (
    INVESTMENT_OVERFLOW_LEGACY,
    INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS,
    INVESTMENT_OVERFLOW_RETAIN_AS_CASH,
    GoalPilotConfig,
)

INVEST_ONLY = (0.0, 1.0, 0.0)
MIXED = (0.5, 0.5, 0.0)
SAVINGS_ONLY = (1.0, 0.0, 0.0)

EXISTING_PRESETS = {
    "archived": GoalPilotConfig.archived,
    "corrected_accounting": GoalPilotConfig.corrected_accounting,
    "lp_parity": GoalPilotConfig.lp_parity,
    "recommended": GoalPilotConfig.recommended,
    "with_reallocation": GoalPilotConfig.with_reallocation,
    "with_action_mix": GoalPilotConfig.with_action_mix,
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
        a = np.zeros(env.action_space.shape, dtype=np.float32)
        a[:, 0], a[:, 1], a[:, 2] = s, i, loan
        _, _, term, trunc, info = env.step(a)
        months.append(info)
        if term or trunc:
            break
    return months


def _users(rl_data, limit=3):
    profiles = rl_data["profiles"]
    surplus = (profiles["monthly_income"].astype(float)
               - profiles["monthly_expenditure"].astype(float)
               - profiles["monthly_emi"].astype(float))
    mask = (surplus > 0.0) & (profiles["investment_capacity_ratio"].astype(float) > 0.0)
    users = profiles.loc[mask, "user_id"].astype(str).tolist()
    assert users, "expected suitable users"
    return users[:limit]


def _total(months, key):
    return sum(m["budget_audit"][key] for m in months)


# ----------------------------------------------------------- opt-in contract ---------------

def test_default_policy_is_legacy_in_every_existing_preset():
    for name, factory in EXISTING_PRESETS.items():
        assert getattr(factory(), "investment_overflow_policy") == INVESTMENT_OVERFLOW_LEGACY, name
    assert GoalPilotConfig().investment_overflow_policy == INVESTMENT_OVERFLOW_LEGACY


def test_overflow_preset_changes_exactly_one_field():
    for mode in (INVESTMENT_OVERFLOW_RETAIN_AS_CASH, INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS):
        cfg = GoalPilotConfig.with_investment_overflow(mode)
        assert cfg.investment_overflow_policy == mode
        base = GoalPilotConfig.recommended().to_dict()
        assert {k for k in base if base[k] != cfg.to_dict()[k]} == {
            "investment_overflow_policy"}


def test_an_invalid_policy_is_rejected():
    with pytest.raises(ValueError):
        GoalPilotConfig(investment_overflow_policy="bogus")


# --------------------------------------------------- legacy is reproduced exactly -----------

def test_legacy_share_formula_is_reproduced_by_the_helper(rl_data):
    """Pins the historical `share` arithmetic independently of the environment run."""
    users = _users(rl_data, limit=1)
    env = _env(rl_data, users, GoalPilotConfig.recommended())
    w_sav = np.array([0.0, 2.0, 0.0, 0.0, 0.0])
    base = np.array([10.0, 20.0, 30.0, 0.0, 0.0])
    overflow = 12.0
    got, redirected, retained = env._settle_investment_overflow(
        base.copy(), w_sav, overflow, 5, np.ones(5))
    expected = base + w_sav / w_sav.sum() * overflow
    np.testing.assert_allclose(got, expected, rtol=0.0, atol=0.0)
    assert redirected == overflow and retained == 0.0
    # equal split when there are no savings weights at all
    got2, _, _ = env._settle_investment_overflow(
        np.zeros(5), np.zeros(5), overflow, 5, np.ones(5))
    np.testing.assert_allclose(got2, np.full(5, overflow / 5.0), rtol=0.0, atol=0.0)


def test_legacy_mix_behaves_as_retain_as_cash(rl_data):
    """In `mix` the historical behaviour already is 'leave it unallocated'."""
    users = _users(rl_data)
    legacy = _env(rl_data, users, GoalPilotConfig.with_action_mix())
    retained = _env(rl_data, users, GoalPilotConfig.with_action_mix().replace(
        investment_overflow_policy=INVESTMENT_OVERFLOW_RETAIN_AS_CASH))
    for uid in users:
        for a, b in zip(_roll(legacy, uid, INVEST_ONLY), _roll(retained, uid, INVEST_ONLY)):
            for key in ("savings_contribution", "investment_contribution",
                        "unallocated_surplus", "overflow_retained_as_cash"):
                assert a["budget_audit"][key] == pytest.approx(b["budget_audit"][key],
                                                               abs=1e-9), (uid, key)


# ---------------------------------------------------------------- retain_as_cash -------------

def test_retain_as_cash_stops_the_share_mode_redirect(rl_data):
    users = _users(rl_data)
    legacy = _env(rl_data, users, GoalPilotConfig.recommended())
    retained = _env(rl_data, users, GoalPilotConfig.with_investment_overflow(
        INVESTMENT_OVERFLOW_RETAIN_AS_CASH))
    strictly_higher = 0
    for uid in users:
        a = _roll(legacy, uid, INVEST_ONLY)
        b = _roll(retained, uid, INVEST_ONLY)
        assert _total(b, "overflow_retained_as_cash") > 0.0, uid
        assert _total(b, "overflow_redirected_to_savings") == 0.0, uid
        # the excess is no longer credited as savings, so goals are funded less
        assert _total(b, "savings_contribution") < _total(a, "savings_contribution") - 1e-6, uid
        # The legacy redirect does NOT leave the investment channel untouched: pushing the
        # overflow into savings inflates the total the budget guard reconciles, so the guard
        # re-scales BOTH channels and investment shrinks with it. Removing the redirect can
        # therefore *increase* real investment - the historical claim that "no budget is lost"
        # is not quite right. Where capacity is small the guard never binds, so the two agree
        # exactly; either way the redirect must never *increase* investment.
        inv_legacy = _total(a, "investment_contribution")
        inv_retained = _total(b, "investment_contribution")
        assert inv_retained >= inv_legacy - 1e-6, uid
        if inv_retained > inv_legacy + 1e-6:
            strictly_higher += 1
    assert strictly_higher > 0, (
        "expected at least one user where the guard re-scaling mechanism is visible; "
        "if none exists the documented mechanism is wrong"
    )


# ------------------------------------------------------------ redirect_to_savings -----------

def test_redirect_to_savings_credits_the_overflow_as_savings(rl_data):
    users = _users(rl_data)
    retained = _env(rl_data, users, GoalPilotConfig.with_action_mix().replace(
        investment_overflow_policy=INVESTMENT_OVERFLOW_RETAIN_AS_CASH))
    redirected = _env(rl_data, users, GoalPilotConfig.with_action_mix().replace(
        investment_overflow_policy=INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS))
    for uid in users:
        a = _roll(retained, uid, INVEST_ONLY)
        b = _roll(redirected, uid, INVEST_ONLY)
        assert _total(b, "overflow_redirected_to_savings") > 0.0, uid
        assert _total(b, "overflow_retained_as_cash") == pytest.approx(0.0, abs=1e-6), uid
        # credited as SAVINGS, and the investment channel is not increased by it
        assert _total(b, "savings_contribution") > _total(a, "savings_contribution") + 1e-6, uid
        inv_retained = _total(a, "investment_contribution")
        inv_redirected = _total(b, "investment_contribution")
        assert inv_redirected <= inv_retained + 1e-6, uid
        # the small dip is the guard re-scaling both channels once the redirected savings
        # inflate the base it reconciles - bounded, not a channel substitution
        assert inv_redirected == pytest.approx(inv_retained, rel=5e-3), uid


def test_redirect_with_no_eligible_goal_retains_everything_as_cash(rl_data):
    """All goals already at target: nothing can absorb the overflow."""
    users = _users(rl_data, limit=1)
    env = _env(rl_data, users, GoalPilotConfig.with_action_mix().replace(
        investment_overflow_policy=INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS))
    uid = users[0]
    env.reset(options={"user_id": uid})
    # fully saturate every goal, so no goal has remaining need
    env.goal_balances = env.goal_targets.astype("float64").copy()
    action = np.zeros(env.action_space.shape, dtype=np.float32)
    action[:, 1] = 1.0
    _, _, _, _, info = env.step(action)
    ba = info["budget_audit"]
    assert ba["invest_overflow"] > 0.0
    assert ba["overflow_redirected_to_savings"] == pytest.approx(0.0, abs=1e-9)
    assert ba["overflow_retained_as_cash"] == pytest.approx(ba["invest_overflow"], rel=1e-9)

    # the helper agrees when need is explicitly zero
    got, redirected, retained = env._settle_investment_overflow(
        np.zeros(5), np.zeros(5), 100.0, 5, np.zeros(5))
    assert redirected == 0.0 and retained == 100.0


# ------------------------------------------- conservation, no double allocation -------------

@pytest.mark.parametrize("mode", [INVESTMENT_OVERFLOW_RETAIN_AS_CASH,
                                  INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS])
@pytest.mark.parametrize("policy", [SAVINGS_ONLY, INVEST_ONLY, MIXED])
def test_overflow_modes_preserve_the_budget_and_the_ledger(rl_data, mode, policy):
    users = _users(rl_data)
    env = _env(rl_data, users, GoalPilotConfig.recommended().replace(
        investment_overflow_policy=mode))
    for uid in users:
        for m in _roll(env, uid, policy):
            ba = m["budget_audit"]
            # no double allocation: the overflow is split exactly once
            assert (ba["overflow_redirected_to_savings"] + ba["overflow_retained_as_cash"]
                    ) == pytest.approx(ba["invest_overflow"], rel=1e-9, abs=1e-9)
            # the excess is never invested twice
            assert ba["invest_actual"] <= ba["invest_requested"] + 1e-9
            # budget conservation
            assert (ba["savings_contribution"] + ba["investment_contribution"]
                    + ba["unallocated_surplus"]) == pytest.approx(
                ba["discretionary_budget"], abs=1e-6)
            assert (ba["savings_contribution"] + ba["investment_contribution"]
                    ) <= ba["discretionary_budget"] + 1e-6
            # accounting invariants
            assert ba["net_worth_change"] == pytest.approx(
                ba["expected_net_worth_change"], abs=1e-4)
            ledger = m["ledger"]
            assert ledger["goal_balances_total"] <= (
                ledger["cash"] + ledger["portfolio"] + 1e-6)
            # affordability
            assert ba["interest_shortfall"] == pytest.approx(0.0, abs=1e-9)


def test_overflow_modes_are_deterministic(rl_data):
    users = _users(rl_data, limit=2)
    cfg = GoalPilotConfig.with_action_mix().replace(
        investment_overflow_policy=INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS)
    first = _roll(_env(rl_data, users, cfg), users[0], INVEST_ONLY)
    second = _roll(_env(rl_data, users, cfg), users[0], INVEST_ONLY)
    for a, b in zip(first, second):
        assert (a["budget_audit"]["overflow_redirected_to_savings"]
                == b["budget_audit"]["overflow_redirected_to_savings"])
        assert a["ledger"]["net_worth"] == pytest.approx(b["ledger"]["net_worth"], abs=0.0)


def test_zero_investment_controls_are_unaffected_by_any_mode(rl_data):
    """Policies requesting no investment can never overflow, so every mode agrees."""
    users = _users(rl_data)
    results = {}
    for mode in (INVESTMENT_OVERFLOW_LEGACY, INVESTMENT_OVERFLOW_RETAIN_AS_CASH,
                 INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS):
        env = _env(rl_data, users, GoalPilotConfig.recommended().replace(
            investment_overflow_policy=mode))
        results[mode] = {
            uid: _total(_roll(env, uid, SAVINGS_ONLY), "savings_contribution")
            for uid in users
        }
    reference = results[INVESTMENT_OVERFLOW_LEGACY]
    for mode, values in results.items():
        for uid, value in values.items():
            assert value == pytest.approx(reference[uid], rel=1e-12), (mode, uid)
        # no overflow anywhere
        env = _env(rl_data, users, GoalPilotConfig.recommended().replace(
            investment_overflow_policy=mode))
        for uid in users:
            assert _total(_roll(env, uid, SAVINGS_ONLY), "invest_overflow") == 0.0
