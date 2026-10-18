"""Goal projection and feasibility.

Produces (a) the goal frame the research LP requires, and (b) the human-facing per-goal
projection table the brief asks for: current funding, future target, remaining gap,
required monthly contribution, planned contribution, feasibility, projected completion or
shortfall, and the assumptions/uncertainty attached to each number.

Goal cost projection (explicit and configurable — historical CPI is *not* used as a
forecast):

    future_nominal_cost = current_cost × (1 + inflation_assumption) ** (months / 12)
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, asdict
from typing import Any

import pandas as pd

from app.services.money import months_between

#: Columns the research `prepare_goals` requires, in the schema it validates.
REQUIRED_GOAL_COLUMNS = [
    "goal_id",
    "goal_name",
    "current_cost",
    "target_date",
    "time_horizon_months",
    "priority",
    "criticality",
    "existing_funding",
]


@dataclass
class GoalProjection:
    goal_ref: str
    goal_id: int | None
    name: str
    goal_type: str
    priority: int
    criticality: int
    target_date: str
    months_remaining: int
    current_cost: float
    future_target: float
    existing_funding: float
    remaining_gap: float
    required_monthly_contribution: float
    #: The monthly amount genuinely available for goals: surplus net of the protected buffer.
    #: Feasibility is judged against this, not against gross surplus.
    goal_budget: float
    planned_monthly_contribution: float | None
    projected_funding: float | None
    projected_shortfall: float | None
    achievement_ratio: float | None
    feasibility: str
    date_flexible: bool
    amount_flexible: bool
    inflation_assumption: float
    investment_return_assumption: float
    uncertainty: str
    notes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def goal_frame(goals: list[Any], inflation: float, *, today: dt.date | None = None) -> pd.DataFrame:
    """Build the DataFrame the research LP expects.

    ``goal_id`` is the solver-side identifier and is namespaced with the DB primary key so
    it is unique even if two goals share a name. ``target_date`` is an ISO string, which is
    what the research ``prepare_goals`` parses.
    """
    today = today or dt.date.today()
    rows: list[dict[str, Any]] = []
    for g in goals:
        months = max(1, months_between(today, g.target_date))
        rows.append(
            {
                "goal_id": f"G{g.id}",
                "db_goal_id": g.id,
                "goal_name": g.name,
                "current_cost": float(g.current_cost),
                "target_date": g.target_date.isoformat(),
                "time_horizon_months": int(months),
                "priority": int(g.priority),
                "criticality": int(g.criticality),
                "existing_funding": float(g.current_funded_amount),
            }
        )
    df = pd.DataFrame(rows, columns=REQUIRED_GOAL_COLUMNS + ["db_goal_id"])
    if inflation != 0.0 and not df.empty:
        # `prepare_goals` applies inflation itself; we keep the raw cost here so there is
        # exactly one place that applies it.
        pass
    return df


def _future_value_factor(annual_return: float, months: int) -> float:
    """FV at deadline of ₹1 contributed at each month end."""
    if months <= 0:
        return 0.0
    r = (1 + annual_return) ** (1 / 12) - 1
    if abs(r) < 1e-12:
        return float(months)
    return ((1 + r) ** months - 1) / r


def project_goals(
    goals: list[Any],
    *,
    inflation: float,
    savings_return: float,
    investment_return: float,
    monthly_surplus: float,
    available_cash: float,
    goal_budget: float | None = None,
    allocations: pd.DataFrame | None = None,
    today: dt.date | None = None,
) -> list[GoalProjection]:
    """Per-goal projection table.

    ``allocations`` is the LP output when a plan exists. Without it, ``planned_*`` fields
    are ``None`` — the platform never invents a plan to fill a table.

    ``goal_budget`` is the amount available for goals after the protected buffer. When it is
    omitted it falls back to ``monthly_surplus``, which is what every caller did before the
    distinction was introduced; that fallback is why a goal could be labelled "feasible"
    while the buffer had already claimed the money it needed.
    """
    today = today or dt.date.today()
    budget = float(goal_budget) if goal_budget is not None else float(monthly_surplus)
    alloc_by_ref: dict[str, Any] = {}
    if allocations is not None and not allocations.empty:
        # Index by BOTH identifiers. The persisted frame carries `goal_id` (an int) while the
        # plan payload carries `goal_ref` ("G<id>"); looking up only one of them silently
        # matched nothing, so every goal was reported as unplanned even when the optimiser had
        # allocated money to it.
        for _, row in allocations.iterrows():
            goal_id = row.get("goal_id")
            if goal_id is not None and not (isinstance(goal_id, float) and pd.isna(goal_id)):
                alloc_by_ref[str(goal_id)] = row
            goal_ref = row.get("goal_ref")
            if isinstance(goal_ref, str) and goal_ref:
                alloc_by_ref[goal_ref] = row

    total_gap = 0.0
    prepared: list[dict[str, Any]] = []
    for g in goals:
        months = max(1, months_between(today, g.target_date))
        future_target = float(g.current_cost) * (1 + inflation) ** (months / 12)
        gap = max(0.0, future_target - float(g.current_funded_amount))
        total_gap += gap
        prepared.append(
            {
                "goal": g,
                "months": months,
                "future_target": future_target,
                "gap": gap,
            }
        )

    projections: list[GoalProjection] = []
    for item in prepared:
        g = item["goal"]
        months = item["months"]
        future_target = item["future_target"]
        gap = item["gap"]
        required = gap / months if months else gap

        # Share of the goal budget the goal would need if funded purely from monthly cash flow.
        share_of_surplus = required / budget if budget > 0 else float("inf")

        # Explicit None checks: `a or b` would evaluate the truthiness of a pandas Series and
        # raise "The truth value of a Series is ambiguous".
        alloc = alloc_by_ref.get(str(g.id))
        if alloc is None:
            alloc = alloc_by_ref.get(f"G{g.id}")
        planned = None
        projected = None
        shortfall = None
        achievement = None
        if alloc is not None:
            planned = float(alloc["monthly_savings_contribution"]) + float(
                alloc["monthly_investment_contribution"]
            )
            projected = float(alloc["projected_new_funding"]) + float(g.current_funded_amount)
            shortfall = float(alloc["shortfall"])
            achievement = float(alloc["achievement_ratio"])

        notes: list[str] = []
        # Feasibility is a statement about the arithmetic, not about the person.
        if gap <= 0:
            feasibility = "funded"
            notes.append("Already fully funded at today's projected cost.")
        elif budget <= 0:
            feasibility = "infeasible"
            notes.append(
                "There is no money available for goals this month: essential expenses, debt "
                "obligations and the protected savings buffer consume the whole surplus."
            )
        elif required > budget:
            feasibility = "infeasible_on_current_cashflow"
            notes.append(
                f"The goal needs {required:,.0f}/month but only {budget:,.0f}/month is "
                f"available for goals after the protected buffer"
                + (
                    f" (gross surplus is {monthly_surplus:,.0f})."
                    if abs(monthly_surplus - budget) > 0.005
                    else "."
                )
            )
        elif share_of_surplus > 0.5:
            feasibility = "at_risk"
            notes.append(
                f"This single goal would consume {share_of_surplus:.0%} of the money available "
                "for goals, leaving little capacity for the others or for shocks."
            )
        else:
            feasibility = "feasible"

        if shortfall is not None and shortfall > 1e-6:
            notes.append(
                f"After optimised allocation a shortfall of {shortfall:,.0f} remains; the goal is "
                "not projected to be met in full by the target date."
            )
        if g.date_flexible is False and feasibility in ("infeasible_on_current_cashflow", "at_risk"):
            notes.append("The target date is marked inflexible, so extending it is not offered.")
        if g.amount_flexible is False and feasibility == "infeasible_on_current_cashflow":
            notes.append("The target amount is marked inflexible, so reducing it is not offered.")

        uncertainty = (
            "high" if months > 60 or g.amount_flexible else "medium" if months > 24 else "low"
        )

        projections.append(
            GoalProjection(
                goal_ref=f"G{g.id}",
                goal_id=g.id,
                name=g.name,
                goal_type=g.goal_type,
                priority=int(g.priority),
                criticality=int(g.criticality),
                target_date=g.target_date.isoformat(),
                months_remaining=int(months),
                current_cost=float(g.current_cost),
                future_target=future_target,
                existing_funding=float(g.current_funded_amount),
                remaining_gap=gap,
                required_monthly_contribution=required,
                goal_budget=budget,
                planned_monthly_contribution=planned,
                projected_funding=projected,
                projected_shortfall=shortfall,
                achievement_ratio=achievement,
                feasibility=feasibility,
                date_flexible=bool(g.date_flexible),
                amount_flexible=bool(g.amount_flexible),
                inflation_assumption=inflation,
                investment_return_assumption=investment_return,
                uncertainty=uncertainty,
                notes=notes,
            )
        )
    return projections


def suggest_alternatives(
    projection: GoalProjection,
    *,
    monthly_surplus: float,
    available_cash: float,
    emergency_months: float,
    monthly_income: float = 0.0,
    existing_emi: float = 0.0,
    emi_income_ratio_cap: float = 0.35,
    loan_annual_rate: float = 0.12,
    loan_tenure_months: int = 60,
    max_loan_per_goal: float = 150_000.0,
    max_new_loan: float = 150_000.0,
    allow_financing: bool = True,
    investment_return: float = 0.05,
) -> list[dict[str, Any]]:
    """Realistic, bounded options for an at-risk or infeasible goal.

    Each option states what it would require. None of them is applied automatically and
    none of them promises achievement. Every figure is arithmetic from the projection and the
    configured assumptions: no product, lender or return is recommended.

    The financing and investment routes are quantified rather than described, because a user
    whose surplus cannot reach the target needs to know *how far off* a loan or an investment
    plan would be — a bare "financing" row told them nothing.
    """
    options: list[dict[str, Any]] = []
    months = max(1, projection.months_remaining)
    gap = projection.remaining_gap

    if gap <= 0:
        return options

    if monthly_surplus > projection.required_monthly_contribution:
        options.append(
            {
                "option": "increase_contribution",
                "affordable": True,
                "detail": (
                    f"Increase the monthly contribution to "
                    f"{projection.required_monthly_contribution:,.0f}; the surplus can absorb it."
                ),
            }
        )
    elif monthly_surplus > 0:
        options.append(
            {
                "option": "increase_contribution",
                "affordable": False,
                "detail": (
                    f"The full required contribution of "
                    f"{projection.required_monthly_contribution:,.0f}/month exceeds the "
                    f"{monthly_surplus:,.0f}/month surplus."
                ),
            }
        )

    if projection.date_flexible:
        for extra_years in (1, 2, 3):
            new_months = months + extra_years * 12
            reduced = gap / new_months
            options.append(
                {
                    "option": f"extend_deadline_{extra_years}y",
                    "affordable": True,
                    "detail": (
                        f"Extending the deadline by {extra_years} year(s) reduces the required "
                        f"contribution to {reduced:,.0f}/month."
                    ),
                }
            )

    if projection.amount_flexible:
        options.append(
            {
                "option": "reduce_target",
                "affordable": True,
                "detail": (
                    f"Reducing the target to {max(0.0, projection.existing_funding + monthly_surplus * months):,.0f} "
                    "would match what the current surplus can fund by the deadline."
                ),
            }
        )

    free_cash = max(0.0, available_cash)
    if free_cash > 0:
        options.append(
            {
                "option": "use_existing_savings",
                "affordable": True,
                "detail": (
                    f"Up to {free_cash:,.0f} of cash above the {emergency_months:g}-month "
                    "emergency guideline is available to allocate."
                ),
            }
        )

    # --- Investment route -----------------------------------------------------------------
    # Compounding only helps when there is time for it. With a month or two left, the honest
    # answer is that market returns cannot close the gap, so the row says so instead of
    # implying an investment product would.
    monthly_rate = (1.0 + investment_return) ** (1.0 / 12.0) - 1.0
    if months >= 3 and monthly_rate > 0:
        growth = (1.0 + monthly_rate) ** months - 1.0
        invested_monthly = gap * monthly_rate / growth
        saving_vs_cash = projection.required_monthly_contribution - invested_monthly
        affordable = monthly_surplus >= invested_monthly
        options.append(
            {
                "option": "invest_for_goal",
                "affordable": affordable,
                "detail": (
                    f"Saving through a {investment_return:.1%}/year investment instead of cash "
                    f"would need {invested_monthly:,.0f}/month for {months} month(s), "
                    f"{max(0.0, saving_vs_cash):,.0f}/month less than the {projection.required_monthly_contribution:,.0f} "
                    "a cash-only plan needs"
                    + (
                        "; your surplus can absorb that."
                        if affordable
                        else f"; your surplus of {monthly_surplus:,.0f}/month cannot."
                    )
                    + " Returns are not guaranteed and can be negative over a short horizon."
                ),
            }
        )
    else:
        options.append(
            {
                "option": "invest_for_goal",
                "affordable": False,
                "detail": (
                    f"Investing cannot close this gap: only {months} month(s) remain, so the money "
                    "has to come from existing cash, higher contributions or borrowing. Market "
                    "returns over a horizon this short are uncertain and can be negative."
                ),
            }
        )

    # --- Financing route ------------------------------------------------------------------
    # Quantified with the configured rate, tenure and EMI ceiling. The principal is capped by
    # what the goal still needs and by the single-loan / total-new-loan limits the planner uses.
    if not allow_financing:
        options.append(
            {
                "option": "financing",
                "affordable": False,
                "detail": (
                    "Financing is switched off for this plan, so no loan is proposed. Enable "
                    "'Allow financing' on the Optimise page to let the planner consider one "
                    "within your EMI ceiling. A loan raises the total cost of the goal through "
                    "interest and is never used to make a goal merely look funded."
                ),
            }
        )
    elif loan_tenure_months >= 1 and gap > 0:
        loan_amount = min(gap, max(0.0, max_loan_per_goal), max(0.0, max_new_loan))
        if loan_amount <= 0:
            options.append(
                {
                    "option": "financing",
                    "affordable": False,
                    "detail": (
                        "The configured loan limits are zero, so no borrowing can be proposed "
                        "for this goal."
                    ),
                }
            )
        else:
            loan_monthly_rate = loan_annual_rate / 12.0
            if loan_monthly_rate > 0:
                emi = (
                    loan_amount
                    * loan_monthly_rate
                    / (1.0 - (1.0 + loan_monthly_rate) ** (-loan_tenure_months))
                )
            else:
                emi = loan_amount / loan_tenure_months
            emi_ceiling = max(0.0, monthly_income * emi_income_ratio_cap - existing_emi)
            total_interest = max(0.0, emi * loan_tenure_months - loan_amount)
            fits_ceiling = emi <= emi_ceiling + 1e-6
            fits_surplus = emi <= monthly_surplus + 1e-6
            affordable = bool(fits_ceiling and fits_surplus)
            remaining = max(0.0, gap - loan_amount)
            options.append(
                {
                    "option": "financing",
                    "affordable": affordable,
                    "detail": (
                        f"Borrowing {loan_amount:,.0f} at {loan_annual_rate:.1%}/year over "
                        f"{loan_tenure_months} months costs {emi:,.0f}/month in EMI and "
                        f"{total_interest:,.0f} in interest over the term. "
                        f"That EMI uses {emi:,.0f} of your {emi_ceiling:,.0f}/month EMI room "
                        f"({emi_income_ratio_cap:.0%} of income minus existing EMIs)"
                        + (" and fits within your surplus. " if fits_surplus else " and exceeds your surplus. ")
                        + (
                            "It covers the whole gap."
                            if remaining <= 1e-6
                            else f"{remaining:,.0f} would still have to come from your side."
                        )
                        + " No loan is applied for on your behalf."
                    ),
                }
            )

    options.append(
        {
            "option": "reprioritise",
            "affordable": True,
            "detail": (
                "The optimiser already tries to prioritise by weight; lowering this goal's "
                "priority or criticality will change how the shortfall is distributed."
            ),
        }
    )
    return options
