"""Encode an LP plan (absolute rupees) into the scale-free `mix` action vector.

Why this exists
---------------
The LP optimizer emits **absolute rupee** amounts per goal
(`monthly_savings_contribution`, `monthly_investment_contribution`), while `mix`/`share` action
weights are *scale-free*: only the ratio of the savings-weight sum to the investment-weight sum
carries information, and within each channel only the relative weights matter. Encoding the
absolute amounts directly as weights therefore destroys exactly the information that
distinguishes a plan that allocates 100% of the budget from one that allocates 60%.

This module performs the conversion explicitly and reversibly:

    action = encode(plan)      -> weights + a documented investment fraction
    plan'  = decode(action, A) -> rupee amounts, *before* capacity constraints

Reproduction guarantee (the documented tolerance)
-------------------------------------------------
``decode(encode(plan), A = plan_total)`` reproduces the plan's per-goal savings and investment
amounts to **float64 machine precision** (``TOLERANCE = 1e-9``, asserted at 1e-12). The
environment's action ``Box`` is **float32**, so an action that actually reaches the environment
reproduces the plan only to ``ACTION_TOLERANCE = 1e-6`` relative; ``action_float64`` is returned
so the two error sources stay separable. For any other budget the mixed
schema cannot reproduce the plan, because the action always requests the *whole* available
budget: the decoded amounts are then the plan scaled by ``A / plan_total``. That is a
**structural property of the action schema, not an encoding error**, and it is returned
explicitly as ``scale_factor`` so it can be reported separately from:
  * encoding error (none: the map is exact), and
  * capacity deviation (applied later by the environment, not by the encoder).

The plan's originally unallocated budget is reported explicitly as ``unallocated_rupees`` when
the LP's own budget is supplied.
"""
from __future__ import annotations

import numpy as np

TOLERANCE = 1e-9          # exactness of the encoding itself (float64 arithmetic)
ACTION_TOLERANCE = 1e-6   # end-to-end reproduction, bounded by the float32 action space


def _as_float_array(values) -> np.ndarray:
    if values is None:
        return np.zeros(0, dtype="float64")
    return np.asarray(values, dtype="float64").ravel()


def encode_lp_plan_for_mix(savings, investments, *, n_slots: int | None = None,
                           lp_budget: float | None = None) -> dict:
    """Convert absolute per-goal rupee amounts into a `mix` action vector.

    ``savings`` / ``investments`` are per-goal rupee amounts (one entry per goal slot).
    ``lp_budget`` is the budget the LP planned against, used only to report the amount the
    plan left unallocated.

    Returns a dict containing the action, the explicit investment fraction, the within-channel
    distribution weights, the plan totals and the unallocated remainder.
    """
    sav = _as_float_array(savings)
    inv = _as_float_array(investments)
    if sav.size != inv.size:
        raise ValueError("savings and investments must have the same length")
    n = int(sav.size if n_slots is None else n_slots)
    if n < sav.size:
        raise ValueError("n_slots is smaller than the plan length")

    savings_total = float(sav.sum())
    investment_total = float(inv.sum())
    plan_total = savings_total + investment_total

    savings_weights = np.zeros(n, dtype="float64")
    investment_weights = np.zeros(n, dtype="float64")
    action64 = np.zeros((n, 3), dtype="float64")

    is_degenerate = plan_total <= TOLERANCE
    if not is_degenerate:
        # within-channel distribution: pure shares of each channel's own envelope
        if savings_total > TOLERANCE:
            savings_weights[:sav.size] = sav / savings_total
        if investment_total > TOLERANCE:
            investment_weights[:inv.size] = inv / investment_total

        investment_fraction = investment_total / plan_total
        # Scale so that (a) the ratio of the channel sums equals the investment fraction and
        # (b) the largest weight is exactly 1.0, keeping the vector inside the Box[0, 1]
        # action space without distorting the ratios.
        peak = max(savings_weights.max() * (1.0 - investment_fraction),
                   investment_weights.max() * investment_fraction)
        scale = (1.0 / peak) if peak > TOLERANCE else 0.0
        action64[:sav.size, 0] = savings_weights[:sav.size] * (1.0 - investment_fraction) * scale
        action64[:sav.size, 1] = investment_weights[:sav.size] * investment_fraction * scale
    else:
        investment_fraction = 0.0

    # The environment's Box is float32, so this is what actually reaches it. The exact
    # float64 weights are returned alongside so that *encoding* error (float64, ~1e-16) can be
    # told apart from *representation* error (float32, ~1e-7 relative).
    action = action64.astype("float32")

    unallocated = None if lp_budget is None else float(lp_budget) - plan_total
    return {
        "action": action,
        "action_float64": action64,
        "n_slots": n,
        "savings_per_goal": sav.copy(),
        "investments_per_goal": inv.copy(),
        "savings_weights": savings_weights,
        "investment_weights": investment_weights,
        "investment_fraction": investment_fraction,
        "savings_total": savings_total,
        "investment_total": investment_total,
        "plan_total": plan_total,
        "unallocated_rupees": unallocated,
        "has_savings": savings_total > TOLERANCE,
        "has_investment": investment_total > TOLERANCE,
        "is_degenerate": is_degenerate,
    }


def decode_mix_action(action, available_budget: float, *, n_slots: int | None = None) -> dict:
    """Decode a `mix`/`share` action back into rupee amounts, **before** capacity limits.

    Implements the environment's `mix` arithmetic up to (but excluding) the investment-cap
    step, so the encoded plan can be verified independently of capacity.
    """
    arr = np.asarray(action, dtype="float64")
    n = int(arr.shape[0] if n_slots is None else n_slots)
    budget = max(0.0, float(available_budget))
    w_sav = arr[:n, 0]
    w_inv = arr[:n, 1]
    combined = np.concatenate([w_sav, w_inv])
    total = float(combined.sum())
    if total <= TOLERANCE:
        zeros = np.zeros(n, dtype="float64")
        return {
            "savings_per_goal": zeros, "investments_per_goal": zeros.copy(),
            "savings_total": 0.0, "investment_total": 0.0,
            "requested_total": 0.0, "investment_fraction": 0.0,
        }
    shares = combined / total
    savings = shares[:n] * budget
    investments = shares[n:] * budget
    return {
        "savings_per_goal": savings,
        "investments_per_goal": investments,
        "savings_total": float(savings.sum()),
        "investment_total": float(investments.sum()),
        "requested_total": float(savings.sum() + investments.sum()),
        "investment_fraction": float(investments.sum()) / budget if budget > 0 else 0.0,
    }


def encode_lp_allocations(allocations, n_slots: int, lp_budget: float | None = None) -> dict:
    """Convenience wrapper: encode the LP optimizer's own `allocations` frame.

    The frame must carry `goal_id`, `monthly_savings_contribution` and
    `monthly_investment_contribution`. Goals are placed by their position in the frame; any
    slot without a row stays zero. The loan column is handled by the caller, because it is a
    third action dimension with its own caps.
    """
    sav = np.zeros(n_slots, dtype="float64")
    inv = np.zeros(n_slots, dtype="float64")
    for i, (_, row) in enumerate(allocations.iterrows()):
        if i >= n_slots:
            break
        sav[i] = max(0.0, float(row["monthly_savings_contribution"]))
        inv[i] = max(0.0, float(row["monthly_investment_contribution"]))
    encoded = encode_lp_plan_for_mix(sav, inv, n_slots=n_slots, lp_budget=lp_budget)
    encoded["goal_ids"] = [str(g) for g in allocations.get("goal_id", [])]
    return encoded
