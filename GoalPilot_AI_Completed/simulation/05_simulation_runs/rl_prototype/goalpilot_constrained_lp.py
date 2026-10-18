"""Capacity-constrained LP benchmark, aligned with the RL environment's constraints.

Why this exists
---------------
The existing LP (`GoalPilot_MultiGoal_Extension/src/multi_goal_optimizer.py`) already separates
``save`` and ``invest`` per goal, but it bounds monthly investment **only by the monthly
surplus**. The RL environment additionally caps investment at

    invest_cap = available_after_existing_loan x investment_capacity_ratio

with ``investment_capacity_ratio <= 0.4988`` in the sample population. The v6 report
(`outputs/reward_design/v6/CORRECTED_LP_COMPARISON.md`) measured the consequence: the LP plans
**1,438,590** of investment the environment cannot accept, which `share` mode then silently
relabels as savings.

The existing optimizer is **not modified**. This module rebuilds the same model with the same
public helpers and adds the missing constraints, so the two can be compared like for like.

Constraints added (each independently switchable, so their effects can be isolated)
----------------------------------------------------------------------------------
1. ``enforce_investment_capacity`` -  sum_j invest_j <= (monthly_surplus - sum_j loan_j *
   emi_factor) * investment_capacity_ratio, i.e. exactly the environment's rule with the
   capacity base taken net of the new loan's EMI commitments.
2. ``enforce_single_loan_limit`` -  sum_j loan_j <= max_new_loan, mirroring the environment's
   single active loan and its ``max_new_loan`` cap. The existing LP bounds loans only
   *per goal*, so it can originate n x the limit in one month.

With both switches off this module must reproduce ``optimize_multi_goal`` **exactly**
(objective and every allocation), which is asserted by
``tests/test_goalpilot_constrained_lp.py``.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from src.multi_goal_optimizer import (
    FinancialState,
    fv_monthly_contribution_factor,
    monthly_emi_per_rupee,
    prepare_goals,
)

KINDS = ("cash", "asset", "save", "invest", "loan", "short")


def solve_constrained_lp(
    goals: pd.DataFrame,
    state: FinancialState,
    *,
    annual_inflation: float = 0.03,
    savings_return: float = 0.0,
    investment_return: float = 0.05,
    investment_risk_score: float = 0.4,
    loan_annual_rate: float = 0.12,
    loan_tenure_months: int = 60,
    max_loan_per_goal: float = 150000.0,
    max_new_loan: float | None = None,
    investment_capacity_ratio: float | None = None,
    existing_asset_return: float = 0.0,
    existing_asset_risk_score: float = 0.2,
    shortfall_penalty: float = 1.0,
    loan_cost_penalty: float = 0.02,
    risk_penalty: float = 0.0002,
    enforce_investment_capacity: bool = True,
    enforce_single_loan_limit: bool = True,
) -> dict[str, Any]:
    """Solve the LP with the RL environment's capacity and loan constraints applied."""
    if max_new_loan is None:
        max_new_loan = max_loan_per_goal
    if investment_capacity_ratio is None:
        investment_capacity_ratio = 1.0

    state.validate()
    g = prepare_goals(goals, annual_inflation)
    n = len(g)

    def ix(j: int, kind: str) -> int:
        return 6 * j + KINDS.index(kind)

    nv = 6 * n
    c = [0.0] * nv
    bounds = [(0, None)] * nv
    A_ub: list[list[float]] = []
    b_ub: list[float] = []
    A_eq: list[list[float]] = []
    b_eq: list[float] = []

    earmarked = float(g.existing_funding.sum())
    available_cash = max(
        0.0, state.liquid_savings - state.emergency_months * state.essential_expenses - earmarked
    )
    usable_existing_assets = float(state.usable_existing_investments)
    monthly_surplus = max(
        0.0,
        state.monthly_income - state.essential_expenses - state.discretionary_expenses
        - state.existing_emi,
    )
    emi_cap = max(0.0, state.monthly_income * state.emi_income_ratio_cap - state.existing_emi)
    emi_factor = monthly_emi_per_rupee(loan_annual_rate, loan_tenure_months)
    total_weight = float(g.goal_priority_score.sum()) or 1.0

    for j, row in g.reset_index(drop=True).iterrows():
        months = int(row.time_horizon_months)
        sf = fv_monthly_contribution_factor(savings_return, months)
        inv_factor = fv_monthly_contribution_factor(investment_return, months)
        asset_factor = (1 + existing_asset_return) ** (months / 12)
        weight = float(row.goal_priority_score) / total_weight
        c[ix(j, "short")] = shortfall_penalty * weight
        c[ix(j, "loan")] = loan_cost_penalty * max(0.0, loan_annual_rate) * loan_tenure_months / 12
        c[ix(j, "asset")] = 0.001 + risk_penalty * existing_asset_risk_score
        c[ix(j, "save")] = 0.001
        c[ix(j, "invest")] = 0.001 + risk_penalty * investment_risk_score
        bounds[ix(j, "cash")] = (0, None)
        bounds[ix(j, "asset")] = (0, 0) if existing_asset_risk_score > state.risk_capacity else (0, None)
        bounds[ix(j, "save")] = (0, None)
        bounds[ix(j, "invest")] = (0, 0) if investment_risk_score > state.risk_capacity else (0, None)
        bounds[ix(j, "loan")] = (0, min(max_loan_per_goal, float(row.funding_gap)))
        bounds[ix(j, "short")] = (0, float(row.funding_gap))
        eq = [0.0] * nv
        eq[ix(j, "cash")] = 1.0
        eq[ix(j, "asset")] = asset_factor
        eq[ix(j, "save")] = sf
        eq[ix(j, "invest")] = inv_factor
        eq[ix(j, "loan")] = 1.0
        eq[ix(j, "short")] = 1.0
        A_eq.append(eq)
        b_eq.append(float(row.funding_gap))

    def shared_row(kinds: dict[str, float]) -> list[float]:
        row = [0.0] * nv
        for j in range(n):
            for kind, coefficient in kinds.items():
                row[ix(j, kind)] = coefficient
        return row

    # --- the existing model's own constraints, reproduced exactly -------------------------
    A_ub.append(shared_row({"cash": 1.0}))
    b_ub.append(available_cash)
    A_ub.append(shared_row({"asset": 1.0}))
    b_ub.append(usable_existing_assets)
    A_ub.append(shared_row({"save": 1.0, "invest": 1.0}))
    b_ub.append(monthly_surplus)
    A_ub.append(shared_row({"loan": emi_factor}))
    b_ub.append(emi_cap)
    A_ub.append(shared_row({"save": 1.0, "invest": 1.0, "loan": emi_factor}))
    b_ub.append(monthly_surplus)

    # --- constraint 1: investment capacity, as the environment defines it ------------------
    if enforce_investment_capacity:
        # sum invest - ratio * (surplus - sum loan*emi_factor) <= 0
        row = shared_row({"invest": 1.0})
        for j in range(n):
            row[ix(j, "loan")] += investment_capacity_ratio * emi_factor
        A_ub.append(row)
        b_ub.append(investment_capacity_ratio * monthly_surplus)

    # --- constraint 2: a single loan, mirroring the environment ----------------------------
    if enforce_single_loan_limit:
        A_ub.append(shared_row({"loan": 1.0}))
        b_ub.append(float(max_new_loan))

    result = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds,
                     method="highs")
    if not result.success:
        return {
            "status": "infeasible_or_solver_error",
            "solver_message": result.message,
            "goals": g,
            "allocations": pd.DataFrame(),
            "objective": float("nan"),
            "constraints": {},
        }

    records = []
    for j, row in g.reset_index(drop=True).iterrows():
        months = int(row.time_horizon_months)
        sf = fv_monthly_contribution_factor(savings_return, months)
        inv_factor = fv_monthly_contribution_factor(investment_return, months)
        asset_factor = (1 + existing_asset_return) ** (months / 12)
        cash = float(result.x[ix(j, "cash")])
        asset = float(result.x[ix(j, "asset")])
        save = float(result.x[ix(j, "save")])
        invest = float(result.x[ix(j, "invest")])
        loan = float(result.x[ix(j, "loan")])
        short = float(result.x[ix(j, "short")])
        # Column names deliberately mirror `optimize_multi_goal` so the two plans can be
        # compared without a mapping layer.
        records.append({
            "goal_id": row.goal_id,
            "initial_savings_allocated": cash,
            "existing_assets_allocated": asset,
            "monthly_savings_contribution": save,
            "monthly_investment_contribution": invest,
            "loan_principal": loan,
            "estimated_loan_emi": loan * emi_factor,
            "shortfall": short,
            "projected_new_funding": cash + asset * asset_factor + save * sf
            + invest * inv_factor + loan,
            "achievement_ratio": (min(1.0, (cash + asset * asset_factor + save * sf
                                            + invest * inv_factor + loan)
                                     / float(row.funding_gap))
                                  if float(row.funding_gap) else 1.0),
            "funding_gap": float(row.funding_gap),
            "time_horizon_months": months,
        })
    allocations = pd.DataFrame(records)
    savings_total = float(allocations["monthly_savings_contribution"].sum())
    investment_total = float(allocations["monthly_investment_contribution"].sum())
    loan_total = float(allocations["loan_principal"].sum())
    loan_emi_total = float(allocations["estimated_loan_emi"].sum())
    capacity_base = max(0.0, monthly_surplus - loan_emi_total)
    weighted_achievement = float(
        (allocations["achievement_ratio"] * g.goal_priority_score.to_numpy()).sum()
        / total_weight
    )
    return {
        "status": "optimal",
        "solver_message": result.message,
        "goals": g,
        "allocations": allocations,
        "objective": float(result.fun),
        "summary": {
            "status": "optimal",
            "objective_value": float(result.fun),
            "goal_count": n,
            "total_funding_gap": float(g.funding_gap.sum()),
            "total_projected_new_funding": float(allocations.projected_new_funding.sum()),
            "total_shortfall": float(allocations.shortfall.sum()),
            "weighted_goal_achievement": weighted_achievement,
            "monthly_surplus_available": monthly_surplus,
            "monthly_contributions_allocated": savings_total + investment_total,
            "monthly_savings_allocated": savings_total,
            "monthly_investment_allocated": investment_total,
            "emi_capacity": emi_cap,
            "new_total_emi": loan_emi_total,
            "investment_permitted": capacity_base * float(investment_capacity_ratio),
            "monthly_surplus_respected": bool(
                savings_total + investment_total <= monthly_surplus + 1e-5),
            "combined_monthly_cashflow_respected": bool(
                savings_total + investment_total + loan_emi_total <= monthly_surplus + 1e-5),
            "investment_capacity_respected": bool(
                investment_total <= capacity_base * float(investment_capacity_ratio) + 1e-5),
        },
        "constraints": {
            "monthly_surplus": monthly_surplus,
            "emi_cap": emi_cap,
            "emi_factor": emi_factor,
            "available_cash": available_cash,
            "usable_existing_assets": usable_existing_assets,
            "investment_capacity_ratio": float(investment_capacity_ratio),
            "investment_permitted": capacity_base * float(investment_capacity_ratio),
            "enforce_investment_capacity": bool(enforce_investment_capacity),
            "enforce_single_loan_limit": bool(enforce_single_loan_limit),
            "max_new_loan": float(max_new_loan),
            "savings_total": savings_total,
            "investment_total": investment_total,
            "loan_total": loan_total,
            "loan_emi_total": loan_emi_total,
            "contribution_total": savings_total + investment_total,
            "surplus_slack": monthly_surplus - (savings_total + investment_total + loan_emi_total),
            "emi_slack": emi_cap - loan_emi_total,
            "capacity_slack": capacity_base * float(investment_capacity_ratio) - investment_total,
            "total_shortfall": float(allocations["shortfall"].sum()),
            "goal_cap_violations": int((allocations["projected_new_funding"]
                                        > allocations["funding_gap"] + 1e-6).sum()),
        },
    }


def capacity_ratio_for(profile_row: pd.Series) -> float:
    """The environment's per-user investment capacity ratio."""
    return float(profile_row["investment_capacity_ratio"])


def allowed_monthly_investment(monthly_surplus: float, loan_emi_total: float,
                               investment_capacity_ratio: float) -> float:
    """The environment's investment ceiling: ``available x capacity``."""
    return max(0.0, monthly_surplus - loan_emi_total) * float(investment_capacity_ratio)


def numpy_conservation_report(solution: dict[str, Any]) -> dict[str, float]:
    """Budget/feasibility residuals, all of which must be >= -tolerance for a valid plan."""
    cons = solution["constraints"]
    return {
        "surplus_residual": cons["monthly_surplus"]
        - (cons["contribution_total"] + cons["loan_emi_total"]),
        "capacity_residual": cons["investment_permitted"] - cons["investment_total"],
        "emi_residual": cons["emi_cap"] - cons["loan_emi_total"],
        "nonnegative_allocations": float(np.min(solution["allocations"][[
            "initial_savings_allocated", "existing_assets_allocated",
            "monthly_savings_contribution", "monthly_investment_contribution",
            "loan_principal", "shortfall",
        ]].to_numpy())),
    }
