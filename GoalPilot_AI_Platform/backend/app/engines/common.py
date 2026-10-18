"""Shared result contract and plan validation used by every algorithm arm.

Every arm — LP, RL, hybrid, rule baseline — returns an :class:`ArmResult`. A plan is only
allowed to leave this layer carrying ``feasible=True`` if it passes
:func:`validate_plan`, which re-derives every mandatory conservation identity from the
allocations themselves. The RL and hybrid arms therefore *cannot* silently weaken a
financial constraint: a plan that violates one is rejected, not rounded.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

import pandas as pd

# Absolute tolerance for rupee identities. The research parity guarantee is 1e-12 on
# rewards; plans are validated an order of magnitude looser than that but far tighter than
# any material amount.
TOL = 1e-4

ALGORITHM_LP = "lp"
ALGORITHM_RL = "rl"
ALGORITHM_HYBRID = "hybrid"
ALGORITHM_RULE = "rule_baseline"

ALGORITHM_LABELS = {
    ALGORITHM_LP: "Capacity-constrained LP",
    ALGORITHM_RL: "Reinforcement learning (PPO)",
    ALGORITHM_HYBRID: "LP + RL hybrid",
    ALGORITHM_RULE: "Uniform savings rule (control)",
}

#: What the LP objective actually is. The value is a *penalty score*, not money: the shortfall
#: variables are weighted by each goal's normalized priority score, and financing/risk terms are
#: added. It is only meaningful relative to another solution of the same problem.
OBJECTIVE_DEFINITION = (
    "Priority-weighted shortfall penalty plus small financing and risk cost terms: "
    "sum_j(w_j * shortfall_j) + loan/interest cost + risk cost, where w_j is goal j's "
    "priority score divided by the total priority score. The weights sum to 1, so the value "
    "is a weighted rupee shortfall in the same units as the goal gaps, but it is a "
    "dimensionless optimisation score: it is NOT a cash amount, NOT an amount the user pays, "
    "and NOT comparable across different goal sets or assumption sets."
)

#: The comparison table uses one vocabulary for every arm. Each entry says what the number is,
#: how it is measured, and its unit — the previous flat metric dump made an LP *plan* figure
#: look directly comparable with an RL *credited average*, which they are not.
METRIC_DEFINITIONS = {
    "weighted_goal_achievement": (
        "Deadline achievement, weighted by each goal's priority score. Unit: ratio 0..1. "
        "Measured at each goal's own deadline on the shared monthly path."
    ),
    "pct_goals_met_by_deadline": (
        "Share of goals whose balance reaches the target on or before the target date. "
        "Unit: ratio 0..1."
    ),
    "total_shortfall": (
        "Sum of (target - balance at deadline) across goals, floored at zero. Unit: rupees, "
        "future value at each goal's deadline."
    ),
    "monthly_contribution_credited_avg": (
        "Average rupees per month the simulator actually credited to goal accounts over the "
        "episode, savings plus investment. It is a realised average, not the plan's monthly "
        "instruction: it falls below the instruction once a goal is fully funded and further "
        "contributions are capped."
    ),
    "monthly_contribution_planned": (
        "The plan's monthly savings + investment instruction for the current month, from the "
        "optimiser's allocation. Unit: rupees per month."
    ),
    "monthly_savings_credited_avg": "Average rupees per month credited through the savings channel.",
    "monthly_investment_credited_avg": (
        "Average rupees per month credited through the investment channel."
    ),
    "unallocated_budget_total": (
        "Cumulative monthly budget the policy/plan did not allocate to any goal. Unit: rupees "
        "over the episode. It stays in cash."
    ),
    "final_cash": (
        "Cash at the end of the episode. In ledger accounting this includes money earmarked to "
        "goals, because goal balances are a memo account and not a separate pot."
    ),
    "final_unearmarked_cash": "Cash at the end of the episode that is not earmarked to any goal.",
    "earmarked_goal_funding": "Memo total of goal balances; a subset of cash + portfolio.",
    "final_portfolio": "Invested portfolio value at the end of the episode.",
    "final_liabilities": "Outstanding loan balance at the end of the episode.",
    "net_worth": "cash + portfolio - loan balance. Goal balances are not added (memo subset).",
    "months_simulated": "Months replayed, from the first month to the last goal deadline.",
}



@dataclass
class ArmResult:
    algorithm: str
    status: str                      # optimal | infeasible | error | unavailable
    feasible: bool
    allocations: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    objective_value: float | None = None
    runtime_ms: int = 0
    model_version: str = ""
    config_version: str = ""
    warnings: list[str] = field(default_factory=list)
    fallback_reason: str | None = None
    label: str = ""

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["label"] = self.label or ALGORITHM_LABELS.get(self.algorithm, self.algorithm)
        return data


@dataclass
class PlanViolation:
    code: str
    detail: str
    amount: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_plan(
    allocations: pd.DataFrame,
    constraints: dict[str, Any],
    *,
    monthly_surplus: float,
    emi_cap: float,
    available_cash: float,
    usable_existing_assets: float,
    investment_permitted: float | None = None,
) -> list[PlanViolation]:
    """Re-derive every mandatory identity from the allocation table.

    Returns a (possibly empty) list of violations. An empty list is the only condition
    under which an arm may be reported feasible.
    """
    violations: list[PlanViolation] = []
    if allocations is None or allocations.empty:
        violations.append(
            PlanViolation("empty_plan", "The solver returned no allocations.", 0.0)
        )
        return violations

    def col(name: str) -> pd.Series:
        return allocations[name].astype(float) if name in allocations else pd.Series(dtype=float)

    money_cols = [
        "initial_savings_allocated",
        "existing_assets_allocated",
        "monthly_savings_contribution",
        "monthly_investment_contribution",
        "loan_principal",
        "shortfall",
    ]
    for name in money_cols:
        if name not in allocations:
            violations.append(
                PlanViolation("missing_column", f"Allocation column '{name}' is absent.", 0.0)
            )
            continue
        minimum = float(allocations[name].min())
        if minimum < -TOL:
            violations.append(
                PlanViolation(
                    "negative_allocation",
                    f"'{name}' contains a negative value ({minimum:.4f}).",
                    abs(minimum),
                )
            )

    cash_total = float(col("initial_savings_allocated").sum())
    if cash_total > available_cash + TOL:
        violations.append(
            PlanViolation(
                "cash_pool_exceeded",
                f"Initial savings allocated ({cash_total:,.2f}) exceeds the available "
                f"cash pool ({available_cash:,.2f}).",
                cash_total - available_cash,
            )
        )

    asset_total = float(col("existing_assets_allocated").sum())
    if asset_total > usable_existing_assets + TOL:
        violations.append(
            PlanViolation(
                "asset_pool_exceeded",
                f"Existing assets allocated ({asset_total:,.2f}) exceeds the usable pool "
                f"({usable_existing_assets:,.2f}).",
                asset_total - usable_existing_assets,
            )
        )

    contribution_total = float(
        (col("monthly_savings_contribution") + col("monthly_investment_contribution")).sum()
    )
    if contribution_total > monthly_surplus + TOL:
        violations.append(
            PlanViolation(
                "surplus_exceeded",
                f"Monthly contributions ({contribution_total:,.2f}) exceed the monthly "
                f"surplus ({monthly_surplus:,.2f}).",
                contribution_total - monthly_surplus,
            )
        )

    emi_total = float(col("estimated_loan_emi").sum()) if "estimated_loan_emi" in allocations else float(
        col("loan_principal").sum()
    )
    if emi_total > emi_cap + TOL:
        violations.append(
            PlanViolation(
                "emi_cap_exceeded",
                f"New loan EMIs ({emi_total:,.2f}) exceed the remaining EMI capacity "
                f"({emi_cap:,.2f}).",
                emi_total - emi_cap,
            )
        )

    if contribution_total + emi_total > monthly_surplus + TOL:
        violations.append(
            PlanViolation(
                "combined_affordability_exceeded",
                f"Contributions + new EMIs ({contribution_total + emi_total:,.2f}) exceed the "
                f"monthly surplus ({monthly_surplus:,.2f}).",
                contribution_total + emi_total - monthly_surplus,
            )
        )

    invest_total = float(col("monthly_investment_contribution").sum())
    if investment_permitted is not None and invest_total > investment_permitted + TOL:
        violations.append(
            PlanViolation(
                "investment_capacity_exceeded",
                f"Investment ({invest_total:,.2f}) exceeds the permitted capacity "
                f"({investment_permitted:,.2f}).",
                invest_total - investment_permitted,
            )
        )

    # No goal may be funded beyond its own gap — that would be double allocation.
    if {"projected_new_funding", "funding_gap"}.issubset(allocations.columns):
        over = allocations["projected_new_funding"].astype(float) - allocations["funding_gap"].astype(float)
        if float(over.max()) > 1e-6:
            worst = float(over.max())
            violations.append(
                PlanViolation(
                    "goal_overfunded",
                    f"A goal is funded beyond its gap by {worst:,.2f}. Allocations are being "
                    "double-counted.",
                    worst,
                )
            )
    return violations


def violation_summary(violations: list[PlanViolation]) -> dict[str, Any]:
    return {
        "count": len(violations),
        "violations": [v.as_dict() for v in violations],
        "clean": not violations,
    }


def allocations_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows) if rows else pd.DataFrame()
