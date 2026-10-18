"""LP encode/decode parity for the `mix` action mapping (Change 1).

The LP optimizer emits absolute rupees; `mix` weights are scale-free. These tests pin the
conversion, its exact reproduction property, the degenerate cases, and the *structural*
deviation that the schema cannot avoid (a plan that does not consume the whole budget).
"""
from __future__ import annotations

import numpy as np
import pytest

from goalpilot_lp_encoder import (
    ACTION_TOLERANCE,
    TOLERANCE,
    decode_mix_action,
    encode_lp_plan_for_mix,
)

MIXED_PLAN = (np.array([120_000.0, 80_000.0, 40_000.0]),
              np.array([30_000.0, 60_000.0, 15_000.0]))


def test_round_trip_is_exact_when_budget_equals_plan_total():
    """The documented tolerance, split by error source.

    ``encode`` is exact in float64, but the environment's action Box is float32, so the
    tolerance that matters for an action actually fed to the environment is the float32 one.
    Both are asserted separately so a regression can be attributed.
    """
    sav, inv = MIXED_PLAN
    enc = encode_lp_plan_for_mix(sav, inv, n_slots=5)
    exact = decode_mix_action(enc["action_float64"], enc["plan_total"], n_slots=5)
    np.testing.assert_allclose(exact["savings_per_goal"][:3], sav, rtol=1e-12, atol=1e-9)
    np.testing.assert_allclose(exact["investments_per_goal"][:3], inv, rtol=1e-12, atol=1e-9)

    dec = decode_mix_action(enc["action"], enc["plan_total"], n_slots=5)
    assert enc["action"].dtype == np.float32
    np.testing.assert_allclose(dec["savings_per_goal"][:3], sav,
                               rtol=ACTION_TOLERANCE, atol=1e-3)
    np.testing.assert_allclose(dec["investments_per_goal"][:3], inv,
                               rtol=ACTION_TOLERANCE, atol=1e-3)
    # slots without a plan stay empty
    np.testing.assert_allclose(dec["savings_per_goal"][3:], 0.0, atol=1e-9)
    np.testing.assert_allclose(dec["investments_per_goal"][3:], 0.0, atol=1e-9)


def test_investment_fraction_and_channel_sums_are_preserved():
    sav, inv = MIXED_PLAN
    enc = encode_lp_plan_for_mix(sav, inv, n_slots=5)
    assert enc["investment_fraction"] == pytest.approx(inv.sum() / (sav.sum() + inv.sum()))
    weights = enc["action"]
    mix = weights[:, 1].sum() / (weights[:, 0].sum() + weights[:, 1].sum())
    assert mix == pytest.approx(enc["investment_fraction"], rel=1e-6)
    # everything stays inside the Box[0, 1] action space, and the peak weight is exactly 1
    assert weights.min() >= 0.0
    assert weights.max() == pytest.approx(1.0, rel=1e-6)


def test_zero_savings_plan():
    enc = encode_lp_plan_for_mix(np.zeros(3), np.array([50.0, 25.0, 25.0]), n_slots=3)
    assert enc["has_savings"] is False
    assert enc["investment_fraction"] == pytest.approx(1.0)
    np.testing.assert_allclose(enc["action"][:, 0], 0.0, atol=1e-12)
    dec = decode_mix_action(enc["action"], enc["plan_total"], n_slots=3)
    assert dec["savings_total"] == pytest.approx(0.0, abs=1e-6)
    np.testing.assert_allclose(dec["investments_per_goal"], [50.0, 25.0, 25.0], rtol=1e-9)


def test_zero_investment_plan():
    enc = encode_lp_plan_for_mix(np.array([50.0, 25.0, 25.0]), np.zeros(3), n_slots=3)
    assert enc["has_investment"] is False
    assert enc["investment_fraction"] == pytest.approx(0.0)
    np.testing.assert_allclose(enc["action"][:, 1], 0.0, atol=1e-12)
    dec = decode_mix_action(enc["action"], enc["plan_total"], n_slots=3)
    assert dec["investment_total"] == pytest.approx(0.0, abs=1e-6)
    np.testing.assert_allclose(dec["savings_per_goal"], [50.0, 25.0, 25.0], rtol=1e-9)


def test_zero_total_plan_is_degenerate_and_a_true_no_op():
    enc = encode_lp_plan_for_mix(np.zeros(3), np.zeros(3), n_slots=3)
    assert enc["is_degenerate"] is True
    assert enc["plan_total"] == 0.0
    assert enc["investment_fraction"] == 0.0
    np.testing.assert_allclose(enc["action"], 0.0, atol=0.0)
    dec = decode_mix_action(enc["action"], 1_000_000.0, n_slots=3)
    assert dec["requested_total"] == 0.0


def test_fully_allocated_plan_reports_no_unallocated_budget():
    sav = np.array([60_000.0, 40_000.0])
    inv = np.array([20_000.0, 10_000.0])
    enc = encode_lp_plan_for_mix(sav, inv, n_slots=3, lp_budget=float(sav.sum() + inv.sum()))
    assert enc["unallocated_rupees"] == pytest.approx(0.0, abs=1e-9)


def test_partially_allocated_plan_reports_the_remainder_explicitly():
    sav = np.array([60_000.0, 40_000.0])
    inv = np.array([20_000.0, 10_000.0])
    budget = 500_000.0
    enc = encode_lp_plan_for_mix(sav, inv, n_slots=3, lp_budget=budget)
    assert enc["unallocated_rupees"] == pytest.approx(budget - (sav.sum() + inv.sum()))


def test_plan_exceeding_the_stated_budget_reports_a_negative_remainder():
    """Reported, never clamped: over-budget plans must stay visible to the caller."""
    enc = encode_lp_plan_for_mix(np.array([100.0]), np.array([50.0]), n_slots=1, lp_budget=100.0)
    assert enc["unallocated_rupees"] == pytest.approx(-50.0)


def test_scale_deviation_is_structural_not_an_encoding_error():
    """When A != plan_total the decode is the plan scaled by A/plan_total, exactly.

    The schema always requests the whole available budget, so a plan that did not consume the
    budget cannot be reproduced at a larger budget. That scale is returned for separate
    reporting; it is not an encoder error and the environment's capacity limits are applied
    later still.
    """
    sav, inv = MIXED_PLAN
    enc = encode_lp_plan_for_mix(sav, inv, n_slots=5)
    for factor in (0.5, 1.0, 2.0):
        budget = enc["plan_total"] * factor
        dec = decode_mix_action(enc["action"], budget, n_slots=5)
        np.testing.assert_allclose(dec["savings_per_goal"][:3], sav * factor,
                                   rtol=1e-6, atol=1e-6)
        np.testing.assert_allclose(dec["investments_per_goal"][:3], inv * factor,
                                   rtol=1e-6, atol=1e-6)


def test_single_goal_and_many_goal_plans_are_handled():
    one = encode_lp_plan_for_mix(np.array([500.0]), np.array([250.0]), n_slots=5)
    dec = decode_mix_action(one["action_float64"], one["plan_total"], n_slots=5)
    assert dec["savings_total"] == pytest.approx(500.0, rel=1e-9)
    many = encode_lp_plan_for_mix(np.full(5, 10.0), np.full(5, 30.0), n_slots=5)
    dec_many = decode_mix_action(many["action_float64"], many["plan_total"], n_slots=5)
    assert dec_many["savings_total"] == pytest.approx(50.0, rel=1e-9)
    assert dec_many["investment_total"] == pytest.approx(150.0, rel=1e-9)


def test_encoder_is_deterministic():
    sav, inv = MIXED_PLAN
    a = encode_lp_plan_for_mix(sav, inv, n_slots=5)["action"]
    b = encode_lp_plan_for_mix(sav, inv, n_slots=5)["action"]
    np.testing.assert_array_equal(a, b)


def test_mismatched_input_lengths_are_rejected():
    with pytest.raises(ValueError):
        encode_lp_plan_for_mix(np.zeros(3), np.zeros(2), n_slots=3)
    with pytest.raises(ValueError):
        encode_lp_plan_for_mix(np.zeros(4), np.zeros(4), n_slots=3)


# ---------------------------------------------- against the real LP optimizer ----------------

def test_real_lp_plan_is_reproduced_by_the_encoder(rl_data, all_user_ids):
    """End-to-end: solve the real LP, encode, decode, compare to the LP's own columns."""
    import pandas as pd

    from src.multi_goal_optimizer import FinancialState, optimize_multi_goal

    from goalpilot_lp_encoder import encode_lp_allocations

    profiles, goals = rl_data["profiles"], rl_data["goals"]
    checked = 0
    for uid in all_user_ids[:3]:
        p = profiles.loc[profiles["user_id"].astype(str) == uid].iloc[0]
        g = goals.loc[goals["user_id"].astype(str) == uid].copy()
        state = FinancialState(
            monthly_income=float(p["monthly_income"]),
            essential_expenses=float(p["monthly_expenditure"]),
            existing_emi=float(p["monthly_emi"]),
            liquid_savings=float(p["initial_savings"]),
            existing_investments=float(p["initial_investment"]),
            usable_existing_investments=0.0, emergency_months=6.0,
            emi_income_ratio_cap=0.35, risk_capacity=float(p["risk_score"]))
        res = optimize_multi_goal(
            g, state, annual_inflation=0.03, savings_return=0.0, investment_return=0.05,
            investment_risk_score=0.4, loan_annual_rate=0.12, loan_tenure_months=60,
            max_loan_per_goal=150000.0)
        if res["status"] != "optimal" or res["allocations"].empty:
            continue
        alloc = res["allocations"]
        enc = encode_lp_allocations(alloc, n_slots=5)
        if enc["is_degenerate"]:
            continue
        dec = decode_mix_action(enc["action"], enc["plan_total"], n_slots=5)
        np.testing.assert_allclose(
            dec["savings_per_goal"][:len(alloc)],
            alloc["monthly_savings_contribution"].to_numpy(dtype=float),
            rtol=1e-6, atol=1e-4)
        np.testing.assert_allclose(
            dec["investments_per_goal"][:len(alloc)],
            alloc["monthly_investment_contribution"].to_numpy(dtype=float),
            rtol=1e-6, atol=1e-4)
        assert isinstance(alloc, pd.DataFrame)
        checked += 1
    assert checked > 0, "no optimal LP plan was produced, so nothing was validated"
