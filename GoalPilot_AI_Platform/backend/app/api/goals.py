"""Goal management and per-goal projection."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import current_user, owned_or_404
from app.core.errors import ValidationFailure
from app.db import get_db
from app.models import Goal, GoalAllocation, GoalContribution, OptimizationRun, User
from app.schemas.common import MessageResponse
from app.schemas.finance import (
    ContributionIn,
    ContributionOut,
    GoalIn,
    GoalOut,
    GoalProjectionOut,
    GoalUpdate,
)
from app.services.cashflow import CashFlow
from app.services.goals import project_goals, suggest_alternatives
from app.services.money import money_float, round_money
from app.services.planner import load_cashflow, load_goals, get_profile_or_none

router = APIRouter(prefix="/goals", tags=["goals"])
settings = get_settings()


def _latest_plan_allocations(db: Session, user_id: int):
    """The most recent plan's per-goal allocation, shaped for ``project_goals``.

    Returns ``None`` when no plan has been run, so the projection honestly reports null
    ``planned_*`` fields rather than a fabricated plan.
    """
    run = db.execute(
        select(OptimizationRun)
        .where(OptimizationRun.user_id == user_id, OptimizationRun.kind == "plan")
        .order_by(OptimizationRun.created_at.desc(), OptimizationRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if run is None:
        return None

    rows = list(
        db.execute(
            select(GoalAllocation).where(GoalAllocation.optimization_run_id == run.id)
        ).scalars()
    )
    if not rows:
        return None

    import pandas as pd

    frame = pd.DataFrame(
        [
            {
                "goal_id": r.goal_ref,
                "monthly_savings_contribution": float(r.monthly_savings_contribution),
                "monthly_investment_contribution": float(r.monthly_investment_contribution),
                "projected_new_funding": float(r.projected_new_funding),
                "shortfall": float(r.shortfall),
                "achievement_ratio": float(r.achievement_ratio),
            }
            for r in rows
        ]
    )
    frame.attrs["run_id"] = run.id
    return frame


def _goal_out(goal: Goal) -> GoalOut:
    return GoalOut(
        id=goal.id,
        name=goal.name,
        purpose=goal.purpose,
        goal_type=goal.goal_type,
        current_cost=money_float(goal.current_cost),
        target_date=goal.target_date,
        current_funded_amount=money_float(goal.current_funded_amount),
        priority=goal.priority,
        criticality=goal.criticality,
        date_flexible=goal.date_flexible,
        amount_flexible=goal.amount_flexible,
        liquidity_requirement=goal.liquidity_requirement,
        risk_constraint=float(goal.risk_constraint),
        status=goal.status,
        created_at=goal.created_at,
    )


@router.get("", response_model=list[GoalOut])
def list_goals(
    include_inactive: bool = Query(default=True),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return [_goal_out(g) for g in load_goals(db, user.id, include_inactive=include_inactive)]


@router.post("", response_model=GoalOut, status_code=201)
def create_goal(payload: GoalIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    goal = Goal(
        user_id=user.id,
        name=payload.name.strip(),
        purpose=payload.purpose,
        goal_type=payload.goal_type,
        current_cost=round_money(payload.current_cost),
        target_date=payload.target_date,
        current_funded_amount=round_money(payload.current_funded_amount),
        priority=payload.priority,
        criticality=payload.criticality,
        date_flexible=payload.date_flexible,
        amount_flexible=payload.amount_flexible,
        liquidity_requirement=payload.liquidity_requirement,
        risk_constraint=payload.risk_constraint,
        status=payload.status,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _goal_out(goal)


@router.get("/plan", response_model=list[GoalProjectionOut])
def goal_plan(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Per-goal projection without running an optimiser.

    Every figure comes from the arithmetic defined in the data dictionary; no plan is
    invented, so ``planned_monthly_contribution`` is null until an optimisation run exists.
    """
    goals = load_goals(db, user.id)
    if not goals:
        return []
    profile = get_profile_or_none(db, user.id)
    try:
        cf = load_cashflow(db, user.id)
    except ValidationFailure:
        cf = CashFlow()
    inflation = float(profile.inflation_assumption) if profile else 0.03
    investment_return = float(profile.investment_return_assumption) if profile else 0.05
    savings_return = float(profile.savings_return_assumption) if profile else 0.0

    projections = project_goals(
        goals,
        inflation=inflation,
        savings_return=savings_return,
        investment_return=investment_return,
        monthly_surplus=max(0.0, cf.monthly_surplus),
        goal_budget=max(0.0, cf.available_goal_budget),
        available_cash=cf.available_cash_for_goals,
    )
    out = []
    for p in projections:
        out.append(GoalProjectionOut(**p.as_dict()))
    return out


@router.get("/{goal_id}", response_model=GoalOut)
def read_goal(goal_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _goal_out(owned_or_404(db, Goal, user, goal_id))


@router.get("/{goal_id}/detail")
def goal_detail(goal_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    goal = owned_or_404(db, Goal, user, goal_id)
    profile = get_profile_or_none(db, user.id)
    try:
        cf = load_cashflow(db, user.id)
    except ValidationFailure:
        cf = CashFlow()
    inflation = float(profile.inflation_assumption) if profile else 0.03
    investment_return = float(profile.investment_return_assumption) if profile else 0.05
    # Attach the most recent plan's allocation for this goal. Without it the projection's
    # `planned_*` fields are null (correctly — no plan means no plan), but the page then told
    # the user "No optimisation run exists yet" even immediately after running one.
    latest_allocations = _latest_plan_allocations(db, user.id)

    projections = project_goals(
        [goal],
        inflation=inflation,
        savings_return=float(profile.savings_return_assumption) if profile else 0.0,
        investment_return=investment_return,
        monthly_surplus=max(0.0, cf.monthly_surplus),
        goal_budget=max(0.0, cf.available_goal_budget),
        available_cash=cf.available_cash_for_goals,
        allocations=latest_allocations,
    )
    projection = projections[0]
    alternatives = suggest_alternatives(
        projection,
        monthly_surplus=max(0.0, cf.monthly_surplus),
        available_cash=cf.available_cash_for_goals,
        emergency_months=cf.emergency_months,
        monthly_income=cf.monthly_income,
        existing_emi=cf.existing_emi,
        emi_income_ratio_cap=cf.emi_income_ratio_cap,
        loan_annual_rate=(
            float(profile.loan_interest_assumption) if profile else settings.default_loan_annual_rate
        ),
        loan_tenure_months=settings.default_loan_tenure_months,
        investment_return=investment_return,
    )
    contributions = db.execute(
        select(GoalContribution)
        .where(GoalContribution.goal_id == goal.id, GoalContribution.user_id == user.id)
        .order_by(GoalContribution.contribution_date.desc())
    ).scalars()
    return {
        "goal": _goal_out(goal),
        "projection": projection.as_dict(),
        "alternatives": alternatives,
        "contributions": [
            ContributionOut(
                id=c.id,
                goal_id=c.goal_id,
                amount=money_float(c.amount),
                contribution_date=c.contribution_date,
                source=c.source,
                note=c.note,
                created_at=c.created_at,
            )
            for c in contributions
        ],
        "assumptions": {
            "inflation": inflation,
            "investment_return": investment_return,
            "note": (
                "The future target is the current cost compounded at the stated inflation "
                "assumption. Historical CPI is not used as a forecast."
            ),
        },
    }


@router.put("/{goal_id}", response_model=GoalOut)
def update_goal(
    goal_id: int,
    payload: GoalUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    goal = owned_or_404(db, Goal, user, goal_id)
    data = payload.model_dump(exclude_unset=True)
    for key in ("current_cost", "current_funded_amount"):
        if key in data and data[key] is not None:
            data[key] = round_money(data[key])
    for key, value in data.items():
        if value is not None:
            setattr(goal, key, value)
    db.commit()
    db.refresh(goal)
    return _goal_out(goal)


@router.delete("/{goal_id}", response_model=MessageResponse)
def delete_goal(goal_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    goal = owned_or_404(db, Goal, user, goal_id)
    db.delete(goal)
    db.commit()
    return MessageResponse(message="Goal deleted.")


@router.get("/{goal_id}/contributions", response_model=list[ContributionOut])
def list_contributions(
    goal_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    goal = owned_or_404(db, Goal, user, goal_id)
    rows = db.execute(
        select(GoalContribution)
        .where(GoalContribution.goal_id == goal.id, GoalContribution.user_id == user.id)
        .order_by(GoalContribution.contribution_date.desc())
    ).scalars()
    return [
        ContributionOut(
            id=c.id,
            goal_id=c.goal_id,
            amount=money_float(c.amount),
            contribution_date=c.contribution_date,
            source=c.source,
            note=c.note,
            created_at=c.created_at,
        )
        for c in rows
    ]


@router.post("/{goal_id}/contributions", response_model=ContributionOut, status_code=201)
def add_contribution(
    goal_id: int,
    payload: ContributionIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    goal = owned_or_404(db, Goal, user, goal_id)
    row = GoalContribution(
        user_id=user.id,
        goal_id=goal.id,
        amount=round_money(payload.amount),
        contribution_date=payload.contribution_date,
        source=payload.source,
        note=payload.note,
    )
    db.add(row)
    # Recording a contribution increases the funded amount. It is added, never substituted.
    goal.current_funded_amount = round_money(float(goal.current_funded_amount) + payload.amount)
    db.commit()
    db.refresh(row)
    return ContributionOut(
        id=row.id,
        goal_id=row.goal_id,
        amount=money_float(row.amount),
        contribution_date=row.contribution_date,
        source=row.source,
        note=row.note,
        created_at=row.created_at,
    )
