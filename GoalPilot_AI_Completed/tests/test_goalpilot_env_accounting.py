"""Ledger / double-counting regressions for GoalPilotEnv (audit findings F-04, F-05).

The archived environment made three accounting errors:

* savings contributions accumulated in ``cash`` while ``goal_balances`` also held them
  (F-04) — so ``cash + goal_balances`` inflated net worth;
* investment contributions were added to ``portfolio`` *and* to ``goal_balances`` (F-04);
* loan proceeds created a goal balance but never reached an account, and EMI payments
  never left one (F-05).

These tests pin the corrected behaviour.
"""
from __future__ import annotations

import numpy as np
import pytest

import goalpilot_env
from goalpilot_config import GoalPilotConfig, ACCOUNTING_MODE_LEDGER, ACCOUNTING_MODE_LEGACY

POLICIES = {
    "No action": (0.0, 0.0, 0.0),
    "Savings only": (1.0, 0.0, 0.0),
    "Investments only": (0.0, 1.0, 0.0),
    "Mixed allocation": (0.5, 0.5, 0.0),
    "Loan request only": (0.0, 0.0, 1.0),
    "Savings + loan": (0.5, 0.0, 1.0),
}


def _make_env(rl_data, user_ids, config):
    return goalpilot_env.GoalPilotEnv(
        profiles=rl_data["profiles"], goals=rl_data["goals"],
        market=rl_data["market"], user_ids=user_ids, config=config,
    )


def _rollout(env, user_id, policy, collect=True):
    s, i, loan = policy
    env.reset(options={"user_id": user_id})
    months = []
    while True:
        action = np.zeros(env.action_space.shape, dtype=np.float32)
        action[:, 0] = s
        action[:, 1] = i
        action[:, 2] = loan
        obs, reward, term, trunc, info = env.step(action)
        if collect:
            months.append(info["budget_audit"])
        if term or trunc:
            break
    return months


# --------------------------------------------------------------------------- F-04 -----

def test_monthly_budget_audit_balances_to_zero(small_slice):
    """Every month: savings + investments + unallocated == discretionary budget."""
    for mode in (ACCOUNTING_MODE_LEDGER, ACCOUNTING_MODE_LEGACY):
        env = _make_env(small_slice, small_slice["user_ids"],
                        GoalPilotConfig.archived().replace(accounting_mode=mode))
        for policy_name, policy in POLICIES.items():
            for uid in small_slice["user_ids"]:
                for audit in _rollout(env, uid, policy):
                    assert audit["budget_check"] == pytest.approx(0.0, abs=1e-6), (
                        f"budget identity broken: {mode}/{policy_name}/{uid}/"
                        f"month {audit['month']}"
                    )


def test_ledger_net_worth_change_equals_expected(small_slice):
    """net_worth delta must equal surplus + investment gain - interest paid, every month."""
    env = _make_env(small_slice, small_slice["user_ids"],
                    GoalPilotConfig.archived().replace(accounting_mode=ACCOUNTING_MODE_LEDGER))
    for policy_name, policy in POLICIES.items():
        for uid in small_slice["user_ids"]:
            for audit in _rollout(env, uid, policy):
                assert audit["net_worth_change"] == pytest.approx(
                    audit["expected_net_worth_change"], abs=1e-5
                ), f"net worth identity broken: {policy_name}/{uid}/month {audit['month']}"


def test_ledger_net_worth_reconciles_over_whole_episode(small_slice):
    """Open-to-close reconciliation: Delta net worth == surplus - interest + market gain."""
    config = GoalPilotConfig.archived().replace(accounting_mode=ACCOUNTING_MODE_LEDGER)
    env = _make_env(small_slice, small_slice["user_ids"], config)
    for policy_name, policy in POLICIES.items():
        for uid in small_slice["user_ids"]:
            env.reset(options={"user_id": uid})
            start_nw = env.net_worth
            months = _rollout(env, uid, policy)
            end_nw = env.net_worth
            expected = (sum(m["surplus"] for m in months)
                        + env.total_investment_gain
                        - env.total_interest_paid)
            assert (end_nw - start_nw) == pytest.approx(expected, rel=1e-9, abs=1e-4), (
                f"episode reconciliation failed for {policy_name}/{uid}"
            )


def test_legacy_mode_double_counts_and_ledger_mode_does_not(small_slice):
    """F-04 in one assertion.

    Archived accounting keeps a *contribution accumulator* in ``cash`` while
    ``goal_balances`` holds the same contributions, so ``cash + goal_balances`` counts
    every contributed rupee twice — exactly ``cumulative_savings_contributions`` extra.
    The ledger keeps ``goal_balances`` as a memo backed by real assets, and additionally
    retains the unallocated surplus that the archive silently dropped.
    """
    legacy = _make_env(small_slice, small_slice["user_ids"],
                       GoalPilotConfig.archived().replace(accounting_mode=ACCOUNTING_MODE_LEGACY))
    ledger = _make_env(small_slice, small_slice["user_ids"],
                       GoalPilotConfig.archived().replace(accounting_mode=ACCOUNTING_MODE_LEDGER))

    uid = small_slice["user_ids"][0]
    _rollout(legacy, uid, POLICIES["Savings only"])
    _rollout(ledger, uid, POLICIES["Savings only"])

    p = small_slice["profiles"].set_index("user_id").loc[uid]
    earmark = float(small_slice["goals"].loc[
        small_slice["goals"]["user_id"] == uid, "existing_funding"].sum())
    initial_savings = float(p["initial_savings"])
    initial_cash = max(0.0, initial_savings - earmark)
    contribs = legacy.cumulative_savings_contributions

    # (1) legacy `cash` is an accumulator: initial cash + every savings contribution.
    assert legacy.cash == pytest.approx(initial_cash + contribs, rel=1e-9)

    # (2) legacy `goal_balances` ALSO holds the initial earmark plus the same contributions.
    assert legacy.earmarked_goal_funding == pytest.approx(earmark + contribs, rel=1e-9)

    # (3) therefore the archived aggregate double counts by exactly `contribs`.
    archived_aggregate = legacy.cash + legacy.earmarked_goal_funding
    assert archived_aggregate == pytest.approx(initial_savings + 2 * contribs, rel=1e-9)
    assert archived_aggregate - (initial_savings + contribs) == pytest.approx(contribs, rel=1e-9)

    # (4) the ledger's memo is backed by real assets — never an independent asset.
    assert ledger.earmarked_goal_funding <= ledger.cash + ledger.portfolio + 1e-6

    # (5) the ledger retains the unallocated surplus the archive discarded entirely.
    assert ledger.cash > initial_cash + contribs
    assert ledger.total_unallocated_surplus > 0.0
    # ...and the ledger's net worth is the honest figure.
    assert ledger.net_worth == pytest.approx(
        ledger.cash + ledger.portfolio - ledger.loan_balance, rel=1e-12
    )


# --------------------------------------------------------------------------- F-05 -----

def test_loan_proceeds_and_repayment_are_balanced(small_slice):
    """Borrowing must be net-zero on net worth at origination."""
    config = GoalPilotConfig.archived().replace(accounting_mode=ACCOUNTING_MODE_LEDGER)
    env = _make_env(small_slice, small_slice["user_ids"], config)
    uid = small_slice["user_ids"][0]
    env.reset(options={"user_id": uid})

    action = np.zeros(env.action_space.shape, dtype=np.float32)
    action[:, 2] = 1.0                      # maximum loan request, nothing else
    _, _, _, _, info = env.step(action)

    principal = info["new_loan_principal"]
    assert principal > 0.0, "this fixture is expected to permit a loan"
    # The asset side gained cash and the liability side gained the same principal.
    assert env.loan_balance == pytest.approx(principal, rel=1e-9, abs=1e-6)
    assert info["ledger"]["cash"] >= principal - 1e-6


def test_loan_assets_and_liabilities_both_tracked(small_slice):
    """Over a loan episode net worth must not rise merely because debt was taken on."""
    config = GoalPilotConfig.archived().replace(accounting_mode=ACCOUNTING_MODE_LEDGER)
    env = _make_env(small_slice, small_slice["user_ids"], config)
    uid = small_slice["user_ids"][0]
    months = _rollout(env, uid, POLICIES["Loan request only"])
    assert env.cumulative_loan_principal > 0.0
    assert env.total_interest_paid > 0.0, "borrowing must incur interest"
    expected = (sum(m["surplus"] for m in months)
                + env.total_investment_gain - env.total_interest_paid)
    assert (env.net_worth - env.initial_net_worth) == pytest.approx(expected, rel=1e-9, abs=1e-4)


def test_no_loan_policy_pays_no_interest(small_slice):
    config = GoalPilotConfig.archived().replace(accounting_mode=ACCOUNTING_MODE_LEDGER)
    env = _make_env(small_slice, small_slice["user_ids"], config)
    uid = small_slice["user_ids"][0]
    _rollout(env, uid, POLICIES["Savings only"])
    assert env.total_interest_paid == 0.0
    assert env.loan_balance == 0.0
    assert env.cumulative_loan_principal == 0.0
