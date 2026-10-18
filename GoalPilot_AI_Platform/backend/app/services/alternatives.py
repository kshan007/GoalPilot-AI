"""What would each alternative actually achieve for *this* plan?

The goal page already lists arithmetic routes for a single infeasible goal. A plan needs the same
evidence across the whole goal set, so this module re-solves the plan's own constraint set with
exactly one change at a time — a later deadline, a smaller target, or financing switched on — and
reports what that change would do to funding and shortfall.

Honesty rules
-------------
* A relaxation is **never applied** to the user's goals. It is reported with its numbers and left
  for them to adopt or reject (``applied_to_plan`` is always false).
* The trained RL policy is **not** replayed on an altered framing: the checkpoint was trained on
  the fixed goal set, and rolling it out on a different horizon would be out of distribution and
  would look like evidence it is not. For the ``rl`` and ``hybrid`` arms the figures therefore come
  from the LP constraint set (the same solver and assumptions the hybrid's LP stage uses), and
  every row says so in ``evaluated_with``.
"""
from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from app.engines import lp_engine

#: Re-solving is cheap but not free; keep a plan's evaluation bounded and predictable.
MAX_GOALS_EVALUATED = 3
MAX_CANDIDATES = 8

_EVALUATOR_BY_ALGORITHM = {
    "lp": "the same constrained LP that produced this plan",
    "lp_unconstrained": "the constrained LP with this plan's assumptions",
    "rl": (
        "the LP constraint set with this plan's assumptions — the trained policy is not replayed "
        "on an altered framing"
    ),
    "hybrid": (
        "the hybrid's own LP stage — the RL stage is not replayed on an altered framing"
    ),
}


def _add_months(value: dt.date, months: int) -> dt.date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def _goal_view(goal: Any, *, months_delta: int = 0, target: float | None = None) -> SimpleNamespace:
    """A detached copy of the goal the solver can consume without touching the ORM object."""
    return SimpleNamespace(
        id=goal.id,
        name=goal.name,
        goal_type=getattr(goal, "goal_type", ""),
        current_cost=float(goal.current_cost if target is None else target),
        current_funded_amount=float(goal.current_funded_amount),
        target_date=_add_months(goal.target_date, months_delta),
        priority=int(goal.priority),
        criticality=int(goal.criticality),
        date_flexible=bool(getattr(goal, "date_flexible", True)),
        amount_flexible=bool(getattr(goal, "amount_flexible", True)),
    )


def _solve(goals: list[Any], cashflow: Any, assumptions: lp_engine.LpAssumptions):
    return lp_engine.solve(
        goals=goals, cashflow=cashflow, assumptions=assumptions, constrained=True
    )


def _row_goal_id(row: dict[str, Any]) -> int | None:
    """The DB goal id behind an allocation row, whichever identifier the arm used.

    The LP labels rows with ``db_goal_id``; the RL arm only carries ``goal_ref`` such as ``"G3"``.
    Treating a missing key as 0 silently matched nothing, which is why RL plans reported no
    alternatives at all.
    """
    raw = row.get("db_goal_id")
    if raw is None:
        raw = row.get("goal_id")
    if raw is None:
        raw = row.get("goal_ref")
    if isinstance(raw, (int,)) and not isinstance(raw, bool):
        return int(raw)
    text = str(raw or "").strip()
    if text[:1].upper() == "G" and text[1:].isdigit():
        return int(text[1:])
    if text.isdigit():
        return int(text)
    return None


def _row_future_cost(row: dict[str, Any]) -> float:
    for key in ("future_goal_cost", "future_cost", "future_target", "target", "target_amount"):
        if row.get(key) is not None:
            return float(row[key] or 0)
    return 0.0


def _row_shortfall(row: dict[str, Any]) -> float:
    if row.get("shortfall") is not None:
        return float(row["shortfall"] or 0)
    funded = row.get("projected_new_funding")
    if funded is None:
        funded = row.get("funded")
    return max(0.0, _row_future_cost(row) - float(funded or 0))


def _row_for(allocations: list[dict[str, Any]], goal_id: int) -> dict[str, Any] | None:
    for row in allocations:
        if _row_goal_id(row) == int(goal_id):
            return row
    return None


def _outcome(
    *,
    option: str,
    change: str,
    goal: Any | None,
    allocations: list[dict[str, Any]],
    goal_id: int | None,
    algorithm: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = _row_for(allocations, goal_id) if goal_id is not None else None
    shortfall = _row_shortfall(row) if row else 0.0
    achievement = float(row.get("achievement_ratio") or 0) if row else 0.0
    required = (
        float(row.get("monthly_savings_contribution") or 0)
        + float(row.get("monthly_investment_contribution") or 0)
        if row
        else 0.0
    )
    future_cost = _row_future_cost(row) if row else 0.0
    feasible = bool(row is not None and shortfall <= max(1.0, 0.001 * future_cost))
    payload: dict[str, Any] = {
        "option": option,
        "goal_ref": f"G{goal_id}" if goal_id is not None else "",
        "goal_name": getattr(goal, "name", "") if goal is not None else "",
        "change": change,
        "feasible": feasible,
        "achievement_ratio": round(achievement, 4),
        "required_monthly": round(required, 2),
        "shortfall_after": round(shortfall, 2),
        "loan_amount": None,
        "emi": None,
        "extra_interest": None,
        "detail": "",
        "evaluated_with": _EVALUATOR_BY_ALGORITHM.get(
            algorithm, "the constrained LP with this plan's assumptions"
        ),
        "applied_to_plan": False,
    }
    if extra:
        payload.update(extra)
    if feasible:
        payload["detail"] = (
            f"{change} meets this goal at {required:,.0f}/month under the plan's constraints."
        )
    elif row is not None:
        payload["detail"] = (
            f"{change} still leaves {shortfall:,.0f} short "
            f"({achievement:.0%} funded) at {required:,.0f}/month."
        )
    else:
        payload["detail"] = f"{change} did not produce an allocation for this goal."
    return payload


def evaluate(
    *,
    goals: list[Any],
    cashflow: Any,
    assumptions: lp_engine.LpAssumptions,
    allocations: list[dict[str, Any]],
    algorithm: str,
    max_candidates: int = MAX_CANDIDATES,
) -> list[dict[str, Any]]:
    """One change at a time, re-solved, with the resulting numbers.

    Returns an empty list when every goal is already funded (nothing to evaluate) or when the
    solver cannot be reached — the caller decides how to disclose that.
    """
    underfunded: list[tuple[Any, dict[str, Any]]] = []
    for goal in goals:
        row = _row_for(allocations, goal.id)
        if row is None:
            continue
        future_cost = _row_future_cost(row)
        shortfall = _row_shortfall(row)
        if shortfall > max(1.0, 0.001 * future_cost):
            underfunded.append((goal, row))

    if not underfunded:
        return []

    results: list[dict[str, Any]] = []

    def add(candidate: dict[str, Any]) -> None:
        if len(results) < max_candidates:
            results.append(candidate)

    for goal, row in underfunded[:MAX_GOALS_EVALUATED]:
        # --- later deadline -------------------------------------------------------------
        if getattr(goal, "date_flexible", True):
            for extra_months in (12, 24):
                variant = _goal_view(goal, months_delta=extra_months)
                variant_goals = [variant if g.id == goal.id else g for g in goals]
                try:
                    arm = _solve(variant_goals, cashflow, assumptions)
                except Exception:  # noqa: BLE001 - a failed variant must not fail the plan
                    continue
                new_date = variant.target_date.strftime("%d %b %Y")
                add(
                    _outcome(
                        option=f"extend_deadline_{extra_months}m",
                        change=f"Move the target date to {new_date} (+{extra_months} months)",
                        goal=goal,
                        allocations=arm.allocations,
                        goal_id=goal.id,
                        algorithm=algorithm,
                    )
                )

        # --- smaller target ------------------------------------------------------------
        if getattr(goal, "amount_flexible", True):
            affordable = float(row.get("projected_new_funding") or row.get("funded") or 0)
            future_cost = _row_future_cost(row)
            if 0 < affordable < future_cost:
                # Re-solve with the target set to the goal's current cost basis that this plan
                # can actually fund, so the reported funding is not just the old projection.
                scale = affordable / future_cost if future_cost else 1.0
                variant = _goal_view(goal, target=float(goal.current_cost) * scale)
                variant_goals = [variant if g.id == goal.id else g for g in goals]
                try:
                    arm = _solve(variant_goals, cashflow, assumptions)
                except Exception:  # noqa: BLE001
                    continue
                add(
                    _outcome(
                        option="reduce_target",
                        change=f"Set the target to about {affordable:,.0f} (what this plan can fund)",
                        goal=goal,
                        allocations=arm.allocations,
                        goal_id=goal.id,
                        algorithm=algorithm,
                    )
                )

    # --- financing --------------------------------------------------------------------
    # Evaluated whenever the plan proposed no loan, whatever the reason: the user may have
    # switched financing off, or the hybrid's RL stage may have removed it. A no-op variant (the
    # solver would still not borrow) is dropped rather than shown as an option.
    loan_total = sum(float(row.get("loan_principal") or 0) for row in allocations)
    if loan_total <= 0.01 and float(getattr(assumptions, "max_new_loan", 0) or 0) > 0:
        try:
            arm = _solve(goals, cashflow, replace(assumptions, allow_financing=True))
        except Exception:  # noqa: BLE001
            arm = None
        if arm is not None:
            shortfall_before = sum(_row_shortfall(r) for r in allocations)
            shortfall_after = sum(float(r.get("shortfall") or 0) for r in arm.allocations)
            loan = sum(float(r.get("loan_principal") or 0) for r in arm.allocations)
            emi = sum(float(r.get("estimated_loan_emi") or 0) for r in arm.allocations)
            interest = sum(
                float(r.get("estimated_loan_interest_cost") or 0) for r in arm.allocations
            )
            if interest <= 0 and loan > 0 and emi > 0:
                # The constrained solver reports principal and EMI but not total interest.
                tenure = int(getattr(assumptions, "loan_tenure_months", 60) or 60)
                interest = max(0.0, emi * tenure - loan)
            improved = shortfall_after < shortfall_before - 1.0
            if improved:
                add(
                    {
                    "option": "enable_financing",
                    "goal_ref": "all",
                    "goal_name": "Whole plan",
                    "change": "Allow financing, which this plan did not use",
                    "feasible": shortfall_after <= max(1.0, 0.001 * sum(
                        _row_future_cost(r) for r in allocations
                    )),
                    "achievement_ratio": None,
                    "required_monthly": round(
                        sum(
                            float(r.get("monthly_savings_contribution") or 0)
                            + float(r.get("monthly_investment_contribution") or 0)
                            for r in arm.allocations
                        ),
                        2,
                    ),
                    "shortfall_after": round(shortfall_after, 2),
                    "loan_amount": round(loan, 2),
                    "emi": round(emi, 2),
                    "extra_interest": round(interest, 2),
                    "detail": (
                        f"With financing enabled the plan borrows {loan:,.0f} at an EMI of "
                        f"{emi:,.0f}/month and {interest:,.0f} of interest over the term, cutting "
                        f"total shortfall from {shortfall_before:,.0f} to {shortfall_after:,.0f}. "
                        "No loan is applied for on your behalf."
                    ),
                    "evaluated_with": _EVALUATOR_BY_ALGORITHM.get(
                        algorithm, "the constrained LP with this plan's assumptions"
                    ),
                    "applied_to_plan": False,
                }
            )

    return results


def summary_note(alternatives: list[dict[str, Any]], algorithm: str) -> str | None:
    """One line for the plan's warnings list, or None when there is nothing to say."""
    if not alternatives:
        return None
    workable = [a for a in alternatives if a.get("feasible")]
    if not workable:
        return (
            f"{len(alternatives)} alternative(s) were evaluated for the underfunded goals and none "
            "of them closes the gap under the current constraints."
        )
    names = ", ".join(sorted({str(a.get("option", "")).replace("_", " ") for a in workable}))
    note = (
        f"{len(workable)} alternative(s) would meet the underfunded goals under the plan's own "
        f"constraints: {names}. They are reported only — nothing is applied to your goals."
    )
    if algorithm in ("rl", "hybrid"):
        note += (
            " For this arm the alternatives are measured on the LP constraint set; the trained "
            "policy is not replayed on an altered framing."
        )
    return note
