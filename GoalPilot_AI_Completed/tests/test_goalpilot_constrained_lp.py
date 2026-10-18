"""Capacity-constrained LP regressions (Phase 1-2 of the constrained-benchmark brief).

The existing optimizer is **not modified**. `goalpilot_constrained_lp` rebuilds the same model
from the same public helpers and adds two constraints the environment already enforces:

* ``sum_j invest_j`` <= ``(monthly_surplus - sum_j loan_j * emi_factor) x capacity_ratio``
* ``sum_j loan_j`` <= ``max_new_loan``

With both switches off the module must reproduce ``optimize_multi_goal`` exactly - that is the
legacy-parity test below.
"""
from __future__ import annotations

import numpy as np
import pytest

from goalpilot_config import GoalPilotConfig
from goalpilot_constrained_lp import (
    allowed_monthly_investment,
    numpy_conservation_report,
    solve_constrained_lp,
)

PROFILE_COLUMNS = ("monthly_income", "monthly_expenditure", "monthly_emi",
                   "initial_savings", "initial_investment", "risk_score",
                   "investment_capacity_ratio")


def _inputs(rl_data, uid, emergency_months=6.0):
    from src.multi_goal_optimizer import FinancialState
    profiles, goals = rl_data["profiles"], rl_data["goals"]
    p = profiles.loc[profiles["user_id"].astype(str) == uid].iloc[0]
    g = goals.loc[goals["user_id"].astype(str) == uid].copy()
    state = FinancialState(
        monthly_income=float(p["monthly_income"]),
        essential_expenses=float(p["monthly_expenditure"]),
        existing_emi=float(p["monthly_emi"]),
        liquid_savings=float(p["initial_savings"]),
        existing_investments=float(p["initial_investment"]),
        usable_existing_investments=0.0,
        emergency_months=emergency_months,
        emi_income_ratio_cap=0.35,
        risk_capacity=float(p["risk_score"]),
    )
    return g, state, float(p["investment_capacity_ratio"])


LP_KWARGS = dict(annual_inflation=0.03, savings_return=0.0, investment_return=0.05,
                 investment_risk_score=0.4, loan_annual_rate=0.12, loan_tenure_months=60,
                 max_loan_per_goal=150000.0)

COMPARED = ["initial_savings_allocated", "existing_assets_allocated",
            "monthly_savings_contribution", "monthly_investment_contribution",
            "loan_principal", "shortfall"]


# ------------------------------------------------ legacy parity / model equivalence --------

def test_flags_off_reproduces_the_existing_optimizer_exactly(rl_data, all_user_ids):
    """The reimplementation must be the same model, not a lookalike.

    Asserted on the objective and the weighted achievement (which uniquely identify the
    optimum) and on every allocation column, for several real users.
    """
    from src.multi_goal_optimizer import optimize_multi_goal
    checked = 0
    for uid in all_user_ids[:4]:
        g, state, _ = _inputs(rl_data, uid)
        base = optimize_multi_goal(g, state, **LP_KWARGS)
        if base["status"] != "optimal":
            continue
        mine = solve_constrained_lp(g, state, enforce_investment_capacity=False,
                                    enforce_single_loan_limit=False, **LP_KWARGS)
        assert mine["status"] == "optimal", uid
        assert mine["summary"]["objective_value"] == pytest.approx(
            base["summary"]["objective_value"], rel=1e-9, abs=1e-6), uid
        assert mine["summary"]["weighted_goal_achievement"] == pytest.approx(
            base["summary"]["weighted_goal_achievement"], rel=1e-9, abs=1e-9), uid
        assert mine["summary"]["total_shortfall"] == pytest.approx(
            base["summary"]["total_shortfall"], rel=1e-9, abs=1e-6), uid
        for column in COMPARED:
            np.testing.assert_allclose(
                mine["allocations"][column].to_numpy(),
                base["allocations"][column].to_numpy(),
                rtol=1e-9, atol=1e-5, err_msg=f"{uid}:{column}")
        checked += 1
    assert checked > 0, "no optimal plan was produced, so parity was not actually tested"


def test_the_existing_optimizer_is_unaffected_by_this_module(rl_data, all_user_ids):
    """No shared state: solving the constrained model must not perturb the original."""
    from src.multi_goal_optimizer import optimize_multi_goal
    uid = all_user_ids[0]
    g, state, ratio = _inputs(rl_data, uid)
    before = optimize_multi_goal(g, state, **LP_KWARGS)["summary"]["objective_value"]
    solve_constrained_lp(g, state, investment_capacity_ratio=ratio,
                         max_new_loan=150000.0, **LP_KWARGS)
    after = optimize_multi_goal(g, state, **LP_KWARGS)["summary"]["objective_value"]
    assert after == pytest.approx(before, rel=0.0, abs=0.0)


def test_determinism(rl_data, all_user_ids):
    uid = all_user_ids[0]
    g, state, ratio = _inputs(rl_data, uid)
    a = solve_constrained_lp(g, state, investment_capacity_ratio=ratio,
                             max_new_loan=150000.0, **LP_KWARGS)
    b = solve_constrained_lp(g, state, investment_capacity_ratio=ratio,
                             max_new_loan=150000.0, **LP_KWARGS)
    assert a["summary"]["objective_value"] == b["summary"]["objective_value"]
    for column in COMPARED:
        np.testing.assert_array_equal(a["allocations"][column].to_numpy(),
                                      b["allocations"][column].to_numpy())


# ------------------------------------------------------- capacity enforcement --------------

def test_investment_never_exceeds_the_environments_capacity(rl_data, all_user_ids):
    """The whole point: planned investment must fit the environment's ceiling."""
    checked = 0
    for uid in all_user_ids[:8]:
        g, state, ratio = _inputs(rl_data, uid)
        sol = solve_constrained_lp(g, state, investment_capacity_ratio=ratio,
                                   max_new_loan=150000.0, **LP_KWARGS)
        assert sol["status"] == "optimal", uid
        cons = sol["constraints"]
        permitted = allowed_monthly_investment(cons["monthly_surplus"],
                                               cons["loan_emi_total"], ratio)
        assert cons["investment_total"] <= permitted + 1e-6, uid
        assert cons["investment_permitted"] == pytest.approx(permitted, rel=1e-9, abs=1e-9)
        assert cons["capacity_slack"] >= -1e-6, uid
        checked += 1
    assert checked > 0


def test_capacity_zero_forces_zero_investment_without_failing(rl_data, all_user_ids):
    """A user with no investment capacity still gets a plan - it simply cannot invest.

    Note the LP carries a `shortfall` slack, so it is feasible by construction; the test also
    pins that property (see `test_infeasibility_is_unreachable...`).
    """
    checked = 0
    for uid in all_user_ids:
        g, state, _ = _inputs(rl_data, uid)
        sol = solve_constrained_lp(g, state, investment_capacity_ratio=0.0,
                                   max_new_loan=150000.0, **LP_KWARGS)
        assert sol["status"] == "optimal", uid
        assert sol["constraints"]["investment_total"] == pytest.approx(0.0, abs=1e-9), uid
        assert sol["constraints"]["investment_permitted"] == pytest.approx(0.0, abs=1e-9)
        assert sol["constraints"]["capacity_slack"] >= -1e-9
        checked += 1
    assert checked > 0


def test_capacity_constraint_bites_relative_to_the_unconstrained_model(rl_data, all_user_ids):
    """At least somewhere the added constraint must actually bind, or it proves nothing."""
    binding = 0
    for uid in all_user_ids[:8]:
        g, state, ratio = _inputs(rl_data, uid)
        free = solve_constrained_lp(g, state, enforce_investment_capacity=False,
                                    enforce_single_loan_limit=False, **LP_KWARGS)
        capped = solve_constrained_lp(g, state, investment_capacity_ratio=ratio,
                                      max_new_loan=150000.0, **LP_KWARGS)
        if capped["constraints"]["investment_total"] < (
                free["constraints"]["investment_total"] - 1e-6):
            binding += 1
    assert binding > 0, "the capacity constraint never bound, so the benchmark is untested"


# --------------------------------------------- conservation, affordability, goal caps ------

def test_budget_conservation_and_affordability(rl_data, all_user_ids):
    for uid in all_user_ids[:8]:
        g, state, ratio = _inputs(rl_data, uid)
        sol = solve_constrained_lp(g, state, investment_capacity_ratio=ratio,
                                   max_new_loan=150000.0, **LP_KWARGS)
        cons = sol["constraints"]
        # contributions plus new-loan EMIs fit inside the monthly surplus
        assert cons["contribution_total"] + cons["loan_emi_total"] <= (
            cons["monthly_surplus"] + 1e-5), uid
        assert cons["surplus_slack"] >= -1e-5, uid
        # the EMI cap is respected, on both the EMI and the combined constraint
        assert cons["loan_emi_total"] <= cons["emi_cap"] + 1e-5, uid
        assert cons["emi_slack"] >= -1e-5, uid
        residual = numpy_conservation_report(sol)
        assert residual["nonnegative_allocations"] >= -1e-9, uid
        assert residual["surplus_residual"] >= -1e-5, uid
        assert residual["capacity_residual"] >= -1e-6, uid


def test_goal_caps_and_nonnegative_allocations(rl_data, all_user_ids):
    for uid in all_user_ids[:8]:
        g, state, ratio = _inputs(rl_data, uid)
        sol = solve_constrained_lp(g, state, investment_capacity_ratio=ratio,
                                   max_new_loan=150000.0, **LP_KWARGS)
        a = sol["allocations"]
        assert sol["constraints"]["goal_cap_violations"] == 0, uid
        assert (a["projected_new_funding"] <= a["funding_gap"] + 1e-5).all(), uid
        assert (a["shortfall"] >= -1e-9).all(), uid
        assert (a["monthly_savings_contribution"] >= -1e-9).all(), uid
        assert (a["monthly_investment_contribution"] >= -1e-9).all(), uid
        assert (a["loan_principal"] >= -1e-9).all(), uid


def test_single_loan_limit_is_respected_and_is_redundant_on_this_population(
        rl_data, all_user_ids):
    """The single-loan cap is respected, but it is **not** what binds on these users.

    Measured: with the environment's own `max_new_loan = 150000` the cap never activates,
    because the EMI-affordability constraint (`sum loan x emi_factor <= income x 0.35 -
    existing_emi`) already restricts borrowing far below it. That is a real property of the
    benchmark, not a defect - but it means the executable difference between the existing LP
    and the constrained one comes from the *investment-capacity* constraint, not from loans.
    A deliberately low cap is used to show the constraint is nevertheless implemented.
    """
    for uid in all_user_ids[:8]:
        g, state, ratio = _inputs(rl_data, uid)
        capped = solve_constrained_lp(g, state, investment_capacity_ratio=ratio,
                                      max_new_loan=150000.0,
                                      enforce_single_loan_limit=True, **LP_KWARGS)
        uncapped = solve_constrained_lp(g, state, investment_capacity_ratio=ratio,
                                        max_new_loan=150000.0,
                                        enforce_single_loan_limit=False, **LP_KWARGS)
        assert capped["constraints"]["loan_total"] <= 150000.0 + 1e-6, uid
        # redundant here: enabling it changes nothing about borrowing
        assert capped["constraints"]["loan_total"] == pytest.approx(
            uncapped["constraints"]["loan_total"], rel=1e-9, abs=1e-6), uid

    # ...and it genuinely limits borrowing when the cap is tight enough to matter
    g, state, ratio = _inputs(rl_data, all_user_ids[0])
    tight = solve_constrained_lp(g, state, investment_capacity_ratio=ratio,
                                 max_new_loan=1000.0, enforce_single_loan_limit=True,
                                 **LP_KWARGS)
    loose = solve_constrained_lp(g, state, investment_capacity_ratio=ratio,
                                 max_new_loan=1000.0, enforce_single_loan_limit=False,
                                 **LP_KWARGS)
    assert tight["constraints"]["loan_total"] <= 1000.0 + 1e-6
    if loose["constraints"]["loan_total"] > 1000.0 + 1e-6:
        assert tight["constraints"]["loan_total"] < loose["constraints"]["loan_total"]


def test_infeasibility_is_unreachable_because_shortfall_is_a_slack(rl_data, all_user_ids):
    """Documented structural property, and why Phase 2 item 4 matters.

    Every goal equality contains `shortfall` with coefficient 1 and bound (0, gap), so the
    model always has a feasible slack solution. Solver "infeasibility" therefore cannot be a
    modelling outcome here - any apparent failure is numeric, and any difference between the
    LP's numbers and the environment's is an *execution* difference, not infeasibility.
    """
    uid = all_user_ids[0]
    g, state, _ = _inputs(rl_data, uid)
    sol = solve_constrained_lp(g, state, investment_capacity_ratio=0.0,
                              max_new_loan=0.0, **LP_KWARGS)
    assert sol["status"] == "optimal"
    assert sol["constraints"]["total_shortfall"] > 0.0
    assert sol["constraints"]["goal_cap_violations"] == 0


# ------------------------------------------- encode + execute in the environment -----------

def test_encoded_plan_executes_within_the_env_capacity(rl_data, all_user_ids):
    """Encode a constrained plan, run it in the environment, verify capacity every month."""
    from goalpilot_config import ACTION_MODE_SHARE
    from goalpilot_lp_encoder import encode_lp_plan_for_mix

    import goalpilot_env

    uid = all_user_ids[0]
    g, state, ratio = _inputs(rl_data, uid)
    sol = solve_constrained_lp(g, state, investment_capacity_ratio=ratio,
                               max_new_loan=150000.0, **LP_KWARGS)
    a = sol["allocations"]
    sav = np.zeros(5)
    inv = np.zeros(5)
    n = min(5, len(a))
    sav[:n] = a["monthly_savings_contribution"].to_numpy()[:n]
    inv[:n] = a["monthly_investment_contribution"].to_numpy()[:n]
    enc = encode_lp_plan_for_mix(sav, inv, n_slots=5)
    cfg = GoalPilotConfig.recommended()
    assert cfg.action_mode == ACTION_MODE_SHARE
    env = goalpilot_env.GoalPilotEnv(
        profiles=rl_data["profiles"], goals=rl_data["goals"], market=rl_data["market"],
        user_ids=[uid], config=cfg)
    env.reset(options={"user_id": uid})
    months = 0
    while True:
        action = enc["action"].copy()
        _, _, term, trunc, info = env.step(action)
        ba = info["budget_audit"]
        ceiling = ratio * (ba["discretionary_budget"] + ba["env_loan_emi_paid"]
                          + float(info["active_loan_emi"])) + 1e-6
        assert ba["investment_contribution"] <= ceiling, uid
        assert (ba["savings_contribution"] + ba["investment_contribution"]
                <= ba["discretionary_budget"] + 1e-6), uid
        months += 1
        if term or trunc:
            break
    assert months > 0
