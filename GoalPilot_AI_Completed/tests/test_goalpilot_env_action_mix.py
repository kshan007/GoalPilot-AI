"""Regression tests for the opt-in `mix` action mapping (finding R-12).

Background
----------
In `share` mode the 2n savings/investment weights are normalised to shares and investment
demand above `invest_cap` is **pushed into the savings channel**, so `(0, 1, 0)` and
`(0.5, 0.5, 0)` produce identical allocations - the requested mix is unobservable. Measured in
`outputs/reward_design/v2/P1_STRATEGY_SPACE_DIAGNOSIS.md` (R-12) and re-confirmed in
`outputs/reward_design/v3/P1B_R12_AND_P4_FAIR_BASELINES.md` (achievement 0.6545 and idle
fraction 0.0295 for *both* actions).

`mix` mode is identical to `share` except for that one behaviour: excess investment demand is
left unallocated and reported in `budget_audit["unallocated_from_investment_cap"]`.

Three properties of the schema that these tests had to be written around, each established
empirically while writing them:

1. **The weights are normalised within the channel pair, so an absolute weight carries no
   information.** `(0, 0.25, 0)` is *not* "invest a quarter" - with no savings weight the mix is
   100% investment, so it invests the full available budget exactly like `(0, 1, 0)`. The
   meaningful investment control is the **mix ratio** `S_inv / (S_inv + S_sav)`, which spans
   [0, 1] and is honoured up to capacity. That is the explicit investment-fraction control;
   no extra action dimension is needed.
2. **`sum(goal_balances) <= cash + portfolio` is the valid memo bound, not
   `... - loan_balance`.** Goal earmarks can be loan-funded, so the memo partitions *gross*
   assets. Subtracting the liability is only valid for policies that never borrow.
3. **The investment-cap overflow is a different release channel from the per-goal cap.**
   `budget_audit["unallocated_from_investment_cap"]` is *not* picked up by the R-13
   reallocation, which only reallocates `released_by_goal_cap`. Consequence: `mix` stays
   non-degenerate even with the R-13 flag on, and the investment-cap overflow is still wasted
   when both flags are set. Pinned below as a known interaction.
"""
from __future__ import annotations

import numpy as np
import pytest

import goalpilot_env
from goalpilot_config import ACTION_MODE_MIX, GoalPilotConfig

NO_ACTION = (0.0, 0.0, 0.0)
SAVINGS_ONLY = (1.0, 0.0, 0.0)
INVEST_ONLY = (0.0, 1.0, 0.0)
MIXED = (0.5, 0.5, 0.0)
LOAN_ONLY = (0.0, 0.0, 1.0)
SAVINGS_AND_LOAN = (0.5, 0.0, 1.0)

EXISTING_PRESETS = {
    "archived": GoalPilotConfig.archived,
    "corrected_accounting": GoalPilotConfig.corrected_accounting,
    "lp_parity": GoalPilotConfig.lp_parity,
    "recommended": GoalPilotConfig.recommended,
    "with_reallocation": GoalPilotConfig.with_reallocation,
}


def _env(rl_data, user_ids, config):
    return goalpilot_env.GoalPilotEnv(
        profiles=rl_data["profiles"], goals=rl_data["goals"],
        market=rl_data["market"], user_ids=user_ids, config=config,
    )


def _roll(env, uid, policy, builder=None):
    env.reset(options={"user_id": uid})
    months = []
    while True:
        if builder is None:
            s, i, loan = policy
            action = np.zeros(env.action_space.shape, dtype=np.float32)
            action[:, 0], action[:, 1], action[:, 2] = s, i, loan
        else:
            action = builder(env)
        _, _, term, trunc, info = env.step(action)
        months.append(info)
        if term or trunc:
            break
    return months


def _usable(rl_data, limit=3, min_capacity=0.0):
    profiles = rl_data["profiles"]
    surplus = (profiles["monthly_income"].astype(float)
               - profiles["monthly_expenditure"].astype(float)
               - profiles["monthly_emi"].astype(float))
    mask = (surplus > 0.0) & (profiles["investment_capacity_ratio"].astype(float)
                              >= min_capacity)
    users = profiles.loc[mask, "user_id"].astype(str).tolist()
    assert users, "expected suitable users in the sample"
    return users[:limit]


# ------------------------------------------------------- opt-in / legacy parity ------------

def test_mix_mode_is_not_enabled_by_any_existing_preset():
    for name, factory in EXISTING_PRESETS.items():
        assert getattr(factory(), "action_mode") != ACTION_MODE_MIX, name


def test_only_the_dedicated_preset_selects_mix_and_changes_one_field():
    cfg = GoalPilotConfig.with_action_mix()
    assert cfg.action_mode == ACTION_MODE_MIX
    base = GoalPilotConfig.recommended().to_dict()
    derived = cfg.to_dict()
    assert {k for k in base if base[k] != derived[k]} == {"action_mode"}


def test_mix_matches_share_exactly_when_demand_is_within_capacity(rl_data):
    """The single behavioural difference must be invisible below the capacity limit.

    The action is built from each user's own capacity so the investment request is
    guaranteed affordable: with `w_inv = 0.5 * capacity` the realised investment share is
    `0.5c / (1 + 0.5c) < c`, i.e. strictly inside the limit.
    """
    users = _usable(rl_data, min_capacity=1e-9)

    def builder(env):
        c = float(env.profile_map[env.user_id]["investment_capacity_ratio"])
        n = len(env.user_goals)
        a = np.zeros(env.action_space.shape, dtype=np.float32)
        a[:n, 0] = 1.0
        a[:n, 1] = 0.5 * c
        return a

    share_env = _env(rl_data, users, GoalPilotConfig.recommended())
    mix_env = _env(rl_data, users, GoalPilotConfig.with_action_mix())
    for uid in users:
        for a, b in zip(_roll(share_env, uid, None, builder),
                        _roll(mix_env, uid, None, builder)):
            for key in ("savings_contribution", "investment_contribution",
                        "unallocated_surplus"):
                assert a["budget_audit"][key] == pytest.approx(
                    b["budget_audit"][key], abs=1e-9), (uid, key)
            assert b["budget_audit"]["unallocated_from_investment_cap"] == pytest.approx(
                0.0, abs=1e-9), uid


# -------------------------------------------------- non-degenerate investment behaviour -----

def test_mix_is_non_degenerate_when_demand_exceeds_capacity(rl_data):
    """`(0,1,0)` and `(0.5,0.5,0)` must now denote different policies."""
    users = _usable(rl_data, min_capacity=1e-9)
    env = _env(rl_data, users, GoalPilotConfig.with_action_mix())
    for uid in users:
        inv_only = _roll(env, uid, INVEST_ONLY)
        mixed = _roll(env, uid, MIXED)
        for a, b in zip(inv_only, mixed):
            assert a["budget_audit"]["unallocated_from_investment_cap"] > 0.0
            assert (a["budget_audit"]["savings_contribution"]
                    < b["budget_audit"]["savings_contribution"] - 1e-9)
            assert (a["budget_audit"]["unallocated_surplus"]
                    > b["budget_audit"]["unallocated_surplus"] + 1e-9)


def test_mix_honours_the_requested_investment_fraction(rl_data):
    """The mix ratio is the investment-fraction control, and it behaves monotonically.

    `(1-k, k, 0)` requests an investment share of exactly `k` of the available budget, honoured
    up to capacity: realised investment is `min(k*A, cap)`. Users are restricted to
    `capacity > 0.25` so that `k = 0.25` is unambiguously below the limit and `k = 0.5` above it.
    """
    users = _usable(rl_data, min_capacity=0.25)
    env = _env(rl_data, users, GoalPilotConfig.with_action_mix())
    for uid in users:
        quarter = _roll(env, uid, (0.75, 0.25, 0.0))
        half = _roll(env, uid, (0.5, 0.5, 0.0))
        q = sum(m["budget_audit"]["investment_contribution"] for m in quarter)
        h = sum(m["budget_audit"]["investment_contribution"] for m in half)
        assert q > 0.0, uid
        assert q < h, f"{uid}: stronger investment request invested no more ({q} vs {h})"
        # the quarter request is fully affordable, so nothing is left uninvested
        assert all(m["budget_audit"]["unallocated_from_investment_cap"] == pytest.approx(
            0.0, abs=1e-9) for m in quarter), uid


# ------------------------------------------------------------ bounds and no-op -------------

def test_mix_all_zero_action_is_a_true_no_op(rl_data):
    users = _usable(rl_data)
    env = _env(rl_data, users, GoalPilotConfig.with_action_mix())
    for uid in users:
        env.reset(options={"user_id": uid})
        start = float(np.sum(env.goal_balances))
        for m in _roll(env, uid, NO_ACTION):
            assert m["budget_audit"]["savings_contribution"] == 0.0
            assert m["budget_audit"]["investment_contribution"] == 0.0
        assert float(np.sum(env.goal_balances)) == pytest.approx(start, rel=1e-12)


def test_mix_extreme_actions_stay_in_bounds(rl_data):
    users = _usable(rl_data)
    env = _env(rl_data, users, GoalPilotConfig.with_action_mix())

    def oversized(env):
        a = np.zeros(env.action_space.shape, dtype=np.float32)
        a[:] = 5.0                          # above the Box upper bound
        return a

    for uid in users:
        for m in _roll(env, uid, None, oversized):
            ba = m["budget_audit"]
            assert ba["savings_contribution"] >= 0.0
            assert ba["investment_contribution"] >= 0.0
            assert ba["unallocated_surplus"] >= -1e-9
            assert (ba["savings_contribution"] + ba["investment_contribution"]
                    <= ba["discretionary_budget"] + 1e-6)


# ------------------------------------------------------ conservation and limits ------------

@pytest.mark.parametrize("policy", [SAVINGS_ONLY, INVEST_ONLY, MIXED, LOAN_ONLY,
                                    SAVINGS_AND_LOAN])
def test_mix_budget_conservation_limits_and_memo_bound(rl_data, policy):
    users = _usable(rl_data, min_capacity=1e-9)
    env = _env(rl_data, users, GoalPilotConfig.with_action_mix())
    for uid in users:
        capacity = float(env.profile_map[uid]["investment_capacity_ratio"])
        for m in _roll(env, uid, policy):
            ba = m["budget_audit"]
            # every rupee of the discretionary budget is allocated or reported as surplus
            assert (ba["savings_contribution"] + ba["investment_contribution"]
                    + ba["unallocated_surplus"]) == pytest.approx(
                ba["discretionary_budget"], abs=1e-6)
            assert ba["unallocated_from_investment_cap"] >= 0.0
            # investment capacity still binds
            ceiling = capacity * (ba["discretionary_budget"] + ba["env_loan_emi_paid"]
                                  + float(m["active_loan_emi"])) + 1e-6
            assert ba["investment_contribution"] <= ceiling
            # the memo account partitions GROSS assets (earmarks may be loan-funded)
            ledger = m["ledger"]
            assert ledger["goal_balances_total"] <= (
                ledger["cash"] + ledger["portfolio"] + 1e-6)


def test_mix_per_goal_limit_holds_when_the_credit_clamp_is_active(rl_data):
    """A goal is never credited beyond its target in the configuration that guarantees it.

    Over-funding via the monthly market gain is a pre-existing property of `market_weighted`
    (the gain is credited outside the per-goal cap) and is independent of the action mode; the
    credit clamp that removes it belongs to the R-13 package. This test therefore asserts the
    per-goal limit where it is guaranteed, rather than pretending it holds in `mix` alone.
    """
    users = _usable(rl_data, min_capacity=1e-9)
    cfg = GoalPilotConfig.with_action_mix().replace(reallocate_capped_budget=True)
    env = _env(rl_data, users, cfg)
    for uid in users:
        for m in _roll(env, uid, MIXED):
            assert np.all(env.goal_balances <= env.goal_targets + 1e-6), uid
            assert m["budget_audit"]["net_worth_change"] == pytest.approx(
                m["budget_audit"]["expected_net_worth_change"], abs=1e-4)


# ------------------------------------------------------- loan affordability ----------------

def test_mix_loan_affordability_is_respected(rl_data):
    users = _usable(rl_data, min_capacity=1e-9)
    env = _env(rl_data, users, GoalPilotConfig.with_action_mix())
    for uid in users:
        for m in _roll(env, uid, SAVINGS_AND_LOAN):
            ba = m["budget_audit"]
            assert m["new_loan_principal"] >= 0.0
            assert m["new_loan_principal"] <= env.config.max_new_loan + 1e-6
            assert ba["interest_shortfall"] == pytest.approx(0.0, abs=1e-9)
            # contributions plus the loan being serviced this month stay inside surplus
            assert (ba["savings_contribution"] + ba["investment_contribution"]
                    + ba["env_loan_emi_paid"]) <= ba["surplus"] + 1e-6


# ------------------------------------ released budget and the R-13 interaction -------------

def test_mix_released_budget_redistribution_still_works(rl_data):
    users = _usable(rl_data, min_capacity=1e-9)

    def idle_and_moved(config):
        env = _env(rl_data, users, config)
        idle = moved = budget = 0.0
        for uid in users:
            for m in _roll(env, uid, MIXED):
                ba = m["budget_audit"]
                idle += ba["unallocated_surplus"]
                moved += ba["reallocated_from_cap"]
                budget += ba["discretionary_budget"]
        return idle / max(budget, 1e-9), moved

    idle_off, moved_off = idle_and_moved(GoalPilotConfig.with_action_mix())
    idle_on, moved_on = idle_and_moved(
        GoalPilotConfig.with_action_mix().replace(reallocate_capped_budget=True))
    assert moved_off == 0.0
    assert moved_on > 0.0
    assert idle_on < idle_off


def test_mix_stays_non_degenerate_with_reallocation_on(rl_data):
    """Known interaction, pinned: the two release channels are independent.

    R-13 reallocates `released_by_goal_cap` only. The investment-cap overflow is a *different*
    channel and is not reallocated, so `mix` stays non-degenerate even with the R-13 flag on -
    and that overflow is still discarded when both flags are set. Pinned so the interaction
    cannot change silently; whether R-13 *should* also reallocate it is an open design question,
    recorded in `outputs/reward_design/v4/R12_ACTION_SPACE_DESIGN.md`.
    """
    users = _usable(rl_data, min_capacity=1e-9)
    cfg = GoalPilotConfig.with_action_mix().replace(reallocate_capped_budget=True)
    env = _env(rl_data, users, cfg)
    for uid in users:
        a = sum(m["budget_audit"]["savings_contribution"] for m in _roll(env, uid, INVEST_ONLY))
        b = sum(m["budget_audit"]["savings_contribution"] for m in _roll(env, uid, MIXED))
        assert a < b - 1e-9, uid
        assert all(m["budget_audit"]["unallocated_from_investment_cap"] >= 0.0
                   for m in _roll(env, uid, INVEST_ONLY))


# -------------------------------------------------------------------- determinism ----------

def test_mix_is_deterministic(rl_data):
    users = _usable(rl_data, limit=2, min_capacity=1e-9)
    cfg = GoalPilotConfig.with_action_mix()
    first = _roll(_env(rl_data, users, cfg), users[0], MIXED)
    second = _roll(_env(rl_data, users, cfg), users[0], MIXED)
    assert len(first) == len(second)
    for a, b in zip(first, second):
        assert (sum(a["reward_components"].values())
                == sum(b["reward_components"].values()))
        assert a["ledger"]["net_worth"] == pytest.approx(b["ledger"]["net_worth"], abs=0.0)
        assert (a["budget_audit"]["unallocated_from_investment_cap"]
                == b["budget_audit"]["unallocated_from_investment_cap"])
