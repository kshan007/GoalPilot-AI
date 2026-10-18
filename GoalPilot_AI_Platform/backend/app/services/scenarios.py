"""Deterministic economic stress scenarios.

Every scenario is an **explicit assumption applied to the user's own numbers**, never a
generated market outcome. The baseline and the stressed case use the same assumption set
except for the parameters the scenario names, so the difference is attributable to the
shock alone.

Scenarios available (brief §14):
    expenses_up, income_down, unexpected_expense, higher_inflation, lower_returns,
    higher_lending_rates, improved_savings, delayed_goals
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from app.services.cashflow import CashFlow
from app.services.money import months_between, round_money


@dataclass(frozen=True)
class ScenarioPreset:
    preset: str
    name: str
    description: str
    parameters: dict[str, float]
    assumption_note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "preset": self.preset,
            "name": self.name,
            "description": self.description,
            "parameters": dict(self.parameters),
            "assumption_note": self.assumption_note,
        }


PRESETS: dict[str, ScenarioPreset] = {
    "expenses_up": ScenarioPreset(
        "expenses_up",
        "Essential expenses rise",
        "Essential monthly spending increases by the given percentage.",
        {"expense_increase_pct": 10.0},
        "Applied to the user's own recorded essential expenses, not to any market forecast.",
    ),
    "income_down": ScenarioPreset(
        "income_down",
        "Income falls",
        "Monthly income drops by the given percentage (e.g. a job change or reduced hours).",
        {"income_change_pct": -15.0},
        "A user-declared assumption; no labour-market forecast is used.",
    ),
    "unexpected_expense": ScenarioPreset(
        "unexpected_expense",
        "One-off unexpected expense",
        "A single lump sum is removed from liquid savings (medical, repair, relocation).",
        {"one_off_amount": 75_000.0},
        "Treated as a cash outflow today, not as recurring spending.",
    ),
    "higher_inflation": ScenarioPreset(
        "higher_inflation",
        "Higher inflation assumption",
        "The inflation assumption used to project goal costs is raised by the given points.",
        {"inflation_delta_pct": 2.0},
        "This is an assumption change, not a forecast of realised CPI.",
    ),
    "lower_returns": ScenarioPreset(
        "lower_returns",
        "Lower investment returns",
        "The investment-return assumption is reduced by the given percentage points.",
        {"investment_return_delta_pct": -2.0},
        "Historical returns are never presented as a guaranteed forward return.",
    ),
    "higher_lending_rates": ScenarioPreset(
        "higher_lending_rates",
        "Higher lending rates",
        "The loan-interest assumption is raised by the given percentage points.",
        {"loan_rate_delta_pct": 3.0},
        "The RBI weighted-average lending rate is not the rate available to any individual "
        "borrower; this is a stress assumption.",
    ),
    "improved_savings": ScenarioPreset(
        "improved_savings",
        "Improved savings capacity",
        "Discretionary spending falls, raising the monthly surplus.",
        {"discretionary_reduction_pct": 20.0},
        "A user-declared behaviour change, not a forecast.",
    ),
    "delayed_goals": ScenarioPreset(
        "delayed_goals",
        "Goals delayed by a year",
        "Every flexible goal's target date is pushed back by 12 months.",
        {"delay_months": 12.0},
        "Applied only to goals the user marked as date-flexible.",
    ),
}


def list_presets() -> list[dict[str, Any]]:
    return [p.as_dict() for p in PRESETS.values()]


def apply_to_cashflow(
    cashflow: CashFlow, preset: str, parameters: dict[str, float]
) -> tuple[CashFlow, dict[str, float], list[str]]:
    """Return a stressed copy of the cash flow, the assumption overrides, and a narrative."""
    if preset not in PRESETS:
        raise ValueError(f"Unknown scenario preset '{preset}'")
    params = {**PRESETS[preset].parameters, **(parameters or {})}
    narrative: list[str] = []
    overrides: dict[str, float] = {}

    stressed = CashFlow(**cashflow.as_dict())
    stressed.warnings = list(cashflow.warnings)

    if preset == "expenses_up":
        pct = float(params["expense_increase_pct"])
        delta = stressed.essential_expenses * pct / 100.0
        stressed.essential_expenses += delta
        narrative.append(
            f"Essential expenses rise {pct:+.1f}% ({delta:,.0f}/month)."
        )
    elif preset == "income_down":
        pct = float(params["income_change_pct"])
        delta = stressed.monthly_income * pct / 100.0
        stressed.monthly_income = max(0.0, stressed.monthly_income + delta)
        narrative.append(f"Monthly income changes {pct:+.1f}% ({delta:,.0f}/month).")
    elif preset == "unexpected_expense":
        amount = float(params["one_off_amount"])
        stressed.liquid_savings = max(0.0, stressed.liquid_savings - amount)
        narrative.append(f"A one-off expense of {amount:,.0f} is paid from liquid savings.")
    elif preset == "higher_inflation":
        delta = float(params["inflation_delta_pct"]) / 100.0
        overrides["annual_inflation"] = None  # filled by caller from profile + delta
        narrative.append(
            f"Goal-cost inflation assumption rises by {params['inflation_delta_pct']:+.1f} points."
        )
    elif preset == "lower_returns":
        narrative.append(
            f"Investment-return assumption falls by "
            f"{abs(params['investment_return_delta_pct']):.1f} points."
        )
    elif preset == "higher_lending_rates":
        narrative.append(
            f"Loan-interest assumption rises by {params['loan_rate_delta_pct']:+.1f} points."
        )
    elif preset == "improved_savings":
        pct = float(params["discretionary_reduction_pct"])
        delta = stressed.discretionary_expenses * pct / 100.0
        stressed.discretionary_expenses = max(0.0, stressed.discretionary_expenses - delta)
        narrative.append(f"Discretionary spending falls {pct:.1f}% ({delta:,.0f}/month freed).")
    elif preset == "delayed_goals":
        narrative.append(
            f"Flexible goals are delayed {params['delay_months']:.0f} months, reducing the "
            "required monthly contribution."
        )

    # recompute the derived fields the same way build_cashflow does
    stressed.monthly_surplus = (
        stressed.monthly_income
        - stressed.essential_expenses
        - stressed.discretionary_expenses
        - stressed.existing_emi
    )
    stressed.emergency_fund_target = stressed.emergency_months * stressed.essential_expenses
    stressed.emergency_fund_gap = max(
        0.0, stressed.emergency_fund_target - stressed.liquid_savings
    )
    stressed.emergency_fund_progress = (
        min(1.0, stressed.liquid_savings / stressed.emergency_fund_target)
        if stressed.emergency_fund_target > 0
        else 1.0
    )
    stressed.emi_income_ratio = (
        stressed.existing_emi / stressed.monthly_income if stressed.monthly_income > 0 else 0.0
    )
    stressed.available_cash_for_goals = max(
        0.0, stressed.liquid_savings - stressed.emergency_fund_target - stressed.earmarked_goal_funding
    )
    return stressed, params, narrative


def assumption_overrides(
    preset: str, parameters: dict[str, float], base: dict[str, float]
) -> dict[str, float]:
    """Assumption deltas implied by a scenario, given the baseline assumptions."""
    out = dict(base)
    if preset == "higher_inflation":
        out["annual_inflation"] = base.get("annual_inflation", 0.03) + (
            float(parameters.get("inflation_delta_pct", 2.0)) / 100.0
        )
    elif preset == "lower_returns":
        out["investment_return"] = max(
            -0.5,
            base.get("investment_return", 0.05)
            + float(parameters.get("investment_return_delta_pct", -2.0)) / 100.0,
        )
    elif preset == "higher_lending_rates":
        out["loan_annual_rate"] = base.get("loan_annual_rate", 0.12) + (
            float(parameters.get("loan_rate_delta_pct", 3.0)) / 100.0
        )
    return out


def delay_goals(goals: list[Any], months: int) -> dict[int, dt.date]:
    """New target dates for date-flexible goals. Returns goal_id -> new date."""
    out: dict[int, dt.date] = {}
    for goal in goals:
        if not getattr(goal, "date_flexible", False):
            continue
        year = goal.target_date.year + (goal.target_date.month - 1 + months) // 12
        month = (goal.target_date.month - 1 + months) % 12 + 1
        out[goal.id] = dt.date(year, month, min(goal.target_date.day, 28))
    return out


def diff_plans(baseline: dict[str, Any], stressed: dict[str, Any]) -> dict[str, Any]:
    """Quantified difference between a baseline plan and its stressed counterpart."""
    b_sum, s_sum = baseline.get("summary", {}), stressed.get("summary", {})
    keys = [
        "weighted_goal_achievement",
        "total_shortfall",
        "monthly_contributions_allocated",
        "monthly_savings_allocated",
        "monthly_investment_allocated",
        "new_total_emi",
    ]
    deltas: dict[str, Any] = {}
    for key in keys:
        b = b_sum.get(key)
        s = s_sum.get(key)
        if isinstance(b, (int, float)) and isinstance(s, (int, float)):
            deltas[key] = {"baseline": round(float(b), 2), "stressed": round(float(s), 2),
                           "delta": round(float(s) - float(b), 2)}
    b_cf, s_cf = baseline.get("cashflow", {}), stressed.get("cashflow", {})
    for key in ("monthly_surplus", "available_cash_for_goals", "emergency_fund_progress"):
        b = b_cf.get(key)
        s = s_cf.get(key)
        if isinstance(b, (int, float)) and isinstance(s, (int, float)):
            deltas[key] = {"baseline": round(float(b), 2), "stressed": round(float(s), 2),
                           "delta": round(float(s) - float(b), 2)}
    return deltas


def narrate(baseline: dict[str, Any], stressed: dict[str, Any], deltas: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    ach = deltas.get("weighted_goal_achievement")
    if ach:
        direction = "falls" if ach["delta"] < 0 else "rises"
        lines.append(
            f"Weighted goal achievement {direction} from {ach['baseline']:.4f} to "
            f"{ach['stressed']:.4f} ({ach['delta']:+.4f})."
        )
    sh = deltas.get("total_shortfall")
    if sh:
        direction = "widens" if sh["delta"] > 0 else "narrows"
        lines.append(
            f"Total unfunded shortfall {direction} from {sh['baseline']:,.0f} to "
            f"{sh['stressed']:,.0f} ({sh['delta']:+,.0f})."
        )
    sur = deltas.get("monthly_surplus")
    if sur:
        lines.append(
            f"Monthly surplus moves from {sur['baseline']:,.0f} to {sur['stressed']:,.0f}."
        )
    if not lines:
        lines.append(
            "The scenario did not change the plan materially on the modelled horizon."
        )
    stressed_status = stressed.get("status")
    if stressed_status and stressed_status != "optimal":
        lines.append(
            f"The stressed case returned status '{stressed_status}': the goal set is not "
            "fully fundable under this assumption set. Shortfalls are reported per goal."
        )
    return lines
