"""Adapters from the existing GoalPilot simulation schema to the multi-goal LP.

The supplied simulation contains one goal record per user. This module deliberately
separates actual simulated financial profiles from any synthetic multi-goal examples.
"""
from __future__ import annotations
from typing import Any
import pandas as pd
try:
    from .multi_goal_optimizer import FinancialState
except ImportError:  # allow running scripts with src/ on PYTHONPATH
    from multi_goal_optimizer import FinancialState

REQUIRED_PROFILE_COLUMNS = {
    "user_id", "final_monthly_income", "final_monthly_expenditure",
    "final_monthly_emi", "final_savings_balance", "risk_profile"
}
RISK_PROFILE_CAPACITY = {"conservative": 0.25, "moderate": 0.50, "aggressive": 0.75}


def financial_state_from_simulation_row(row: pd.Series | dict[str, Any], *,
                                         emergency_months: float = 6.0,
                                         emi_income_ratio_cap: float = 0.35,
                                         risk_capacity_override: float | None = None) -> tuple[str, FinancialState]:
    """Map one final_optimisation_input row into optimizer state.

    risk_capacity is a configurable proxy derived from the simulation's risk_profile,
    not a validated investment suitability assessment. Existing portfolio value is
    preserved in the source row but is not counted as liquid cash by this LP.
    """
    d = dict(row)
    missing = REQUIRED_PROFILE_COLUMNS - set(d)
    if missing:
        raise ValueError(f"Simulation profile is missing required columns: {sorted(missing)}")
    profile = str(d["risk_profile"]).strip().lower()
    if risk_capacity_override is None:
        if profile not in RISK_PROFILE_CAPACITY:
            raise ValueError(f"Unknown risk_profile {profile!r}; supply an explicit risk_capacity_override")
        risk_capacity = RISK_PROFILE_CAPACITY[profile]
    else:
        risk_capacity = float(risk_capacity_override)
        if not 0 <= risk_capacity <= 1:
            raise ValueError("risk_capacity_override must be between 0 and 1")
    state = FinancialState(
        monthly_income=float(d["final_monthly_income"]),
        # The simulation exposes final_monthly_expenditure as a combined spend
        # field. It is mapped to essential_expenses for conservative cash-flow
        # capacity; no extra discretionary amount is subtracted here.
        essential_expenses=float(d["final_monthly_expenditure"]),
        discretionary_expenses=0.0,
        existing_emi=float(d["final_monthly_emi"]),
        liquid_savings=float(d["final_savings_balance"]),
        # Existing portfolio is not silently treated as cash; the current LP has no
        # evidence that this value is liquid/available for goals.
        existing_investments=float(d.get("final_portfolio_value", 0.0) or 0.0),
        usable_existing_investments=0.0,
        emergency_months=float(emergency_months),
        emi_income_ratio_cap=float(emi_income_ratio_cap),
        risk_capacity=risk_capacity,
    )
    state.validate()
    return str(d["user_id"]), state


def legacy_goal_to_goal_row(row: pd.Series | dict[str, Any], *, goal_id: str | None = None,
                            goal_name: str = "Existing simulated goal",
                            priority: float = 3.0, criticality: float = 3.0,
                            target_date: str | None = None) -> dict[str, Any]:
    """Map a legacy one-goal simulation row to the new goal schema.

    Priority, criticality, a calendar target date, and current goal-specific funding are not
    provided by the legacy outcome dataset; defaults must therefore be explicitly reviewed.
    """
    d = dict(row)
    required = {"user_id", "target_amount", "goal_horizon_months"}
    missing = required - set(d)
    if missing:
        raise ValueError(f"Legacy goal row is missing required columns: {sorted(missing)}")
    months = int(d["goal_horizon_months"])
    if months < 1:
        raise ValueError("goal_horizon_months must be at least 1")
    if target_date is None:
        # Do not silently infer a real deadline: this generated date is explicitly
        # an approximate mapping for integration testing only.
        target_date = (pd.Timestamp.today().normalize() + pd.DateOffset(months=months)).strftime("%Y-%m-%d")
    # Historical/at-deadline funding is not a current balance; do not count it as
    # existing funding. Current goal-specific funding must be supplied separately.
    target = float(d["target_amount"])
    return {
        "goal_id": goal_id or f"LEGACY_{d['user_id']}",
        "goal_name": goal_name,
        "current_cost": target,
        "target_date": target_date,
        "time_horizon_months": months,
        "priority": float(priority),
        "criticality": float(criticality),
        "existing_funding": 0.0,
    }
