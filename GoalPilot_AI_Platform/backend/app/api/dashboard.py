"""Dashboard, account management and data export."""
from __future__ import annotations

import datetime as dt
import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import current_user
from app.core.errors import ValidationFailure
from app.db import get_db
from app.models import (
    Asset,
    AuditEvent,
    Budget,
    ExpenseForecast,
    FinancialProfile,
    ForecastEvaluation,
    Goal,
    GoalContribution,
    IncomeSource,
    Liability,
    MonthlyRecord,
    OptimizationRun,
    ScenarioRun,
    Transaction,
    User,
    UserPreference,
)
from app.schemas.common import MessageResponse
from app.schemas.optimization import DashboardResponse
from app.services.cashflow import CashFlow
from app.services.forecasting import detect_persistent_overspend
from app.services.goals import project_goals
from app.services.money import money_float
from app.services.planner import get_profile_or_none, load_cashflow, load_goals, situation_tier

router = APIRouter(tags=["dashboard"])

LABELS_NOTE = (
    "Every figure is labelled by provenance: 'actual' comes from recorded transactions, "
    "'estimated' from a forecast and 'projected' from the planner's assumptions. No value is "
    "presented as if it were known when it is not."
)


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        cf = load_cashflow(db, user.id)
    except Exception:
        cf = CashFlow()

    profile = get_profile_or_none(db, user.id)
    goals = load_goals(db, user.id)
    inflation = float(profile.inflation_assumption) if profile else 0.03
    investment_return = float(profile.investment_return_assumption) if profile else 0.05

    projections = (
        project_goals(
            goals,
            inflation=inflation,
            savings_return=float(profile.savings_return_assumption) if profile else 0.0,
            investment_return=investment_return,
            monthly_surplus=max(0.0, cf.monthly_surplus),
            goal_budget=max(0.0, cf.available_goal_budget),
            available_cash=cf.available_cash_for_goals,
        )
        if goals
        else []
    )
    on_track = [p for p in projections if p.feasibility in ("feasible", "funded")]
    at_risk = [p for p in projections if p.feasibility in ("at_risk", "infeasible_on_current_cashflow", "infeasible")]

    # ---- monthly trend ---------------------------------------------------------------
    months = db.execute(
        select(MonthlyRecord)
        .where(MonthlyRecord.user_id == user.id)
        .order_by(MonthlyRecord.period.desc())
        .limit(24)
    ).scalars().all()
    months = list(reversed(months))
    trend = [
        {
            "period": m.period,
            "income_actual": money_float(m.total_income_actual),
            "income_expected": money_float(m.total_income_expected),
            "expense_actual": money_float(m.total_expense_actual),
            "expense_estimated": money_float(m.total_expense_estimated),
            "surplus_actual": money_float(m.surplus_actual),
            "surplus_projected": money_float(m.surplus_projected),
            "status": m.status,
        }
        for m in months
    ]
    current_period = dt.date.today().strftime("%Y-%m")
    current = next((t for t in trend if t["period"] == current_period), None)

    # ---- category breakdown for the most recent month with data -----------------------
    category_rows: list[dict] = []
    for m in reversed(months):
        txns = db.execute(
            select(Transaction).where(
                Transaction.month_id == m.id, Transaction.kind == "expense"
            )
        ).scalars().all()
        if not txns:
            continue
        agg: dict[str, dict[str, float]] = {}
        for t in txns:
            slot = agg.setdefault(t.category, {"actual": 0.0, "estimated": 0.0})
            slot["actual" if t.status == "actual" else "estimated"] += float(t.amount)
        category_rows = [
            {"category": c, **v} for c, v in sorted(agg.items(), key=lambda kv: -sum(kv[1].values()))
        ]
        break

    # ---- forecasts -------------------------------------------------------------------
    forecasts = db.execute(
        select(ExpenseForecast)
        .where(ExpenseForecast.user_id == user.id)
        .order_by(ExpenseForecast.period.desc(), ExpenseForecast.category)
        .limit(60)
    ).scalars().all()
    evaluations = db.execute(
        select(ForecastEvaluation).where(ForecastEvaluation.user_id == user.id)
    ).scalars().all()
    err_by_period: dict[str, dict[str, float]] = {}
    for e in evaluations:
        slot = err_by_period.setdefault(e.period, {"forecast": 0.0, "actual": 0.0, "abs_error": 0.0})
        slot["forecast"] += float(e.forecast_amount)
        slot["actual"] += float(e.actual_amount)
        slot["abs_error"] += float(e.abs_error)

    budgets = db.execute(
        select(Budget).where(Budget.user_id == user.id, Budget.is_active.is_(True))
    ).scalars().all()
    budget_map = {b.category: float(b.monthly_limit) for b in budgets}
    history_obs = db.execute(
        select(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.kind == "expense",
            Transaction.status == "actual",
        )
    ).scalars().all()
    from app.services.forecasting import MonthObservation

    observations = [
        MonthObservation(period=t.period, category=t.category, amount=float(t.amount))
        for t in history_obs
    ]

    # ---- optimisation -----------------------------------------------------------------
    last_run = db.execute(
        select(OptimizationRun)
        .where(OptimizationRun.user_id == user.id, OptimizationRun.kind == "plan")
        .order_by(OptimizationRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    last_compare = db.execute(
        select(OptimizationRun)
        .where(OptimizationRun.user_id == user.id, OptimizationRun.kind == "compare")
        .order_by(OptimizationRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    comparison_arms = []
    if last_compare is not None:
        payload = json.loads(last_compare.result_json or "{}")
        comparison_arms = [
            {
                "algorithm": a.get("algorithm"),
                "label": a.get("label"),
                "weighted_goal_achievement": (a.get("metrics") or {}).get(
                    "weighted_goal_achievement"
                ),
                "pct_goals_met_by_deadline": (a.get("metrics") or {}).get(
                    "pct_goals_met_by_deadline"
                ),
                "available": a.get("available"),
            }
            for a in payload.get("arms", [])
        ]
    plan_result = json.loads(last_run.result_json or "{}") if last_run else {}

    total_debt = sum(float(l.outstanding_principal) for l in db.execute(
        select(Liability).where(Liability.user_id == user.id)
    ).scalars().all())
    total_emi = float(cf.existing_emi)

    return DashboardResponse(
        as_of=dt.datetime.now(dt.timezone.utc).isoformat(),
        cashflow={
            **cf.as_dict(),
            "is_deficit": cf.is_deficit,
            "situation_tier": situation_tier(cf),
        },
        goals={
            "active_count": len(goals),
            "total_goals": len(db.execute(select(Goal).where(Goal.user_id == user.id)).scalars().all()),
            "on_track": len(on_track),
            "at_risk": len(at_risk),
            "total_remaining_gap": round(sum(p.remaining_gap for p in projections), 2),
            "total_required_monthly": round(
                sum(p.required_monthly_contribution for p in projections), 2
            ),
            "items": [p.as_dict() for p in projections],
            "funding_chart": [
                {
                    "name": p.name,
                    "future_target": round(p.future_target, 2),
                    "existing_funding": round(p.existing_funding, 2),
                    "remaining_gap": round(p.remaining_gap, 2),
                    "feasibility": p.feasibility,
                }
                for p in projections
            ],
        },
        monthly={
            "current_period": current_period,
            "current": current,
            "trend": trend,
            "category_breakdown": category_rows,
        },
        forecasts={
            "latest_count": len(forecasts),
            "latest": [
                {
                    "period": f.period,
                    "category": f.category,
                    "amount": money_float(f.forecast_amount),
                    "method": f.method,
                    "is_provisional": f.is_provisional,
                    "data_quality": f.data_quality,
                }
                for f in forecasts[:30]
            ],
            "error_trend": [
                {
                    "period": period,
                    "forecast": round(v["forecast"], 2),
                    "actual": round(v["actual"], 2),
                    "abs_error": round(v["abs_error"], 2),
                }
                for period, v in sorted(err_by_period.items())
            ],
            "persistent_overspend": detect_persistent_overspend(observations, budget_map),
        },
        debt={
            "outstanding_principal": round(total_debt, 2),
            "monthly_emi": round(total_emi, 2),
            "emi_income_ratio": round(cf.emi_income_ratio, 4),
            "emi_income_ratio_cap": cf.emi_income_ratio_cap,
            "within_cap": cf.emi_income_ratio <= cf.emi_income_ratio_cap,
        },
        optimization={
            "last_plan": (
                {
                    "run_id": last_run.id,
                    "algorithm": last_run.algorithm,
                    "status": last_run.status,
                    "feasible": last_run.feasible,
                    "weighted_achievement": (
                        float(last_run.weighted_achievement)
                        if last_run.weighted_achievement is not None
                        else None
                    ),
                    "total_shortfall": (
                        float(last_run.total_shortfall)
                        if last_run.total_shortfall is not None
                        else None
                    ),
                    "created_at": last_run.created_at.isoformat(),
                    "summary": plan_result.get("summary", {}),
                }
                if last_run
                else None
            ),
            "last_comparison": (
                {
                    "run_id": last_compare.id,
                    "recommended_algorithm": last_compare.algorithm,
                    "created_at": last_compare.created_at.isoformat(),
                    "arms": comparison_arms,
                }
                if last_compare
                else None
            ),
        },
        labels_note=LABELS_NOTE,
    )


# --------------------------------------------------------------------------------------
# account and data management
# --------------------------------------------------------------------------------------
@router.get("/account/export")
def export_account(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Full JSON export of everything the account owns. No derived secret is included."""
    def rows(model):
        return [r for r in db.execute(select(model).where(model.user_id == user.id)).scalars()]

    def ser(obj) -> dict:
        out = {}
        for column in obj.__table__.columns:
            value = getattr(obj, column.name)
            if isinstance(value, (dt.date, dt.datetime)):
                value = value.isoformat()
            elif hasattr(value, "__float__") and column.name not in ("id", "user_id"):
                value = float(value)
            out[column.name] = value
        return out

    profile = get_profile_or_none(db, user.id)
    pref = db.execute(
        select(UserPreference).where(UserPreference.user_id == user.id)
    ).scalar_one_or_none()
    export = {
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "account": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "created_at": user.created_at.isoformat(),
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        },
        "preferences": ser(pref) if pref else None,
        "financial_profile": ser(profile) if profile else None,
        "income_sources": [ser(r) for r in rows(IncomeSource)],
        "assets": [ser(r) for r in rows(Asset)],
        "liabilities": [ser(r) for r in rows(Liability)],
        "goals": [ser(r) for r in rows(Goal)],
        "goal_contributions": [ser(r) for r in rows(GoalContribution)],
        "monthly_records": [ser(r) for r in rows(MonthlyRecord)],
        "transactions": [ser(r) for r in rows(Transaction)],
        "budgets": [ser(r) for r in rows(Budget)],
        "expense_forecasts": [ser(r) for r in rows(ExpenseForecast)],
        "forecast_evaluations": [ser(r) for r in rows(ForecastEvaluation)],
        "optimization_runs": [ser(r) for r in rows(OptimizationRun)],
        "scenario_runs": [ser(r) for r in rows(ScenarioRun)],
        "note": (
            "No password hash, reset token or session token is included in this export."
        ),
    }
    db.add(AuditEvent(user_id=user.id, event_type="data_export", detail_json="{}"))
    db.commit()
    return export


@router.delete("/account", response_model=MessageResponse)
def delete_account(
    confirm: str = Query(
        default="",
        description="Must be exactly DELETE. Guards against an accidental destructive call.",
    ),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Delete the account and every owned record.

    Requires ``?confirm=DELETE`` so the destructive call cannot fire by accident. All
    child rows are removed through the foreign keys' ON DELETE CASCADE.
    """
    if confirm != "DELETE":
        raise ValidationFailure(
            "Account deletion requires ?confirm=DELETE. Nothing was deleted.",
            details={"expected": "DELETE"},
        )
    email = user.email
    db.delete(user)
    db.commit()
    return MessageResponse(message=f"Account {email} and all associated data have been deleted.")
