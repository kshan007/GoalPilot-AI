"""Action-semantics and goal-credit validation (Phase C) plus findings R-02 and R-03.

Phase C of the validation brief asks for three things, all pinned here:

* **C1** — ``share`` mode must allocate the whole available budget, must be insensitive to
  the *magnitude* of a constant weight (no artificial under-allocation penalty), and must
  preserve an all-zero action as a genuine no-op.
* **C2** — ``_credit_goals`` must use the correct time remaining, and the environment must
  never count a *projected* future return as realised goal funding.
* **C3** — the archived savings-only / mixed-allocation degeneracy is preserved under
  ``face_value``, while the recommended configuration must break it for a **real** reason.

Findings pinned here:

* **R-02** — the emergency reserve is now restricted cash on the balance sheet in ledger
  mode, so it is counted exactly once and appears in net worth.
* **R-03** — ``growth_weighted`` books a projection (documented, still selectable for
  LP-parity work); ``market_weighted`` books realised revaluation only.
"""
from __future__ import annotations

import numpy as np
import pytest

import goalpilot_env
from goalpilot_config import (
    ACTION_MODE_SHARE,
    GOAL_CREDIT_FACE_VALUE,
    GOAL_CREDIT_GROWTH_WEIGHTED,
    GOAL_CREDIT_MARKET_WEIGHTED,
    GoalPilotConfig,
)

NO_ACTION = (0.0, 0.0, 0.0)
SAVINGS_ONLY = (1.0, 0.0, 0.0)
INVEST_ONLY = (0.0, 1.0, 0.0)
MIXED = (0.5, 0.5, 0.0)
SAVINGS_AND_LOAN = (0.5, 0.0, 1.0)

SHARE_LP = GoalPilotConfig.lp_parity().replace(action_mode=ACTION_MODE_SHARE)


def _env(rl_data, user_ids, config):
    return goalpilot_env.GoalPilotEnv(
        profiles=rl_data["profiles"], goals=rl_data["goals"],
        market=rl_data["market"], user_ids=user_ids, config=config,
    )


def _roll(env, uid, policy, weights=None):
    """Roll one episode; ``weights`` overrides the per-slot savings/investment weights."""
    s, i, loan = policy
    env.reset(options={"user_id": uid})
    months = []
    while True:
        action = np.zeros(env.action_space.shape, dtype=np.float32)
        action[:, 0], action[:, 1], action[:, 2] = s, i, loan
        if weights is not None:
            action[:, 0] = weights
        _, _, term, trunc, info = env.step(action)
        months.append(info)
        if term or trunc:
            break
    return months


# ------------------------------------------------------------------ C1 --------

@pytest.mark.parametrize("weight", [0.25, 0.50, 0.75, 1.00])
def test_share_mode_constant_weights_are_equivalent(rl_data, weight):
    """A constant savings weight must always commit the whole budget in share mode.

    This is the F-02 fix: in ``magnitude`` mode 0.25 captured only ~94 % of the budget,
    whereas ``share`` normalises, so 0.25 behaves exactly like 1.00.
    """
    users = ["USER_00001", "USER_00003"]
    env = _env(rl_data, users, SHARE_LP)
    reference = {}
    for uid in users:
        months = _roll(env, uid, SAVINGS_ONLY, weights=weight)
        reference[uid] = float(np.sum(months[-1]["goal_balances"]))
        # The discretionary budget is either allocated or reported as surplus - it is never
        # silently dropped. Surplus only appears once a per-goal cap releases money (R-08).
        for m in months:
            ba = m["budget_audit"]
            assert (
                ba["savings_contribution"] + ba["investment_contribution"]
                + ba["unallocated_surplus"]
            ) == pytest.approx(ba["discretionary_budget"], abs=1e-6), ba

    env_baseline = _env(rl_data, users, SHARE_LP)
    for uid in users:
        months = _roll(env_baseline, uid, SAVINGS_ONLY, weights=1.00)
        assert float(np.sum(months[-1]["goal_balances"])) == pytest.approx(
            reference[uid], rel=1e-12
        )


def test_share_mode_zero_action_is_a_true_no_op(rl_data):
    """The all-zero action must not be normalised into a full-budget allocation."""
    users = ["USER_00001", "USER_00003"]
    env = _env(rl_data, users, SHARE_LP)
    for uid in users:
        _, info0 = env.reset(options={"user_id": uid})
        start = float(np.sum(info0.get("goal_balances", env.goal_balances)))
        months = _roll(env, uid, NO_ACTION)
        for m in months:
            assert m["budget_audit"]["savings_contribution"] == pytest.approx(0.0, abs=1e-12)
            assert m["budget_audit"]["investment_contribution"] == pytest.approx(0.0, abs=1e-12)
        assert float(np.sum(env.goal_balances)) == pytest.approx(start, rel=1e-12)


# ------------------------------------------------------------------ C2 --------

def test_credit_horizon_uses_remaining_months(rl_data):
    """``months_left = deadline - month_index``, inclusive of the current month."""
    env = _env(rl_data, ["USER_00001"],
               GoalPilotConfig.lp_parity().replace(
                   goal_credit_mode=GOAL_CREDIT_GROWTH_WEIGHTED))
    env.reset(options={"user_id": "USER_00001"})
    n = len(env.user_goals)
    ones = np.ones(n, dtype="float64")
    rate = 1.0 + env.config.investment_return_assumption

    for month_index in (0, 1, 11, 12, 60, int(env.goal_deadlines.max())):
        env.month_index = month_index
        cred_sav, cred_inv = env._credit_goals(ones, ones, n)
        expected = rate ** (np.maximum(0, env.goal_deadlines - month_index) / 12.0)
        np.testing.assert_allclose(cred_inv, expected, rtol=1e-12)
        # annual_savings_return is 0.0, so savings are credited at face value
        np.testing.assert_allclose(cred_sav, np.ones(n), rtol=1e-12)

    # a zero-month horizon must not grow at all
    env.month_index = int(env.goal_deadlines.max())
    _, cred_inv = env._credit_goals(ones, ones, n)
    assert float(cred_inv.min()) == pytest.approx(1.0, rel=1e-12)


def test_growth_weighted_books_a_projection_while_market_weighted_does_not(rl_data):
    """R-03 in one place: the old mode multiplies a rupee; the new mode does not."""
    n_users = ["USER_00001"]
    ones = np.ones(1, dtype="float64")

    growth = _env(rl_data, n_users,
                  GoalPilotConfig.lp_parity().replace(
                      goal_credit_mode=GOAL_CREDIT_GROWTH_WEIGHTED))
    growth.reset(options={"user_id": "USER_00001"})
    growth.month_index = 0
    n = len(growth.user_goals)
    ones = np.ones(n, dtype="float64")
    _, cred_inv_growth = growth._credit_goals(ones, ones, n)
    np.testing.assert_allclose(
        cred_inv_growth,
        (1.0 + growth.config.investment_return_assumption) ** (growth.goal_deadlines / 12.0),
        rtol=1e-12,
    )
    assert cred_inv_growth.max() > 1.5, (
        "a 10-year-plus horizon should be credited well above its face value"
    )

    market = _env(rl_data, n_users, GoalPilotConfig.recommended())
    market.reset(options={"user_id": "USER_00001"})
    market.month_index = 0
    _, cred_inv_market = market._credit_goals(ones, ones, n)
    np.testing.assert_allclose(cred_inv_market, np.ones(n), rtol=1e-12,
                              err_msg="market_weighted must never project growth")


def test_market_weighted_book_never_exceeds_real_assets(rl_data):
    """No projected return is booked: goal funding stays inside real assets (R-03)."""
    users = ["USER_00001", "USER_00005"]
    env = _env(rl_data, users, GoalPilotConfig.recommended())
    for uid in users:
        for policy in (SAVINGS_ONLY, MIXED, INVEST_ONLY, SAVINGS_AND_LOAN):
            for m in _roll(env, uid, policy):
                ledger = m["ledger"]
                assert ledger["goal_balances_total"] <= (
                    ledger["cash"] + ledger["portfolio"] - ledger["loan_balance"]
                    + 1e-6
                ), f"{uid}/{policy}/month {m['budget_audit']['month']}"


def test_zero_investment_capacity_blocks_investment(rl_data):
    """A user with no investment capacity cannot invest, under any credit mode."""
    profiles = rl_data["profiles"].copy()
    profiles["investment_capacity_ratio"] = 0.0
    env = goalpilot_env.GoalPilotEnv(
        profiles=profiles, goals=rl_data["goals"], market=rl_data["market"],
        user_ids=["USER_00001"], config=GoalPilotConfig.recommended(),
    )
    for m in _roll(env, "USER_00001", INVEST_ONLY):
        assert m["budget_audit"]["investment_contribution"] == pytest.approx(0.0, abs=1e-9)
        # the budget is not lost: it stays liquid
        assert m["budget_audit"]["savings_contribution"] >= 0.0
    # nothing was ever converted into the portfolio. (`total_investment_gain` is not zero:
    # the household's pre-existing portfolio keeps earning regardless of new capacity.)
    assert env.cumulative_investment_contributions == pytest.approx(0.0, abs=1e-9)


# ------------------------------------------------------------------ C3 --------

def test_face_value_preserves_the_archived_degeneracy(rl_data):
    """The archived savings-only == mixed identity must survive for reproduction."""
    users = ["USER_00001", "USER_00003", "USER_00004"]
    env = _env(rl_data, users, GoalPilotConfig.archived())
    for uid in users:
        savings = sum(np.sum(m["goal_balances"]) for m in _roll(env, uid, SAVINGS_ONLY))
        mixed = sum(np.sum(m["goal_balances"]) for m in _roll(env, uid, MIXED))
        # cumulative funding is identical by construction under face-value crediting
        assert savings == pytest.approx(mixed, rel=1e-12)


def test_market_weighted_breaks_the_degeneracy_for_a_real_reason(rl_data):
    """Under the recommended config the mix matters, and only via realised returns."""
    users = [f"USER_{i:05d}" for i in range(1, 7)]
    env = _env(rl_data, users, GoalPilotConfig.recommended())
    compared = 0
    for uid in users:
        capacity = float(env.profile_map[uid]["investment_capacity_ratio"])
        if capacity <= 0.0:
            continue
        env.reset(options={"user_id": uid})
        savings_final = float(np.sum(_roll(env, uid, SAVINGS_ONLY)[-1]["goal_balances"]))
        env.reset(options={"user_id": uid})
        mixed_final = float(np.sum(_roll(env, uid, MIXED)[-1]["goal_balances"]))
        compared += 1
        assert mixed_final != pytest.approx(savings_final, rel=1e-9), (
            f"{uid}: mixed and savings-only produced identical funding under market_weighted"
        )
    assert compared > 0, "no user in the slice had positive investment capacity"


# ------------------------------------------------------------------ R-02 -------

def test_reserve_is_on_the_balance_sheet_in_ledger_modes(rl_data):
    """The emergency reserve is restricted cash, counted exactly once (finding R-02)."""
    users = ["USER_00001", "USER_00002"]
    env = _env(rl_data, users, GoalPilotConfig.lp_parity())
    for uid in users:
        _, info = env.reset(options={"user_id": uid})
        profile = env.profile_map[uid]
        # the 6-month cap does not bind for these users, so the whole initial balance is held
        assert info["restricted_cash"] == pytest.approx(info["emergency_reserve"])
        assert info["restricted_cash"] > 0.0
        assert env.cash >= info["restricted_cash"] - 1e-9, "cash must include the reserve"
        assert info["initial_net_worth"] == pytest.approx(
            float(profile["initial_savings"]) + float(profile["initial_investment"]),
            rel=1e-12, abs=1e-6,
        )


def test_reserve_is_absent_when_emergency_months_is_zero(rl_data):
    """Archived and corrected-accounting behaviour carries no reserve (emergency_months = 0)."""
    users = ["USER_00001"]
    for cfg in (GoalPilotConfig.archived(), GoalPilotConfig.corrected_accounting(),
                GoalPilotConfig.lp_parity().replace(emergency_months=0.0)):
        env = _env(rl_data, users, cfg)
        _, info = env.reset(options={"user_id": "USER_00001"})
        assert info["restricted_cash"] == 0.0

    # In ledger mode the balance sheet is the household's full position.
    for cfg in (GoalPilotConfig.corrected_accounting(),
                GoalPilotConfig.lp_parity().replace(emergency_months=0.0)):
        env = _env(rl_data, users, cfg)
        _, info = env.reset(options={"user_id": "USER_00001"})
        profile = env.profile_map["USER_00001"]
        assert info["initial_net_worth"] == pytest.approx(
            float(profile["initial_savings"]) + float(profile["initial_investment"]),
            rel=1e-12, abs=1e-6,
        )


def test_earmarking_neither_creates_nor_destroys_cash(rl_data):
    """B2: the pre-existing earmark stays inside cash; goal_balances is only a label.

    The ledger previously subtracted the earmark from cash at reset while the memo doctrine
    forbade adding `goal_balances` back, so net worth understated the household's position
    by the earmark (finding R-11). Ledger mode now keeps the full balance in cash.
    """
    env = _env(rl_data, ["USER_00001"], GoalPilotConfig.lp_parity())
    _, info = env.reset(options={"user_id": "USER_00001"})
    profile = env.profile_map["USER_00001"]

    # restricted_cash is a disclosure *inside* cash, never added to it
    assert env.cash == pytest.approx(
        float(profile["initial_savings"]), rel=1e-12, abs=1e-6
    )
    assert env.cash >= env.restricted_cash - 1e-9
    assert float(np.sum(env.goal_balances)) <= env.cash + env.portfolio + 1e-6
    assert info["initial_net_worth"] == pytest.approx(
        float(profile["initial_savings"]) + float(profile["initial_investment"]),
        rel=1e-12, abs=1e-6,
    )


# ------------------------------------------------------------------ F ----------

@pytest.mark.parametrize("preset", ["archived", "corrected_accounting", "lp_parity",
                                    "recommended"])
def test_observations_and_rewards_are_finite_for_every_preset(rl_data, preset):
    """Phase F: finite observations and finite rewards across all four presets."""
    cfg = getattr(GoalPilotConfig, preset)()
    env = _env(rl_data, ["USER_00001", "USER_00005"], cfg)
    for uid in ["USER_00001", "USER_00005"]:
        for policy in (NO_ACTION, SAVINGS_ONLY, MIXED, SAVINGS_AND_LOAN):
            env.reset(options={"user_id": uid})
            while True:
                action = np.zeros(env.action_space.shape, dtype=np.float32)
                action[:, 0], action[:, 1], action[:, 2] = policy
                obs, reward, term, trunc, info = env.step(action)
                assert np.isfinite(obs).all()
                assert np.isfinite(reward)
                assert np.isfinite(info["net_worth"])
                assert not info["budget_audit"]["cash_floor_active"]
                if term or trunc:
                    break


# ------------------------------------------------- Phase 1: zero-surplus users --------------

def test_zero_surplus_users_cannot_fund_goals_under_any_action(rl_data):
    """The 0.0000 achievement of the low-risk cohort is environmental, not a policy failure.

    Phase 1 diagnosis (`audit_tools/40_low_risk_diagnosis.py`) established that six of the
    twenty held-out users have `monthly_income - monthly_expenditure - monthly_emi <= 0`, so the
    environment grants them a discretionary budget of exactly zero. Every strategy - including
    the deterministic LP plan and a maximally aggressive action - then funds nothing, which is
    why all ten policies scored an identical 0.0000 achievement and an identical net worth.

    This test pins that as **intentional** behaviour: it is not a learning failure and not an
    implementation defect. It guards against a future change silently altering it and making the
    cohort look like a policy difference.
    """
    profiles = rl_data["profiles"]
    surplus = (profiles["monthly_income"].astype(float)
               - profiles["monthly_expenditure"].astype(float)
               - profiles["monthly_emi"].astype(float))
    zero_users = profiles.loc[surplus <= 0.0, "user_id"].astype(str).tolist()
    assert zero_users, "expected at least one zero-surplus user in the synthetic population"

    env = _env(rl_data, zero_users, GoalPilotConfig.recommended())
    for uid in zero_users:
        for policy in (NO_ACTION, SAVINGS_ONLY, INVEST_ONLY, MIXED, (0.0, 0.0, 1.0),
                       SAVINGS_AND_LOAN):
            env.reset(options={"user_id": uid})
            start = float(np.sum(env.goal_balances))
            for m in _roll(env, uid, policy):
                ba = m["budget_audit"]
                assert ba["surplus"] == pytest.approx(0.0, abs=1e-9)
                assert ba["discretionary_budget"] == pytest.approx(0.0, abs=1e-9)
                assert ba["savings_contribution"] == pytest.approx(0.0, abs=1e-9)
                assert ba["investment_contribution"] == pytest.approx(0.0, abs=1e-9)
                assert m["new_loan_principal"] == pytest.approx(0.0, abs=1e-9)
            # goal funding is unchanged from reset, whatever the policy asked for
            assert float(np.sum(env.goal_balances)) == pytest.approx(start, rel=1e-12)


# ------------------------------------- P1b: known R-12 capacity degeneracy (pinned) ---------

def _feasible_with_capacity(rl_data, limit: int = 4) -> list[str]:
    profiles = rl_data["profiles"]
    surplus = (profiles["monthly_income"].astype(float)
               - profiles["monthly_expenditure"].astype(float)
               - profiles["monthly_emi"].astype(float))
    mask = (surplus > 0.0) & (profiles["investment_capacity_ratio"].astype(float) > 0.0)
    users = profiles.loc[mask, "user_id"].astype(str).tolist()
    assert users, "expected at least one user with surplus and investment capacity"
    return users[:limit]


def test_investment_capacity_overflow_makes_mixed_equivalent_to_investment_only(rl_data):
    """Known property, pinned deliberately (finding R-12).

    Investment is capped at ``available x investment_capacity_ratio`` and the overflow returns
    to savings, so **any** request at or above that capacity yields the same allocation:
    ``(0, 1, 0)`` and ``(0.5, 0.5, 0)`` denote one policy whenever the cap binds.

    This is a property of the environment, not a defect in the test, and it is why no
    "the savings/investment mix matters" claim can be made from this environment. It is pinned
    so that a future change to the overflow rule cannot *silently* invalidate the published
    strategy comparisons - it will fail here first.

    Measured in `outputs/reward_design/v2/P1_STRATEGY_SPACE_DIAGNOSIS.md` (finding R-12) and
    re-confirmed after the R-13 fix, where the two actions remain identical at achievement
    0.6545 with idle fraction 0.0295.
    """
    users = _feasible_with_capacity(rl_data)
    env = _env(rl_data, users, GoalPilotConfig.recommended())
    for uid in users:
        invest_only = _roll(env, uid, INVEST_ONLY)
        mixed = _roll(env, uid, MIXED)
        assert len(invest_only) == len(mixed)
        for a, b in zip(invest_only, mixed):
            for key in ("savings_contribution", "investment_contribution",
                        "investment_contribution"):
                assert a["budget_audit"][key] == pytest.approx(
                    b["budget_audit"][key], abs=1e-9), (uid, key)
            assert a["ledger"]["net_worth"] == pytest.approx(
                b["ledger"]["net_worth"], abs=1e-6), uid
        assert (sum(m["budget_audit"]["savings_contribution"]
                    + m["budget_audit"]["investment_contribution"]
                    for m in invest_only)
                == pytest.approx(
                    sum(m["budget_audit"]["savings_contribution"]
                        + m["budget_audit"]["investment_contribution"]
                        for m in mixed), rel=1e-12)), uid


def test_investment_capacity_ratio_is_actually_respected(rl_data):
    """Guards the other side of R-12: capacity must still bind, or the pin above is vacuous."""
    users = _feasible_with_capacity(rl_data)
    env = _env(rl_data, users, GoalPilotConfig.recommended())
    for uid in users:
        capacity = float(env.profile_map[uid]["investment_capacity_ratio"])
        for m in _roll(env, uid, INVEST_ONLY):
            ba = m["budget_audit"]
            # available budget for this month = discretionary + the EMIs reserved from it
            ceiling = capacity * (ba["discretionary_budget"] + ba["env_loan_emi_paid"]
                                  + float(m["active_loan_emi"])) + 1e-6
            assert ba["investment_contribution"] <= ceiling
