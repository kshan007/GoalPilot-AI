"""Ledger-integrity regressions for GoalPilotEnv (findings R-01, R-04, R-05, R-06).

These pin the behaviours established by the Phase A/B read-only probes
(`audit_tools/30_final_validation_probe.py`, `audit_tools/31_probe_followup.py`):

* **R-01** — a residual loan balance left at tenure expiry must not vanish. It is now
  settled in cash (or, if cash is insufficient, carried and kept in service). Two genuine
  reproductions recorded by the probe are used: ``USER_00078`` month 138 (residual
  Rs 2,534.52 under ``corrected_accounting``) and ``USER_00081`` month 138 (residual
  Rs 236.48 under ``lp_parity``). The archived/legacy path still performs the historical
  implicit write-off, which is what lets ``test_goalpilot_env_parity.py`` keep proving
  exact archived reproduction.
* **R-04** — ``interest_paid`` is the cash interest actually paid; the accrual figure is
  reported separately, and the affordability cap keeps the unpaid-interest shortfall at
  exactly zero.
* **R-05** — the budget guard's re-scaling factor and the cash floor are exposed on
  ``budget_audit`` so a silent clamp cannot go unnoticed.
* **R-06** — the net-worth reconciliation holds month by month in ledger mode.

Why the existing suite did not catch R-01: the offending events occur on ``USER_00078``
and ``USER_00081``, which are outside the 6-user ``small_slice`` fixture used by
``test_goalpilot_env_accounting.py``.
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
LOAN_ONLY = (0.0, 0.0, 1.0)
SAVINGS_AND_LOAN = (0.5, 0.0, 1.0)

# (user, config preset, residual Rs left unamortised at tenure expiry, 1-based month)
WRITE_OFF_CASES = [
    ("USER_00078", "corrected_accounting", 2534.519836795485, 138),
    ("USER_00081", "lp_parity", 236.47895832234133, 138),
]

_PRESETS = {
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
    """Roll one episode and return the per-month ``info`` dictionaries."""
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


# ------------------------------------------------------------------ R-01 ------

@pytest.mark.parametrize("uid,cfg_name,expected_residual,expected_month", WRITE_OFF_CASES)
def test_residual_lien_is_settled_or_carried_never_written_off(
    rl_data, uid, cfg_name, expected_residual, expected_month
):
    """A residual at tenure expiry must be settled in cash or carried, not erased."""
    env = _env(rl_data, [uid], _PRESETS[cfg_name]())
    months = _roll(env, uid, SAVINGS_AND_LOAN)

    # (1) nothing is silently written off in ledger mode
    written = [m for m in months if m["residual_written_off"] > 1e-9]
    assert not written, f"ledger mode silently wrote off a residual lien: {written[0]['budget_audit']}"

    # (2) the recorded residual event still occurs, at the recorded month
    touched = [m for m in months
               if m["residual_settled_cash"] > 1e-9 or m["residual_carried"] > 1e-9]
    assert touched, "the recorded residual event no longer occurs"
    assert touched[0]["budget_audit"]["month"] == expected_month, (
        f"residual event moved to month {touched[0]['budget_audit']['month']}"
    )
    peak = max(m["residual_settled_cash"] + m["residual_carried"] for m in touched)
    assert peak == pytest.approx(expected_residual, rel=1e-6, abs=0.01)

    # (3) settlement debits cash; carry keeps the liability and keeps it in service
    for m in months:
        settled = m["residual_settled_cash"]
        carried = m["residual_carried"]
        assert settled >= 0.0 and carried >= 0.0
        assert not (settled > 1e-9 and carried > 1e-9), "a month cannot both settle and carry"
    settling = [m for m in months if m["residual_settled_cash"] > 1e-9]
    if settling:
        assert all(m["ledger"]["loan_balance"] <= 1e-6 for m in settling)
    carrying = [m for m in months if m["residual_carried"] > 1e-9]
    if carrying:
        # A carried residual stays on the books and stays in service.
        assert all(m["ledger"]["loan_balance"] > 1e-6 for m in carrying)

    # (4) the accounting stays exact, month by month
    for m in months:
        ba = m["budget_audit"]
        assert ba["net_worth_change"] == pytest.approx(
            ba["expected_net_worth_change"], abs=1e-4
        ), f"net-worth identity broken at month {ba['month']}"


@pytest.mark.parametrize("uid,cfg_name,expected_residual,expected_month", WRITE_OFF_CASES)
def test_cash_flow_conservation_with_residual_settlement(
    rl_data, uid, cfg_name, expected_residual, expected_month
):
    """Every month: cash moves by surplus - EMI - investment + new loan - settlement."""
    env = _env(rl_data, [uid], _PRESETS[cfg_name]())
    months = _roll(env, uid, SAVINGS_AND_LOAN)

    for prev, m in zip(months, months[1:]):
        ba = m["budget_audit"]
        expected_delta = (
            ba["surplus"]
            - ba["env_loan_emi_paid"]
            - m["investment_contribution"]
            + m["new_loan_principal"]
            - m["residual_settled_cash"]
        )
        actual_delta = m["ledger"]["cash"] - prev["ledger"]["cash"]
        assert actual_delta == pytest.approx(expected_delta, abs=1e-6), (
            f"cash-flow identity broken at month {ba['month']}: "
            f"actual {actual_delta} vs expected {expected_delta}"
        )


def test_archived_mode_keeps_the_historical_write_off(rl_data):
    """The legacy path must still erase the residual, or archived parity would break."""
    env = _env(rl_data, ["USER_00078"], GoalPilotConfig.archived())
    months = _roll(env, "USER_00078", SAVINGS_AND_LOAN)

    written = [m for m in months if m["residual_written_off"] > 1e-9]
    assert written, "archived mode must retain the historical implicit write-off"
    assert written[0]["budget_audit"]["month"] == 138
    assert written[0]["residual_written_off"] == pytest.approx(2534.519836795485, rel=1e-6)
    # ...and an archived-mode episode never settles anything in cash.
    assert all(m["residual_settled_cash"] == 0.0 for m in months)
    assert all(m["residual_carried"] == 0.0 for m in months)


# ------------------------------------------------------------------ R-04 ------

@pytest.mark.parametrize("cfg_name", ["lp_parity", "recommended"])
def test_interest_paid_is_cash_interest_and_shortfall_is_zero(rl_data, cfg_name):
    """Accrued and cash interest coincide, and no interest is silently forgiven."""
    users = ["USER_00001", "USER_00078", "USER_00081"]
    env = _env(rl_data, users, _PRESETS[cfg_name]())
    for uid in users:
        for policy in (NO_ACTION, SAVINGS_ONLY, SAVINGS_AND_LOAN, LOAN_ONLY):
            months = _roll(env, uid, policy)
            for m in months:
                ba = m["budget_audit"]
                assert ba["interest_shortfall"] == pytest.approx(0.0, abs=1e-9), (
                    f"unpaid interest appeared at month {ba['month']} ({uid}/{policy})"
                )
                assert ba["interest_paid_cash"] == pytest.approx(
                    ba["interest_accrued"], abs=1e-9
                )
                assert m["interest_paid"] == pytest.approx(ba["interest_paid_cash"], abs=1e-12)
            assert env.total_interest_paid == pytest.approx(
                sum(m["budget_audit"]["interest_paid_cash"] for m in months),
                rel=1e-9, abs=1e-6,
            )


# ------------------------------------------------------------------ R-05 ------

@pytest.mark.parametrize("cfg_name", ["lp_parity", "recommended"])
def test_budget_guard_and_cash_floor_are_exposed(rl_data, cfg_name):
    """The guard factor is always reported, bounded, and never triggered needlessly."""
    users = ["USER_00001", "USER_00078"]
    env = _env(rl_data, users, _PRESETS[cfg_name]())
    for uid in users:
        for policy in (NO_ACTION, SAVINGS_ONLY, SAVINGS_AND_LOAN, LOAN_ONLY):
            for m in _roll(env, uid, policy):
                ba = m["budget_audit"]
                assert 0.0 < ba["guard_scale"] <= 1.0 + 1e-12, ba
                assert ba["cash_floor_active"] in (False, 0), (
                    f"cash floor became active at month {ba['month']} ({uid}/{policy})"
                )
                # With no new loan and a policy that cannot over-request, no re-scaling
                # should be needed at all.
                if policy in (NO_ACTION, SAVINGS_ONLY):
                    assert ba["guard_scale"] == pytest.approx(1.0, abs=1e-12), ba
                assert ba["budget_check"] == pytest.approx(0.0, abs=1e-6)


# ------------------------------------------------------------------ R-06 ------

@pytest.mark.parametrize("cfg_name", ["corrected_accounting", "lp_parity"])
def test_net_worth_reconciliation_holds_every_month(rl_data, cfg_name):
    """Open-to-close: net-worth delta equals surplus + market gain - accrued interest."""
    users = ["USER_00001", "USER_00005", "USER_00078", "USER_00081"]
    env = _env(rl_data, users, _PRESETS[cfg_name]())
    for uid in users:
        for policy in (NO_ACTION, SAVINGS_ONLY, INVEST_ONLY, MIXED, LOAN_ONLY, SAVINGS_AND_LOAN):
            for m in _roll(env, uid, policy):
                ba = m["budget_audit"]
                assert ba["net_worth_change"] == pytest.approx(
                    ba["expected_net_worth_change"], abs=1e-4
                ), (
                    f"{cfg_name}/{uid}/{policy}/month {ba['month']}: "
                    f"{ba['net_worth_change']} vs {ba['expected_net_worth_change']}"
                )
