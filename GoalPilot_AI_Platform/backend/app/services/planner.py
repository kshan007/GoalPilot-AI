"""Orchestration: load a user's financial state, run an engine, persist and diff the plan.

This is the only place that touches both the database and the engines, which keeps the
engines pure and independently testable.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationFailure
from app.engines import hybrid_engine, lp_engine, rl_engine, selector
from app.engines.common import (
    ALGORITHM_HYBRID,
    ALGORITHM_LABELS,
    ALGORITHM_LP,
    ALGORITHM_RL,
    OBJECTIVE_DEFINITION,
    ArmResult,
)
from app.models import (
    Asset,
    ExpenseForecast,
    FinancialProfile,
    Goal,
    GoalAllocation,
    IncomeSource,
    Liability,
    MonthlyRecord,
    OptimizationRun,
    Transaction,
    UserPreference,
)
from app.services.cashflow import CashFlow, build_cashflow
from app.services.money import months_between, money_float, round_money
from app.services.goals import project_goals


def get_profile_or_none(db: Session, user_id: int) -> FinancialProfile | None:
    return db.execute(
        select(FinancialProfile).where(FinancialProfile.user_id == user_id)
    ).scalar_one_or_none()


def get_preferences(db: Session, user_id: int) -> UserPreference:
    pref = db.execute(
        select(UserPreference).where(UserPreference.user_id == user_id)
    ).scalar_one_or_none()
    if pref is None:
        pref = UserPreference(user_id=user_id)
        db.add(pref)
        db.flush()
    return pref


def load_income_sources(db: Session, user_id: int) -> list[IncomeSource]:
    return list(
        db.execute(
            select(IncomeSource).where(
                IncomeSource.user_id == user_id, IncomeSource.is_active.is_(True)
            )
        ).scalars()
    )


def load_assets(db: Session, user_id: int) -> list[Asset]:
    return list(db.execute(select(Asset).where(Asset.user_id == user_id)).scalars())


def load_liabilities(db: Session, user_id: int) -> list[Liability]:
    return list(db.execute(select(Liability).where(Liability.user_id == user_id)).scalars())


def load_goals(db: Session, user_id: int, *, include_inactive: bool = False) -> list[Goal]:
    stmt = select(Goal).where(Goal.user_id == user_id)
    if not include_inactive:
        stmt = stmt.where(Goal.status == "active")
    return list(db.execute(stmt.order_by(Goal.priority.desc(), Goal.target_date)).scalars())


def expense_items_for_month(db: Session, user_id: int, period: str) -> list[dict[str, Any]] | None:
    """**Actual** expense lines for a month, or ``None`` when the month has none.

    Only rows with ``status == "actual"`` are used. An estimate is not evidence of what was
    spent, so planning on estimates would let a guess displace what the user told us in their
    profile. Estimates feed the forecaster; actuals feed the plan.

    Returning ``None`` makes the caller fall back to the profile's own essential/discretionary
    split rather than assuming the month's spending was zero.
    """
    month = db.execute(
        select(MonthlyRecord).where(
            MonthlyRecord.user_id == user_id, MonthlyRecord.period == period
        )
    ).scalar_one_or_none()
    if month is None:
        return None
    rows = list(
        db.execute(
            select(Transaction).where(
                Transaction.month_id == month.id,
                Transaction.kind == "expense",
                Transaction.status == "actual",
            )
        ).scalars()
    )
    if not rows:
        return None
    return [
        {
            "category": r.category,
            "amount": float(r.amount),
            "classification": r.classification,
        }
        for r in rows
    ]


def _active_period(db: Session, user_id: int, explicit: str | None = None) -> str:
    """The month whose actuals the plan should use.

    ``explicit`` wins. Otherwise the most recent period that has at least one actual expense
    transaction, falling back to the current calendar month.
    """
    if explicit:
        return explicit
    row = db.execute(
        select(Transaction.period)
        .where(
            Transaction.user_id == user_id,
            Transaction.kind == "expense",
            Transaction.status == "actual",
        )
        .order_by(Transaction.period.desc())
        .limit(1)
    ).scalar_one_or_none()
    return row or dt.date.today().strftime("%Y-%m")


def load_cashflow(
    db: Session,
    user_id: int,
    *,
    period: str | None = None,
) -> CashFlow:
    """Build the canonical financial state.

    ``period`` selects which month's **actual** expense transactions are used for the
    essential/discretionary split. When omitted, the most recent month with actuals is used
    (falling back to the profile figures when no actuals exist anywhere). The choice is
    recorded on the returned object as ``expense_basis`` so the plan can disclose it.
    """
    profile = get_profile_or_none(db, user_id)
    if profile is None:
        raise ValidationFailure(
            "Complete onboarding and save a financial profile before generating a plan."
        )
    income = load_income_sources(db, user_id)
    if not income:
        raise ValidationFailure("Add at least one income source before generating a plan.")
    liabilities = load_liabilities(db, user_id)
    assets = load_assets(db, user_id)
    goals = load_goals(db, user_id, include_inactive=True)
    earmarked = sum(float(g.current_funded_amount) for g in goals if g.status == "active")

    resolved_period = _active_period(db, user_id, period)
    items = expense_items_for_month(db, user_id, resolved_period)
    # Risk *capacity* lives on the profile; liquidity requirement and loss ability live on the
    # preferences. Both are inputs to the investment ceiling, so both are read here. Read-only:
    # a planning GET must not create a preferences row as a side effect.
    preferences = db.execute(
        select(UserPreference).where(UserPreference.user_id == user_id)
    ).scalar_one_or_none()

    return build_cashflow(
        income_sources=income,
        liabilities=liabilities,
        assets=assets,
        profile=profile,
        expense_items=items,
        earmarked_goal_funding=earmarked,
        liquidity_requirement=getattr(preferences, "liquidity_requirement", "medium"),
        loss_ability=getattr(preferences, "loss_ability", "moderate"),
    )


def months_lookup(goals: list[Goal], today: dt.date | None = None) -> dict[int, int]:
    today = today or dt.date.today()
    return {g.id: max(1, months_between(today, g.target_date)) for g in goals}


def assumptions_for(db: Session, user_id: int, overrides: dict[str, Any] | None = None):
    """Profile-level assumption defaults, overridable per request."""
    profile = get_profile_or_none(db, user_id)
    base = lp_engine.LpAssumptions()
    if profile is not None:
        base.annual_inflation = float(profile.inflation_assumption)
        base.investment_return = float(profile.investment_return_assumption)
        base.savings_return = float(profile.savings_return_assumption)
        base.loan_annual_rate = float(profile.loan_interest_assumption)
    if overrides:
        allowed = set(base.as_dict())
        unknown = sorted(set(overrides) - allowed)
        if unknown:
            raise ValidationFailure(
                "Unknown assumption(s)", details={"unknown": unknown, "allowed": sorted(allowed)}
            )
        for key, value in overrides.items():
            if value is not None:
                setattr(base, key, value)
    return base


def run_algorithm(
    *,
    algorithm: str,
    goals: list[Goal],
    cashflow: CashFlow,
    lookup: dict[int, int],
    assumptions: lp_engine.LpAssumptions,
    checkpoint: str | None = None,
) -> ArmResult:
    if algorithm == ALGORITHM_LP:
        return lp_engine.solve(
            goals=goals, cashflow=cashflow, assumptions=assumptions, constrained=True
        )
    if algorithm == "lp_unconstrained":
        result = lp_engine.solve(
            goals=goals, cashflow=cashflow, assumptions=assumptions, constrained=False
        )
        return result
    if algorithm == ALGORITHM_RL:
        return rl_engine.solve(
            goals=goals, cashflow=cashflow, months_lookup=lookup, checkpoint_path=checkpoint
        )
    if algorithm == ALGORITHM_HYBRID:
        return hybrid_engine.solve(
            goals=goals, cashflow=cashflow, months_lookup=lookup, checkpoint_path=checkpoint
        )
    raise ValidationFailure(f"Unknown algorithm '{algorithm}'")


# --------------------------------------------------------------------------------------
# persistence
# --------------------------------------------------------------------------------------
def persist_run(
    db: Session,
    user_id: int,
    result: ArmResult,
    *,
    kind: str,
    assumptions: dict[str, Any],
    input_snapshot: dict[str, Any],
    goal_db_ids: dict[str, int] | None = None,
    label: str = "",
    extra_payload: dict[str, Any] | None = None,
) -> OptimizationRun:
    goal_db_ids = goal_db_ids or {}
    run = OptimizationRun(
        user_id=user_id,
        kind=kind,
        algorithm=result.algorithm,
        status=result.status,
        feasible=result.feasible,
        assumptions_json=json.dumps(assumptions, default=str),
        input_snapshot_json=json.dumps(input_snapshot, default=str),
        result_json=json.dumps(
            {
                "summary": result.summary,
                "constraints": result.constraints,
                "diagnostics": result.diagnostics,
                "label": label,
                **(extra_payload or {}),
            },
            default=str,
        ),
        # The objective is a penalty SCORE, not money. Rounding it through `round_money`
        # truncated e.g. 6.7161 to 6.72 in the database, so a reloaded run disagreed with the
        # run that had just been created and the value looked like a currency amount.
        objective_value=(
            round(float(result.objective_value), 6) if result.objective_value is not None else None
        ),
        weighted_achievement=(
            result.summary.get("weighted_goal_achievement")
            if isinstance(result.summary.get("weighted_goal_achievement"), (int, float))
            else None
        ),
        total_shortfall=(
            round_money(result.summary["total_shortfall"])
            if isinstance(result.summary.get("total_shortfall"), (int, float))
            else None
        ),
        runtime_ms=result.runtime_ms,
        model_version=result.model_version,
        config_version=result.config_version,
        warnings_json=json.dumps(result.warnings, default=str),
    )
    db.add(run)
    db.flush()

    for row in result.allocations or []:
        ref = str(row.get("goal_ref") or row.get("goal_id") or "")
        db.add(
            GoalAllocation(
                user_id=user_id,
                optimization_run_id=run.id,
                goal_id=goal_db_ids.get(ref),
                goal_ref=ref,
                goal_name=str(row.get("goal_name", ""))[:160],
                future_goal_cost=round_money(row.get("future_goal_cost") or row.get("future_cost") or row.get("future_target") or row.get("target") or row.get("target_amount") or 0),
                existing_funding=round_money(row.get("existing_funding") or 0),
                funding_gap=round_money(row.get("funding_gap") or 0),
                initial_savings_allocated=round_money(row.get("initial_savings_allocated") or 0),
                existing_assets_allocated=round_money(row.get("existing_assets_allocated") or 0),
                monthly_savings_contribution=round_money(
                    row.get("monthly_savings_contribution") or 0
                ),
                monthly_investment_contribution=round_money(
                    row.get("monthly_investment_contribution") or 0
                ),
                loan_principal=round_money(row.get("loan_principal") or 0),
                estimated_loan_emi=round_money(row.get("estimated_loan_emi") or 0),
                estimated_loan_interest_cost=round_money(
                    row.get("estimated_loan_interest_cost") or 0
                ),
                projected_new_funding=round_money(
                    row.get("projected_new_funding") or row.get("funded") or 0
                ),
                shortfall=round_money(row.get("shortfall") or 0),
                achievement_ratio=float(row.get("achievement_ratio") or 0),
            )
        )
    db.flush()
    return run


def previous_run(db: Session, user_id: int, kind: str, exclude_id: int | None = None):
    stmt = (
        select(OptimizationRun)
        .where(OptimizationRun.user_id == user_id, OptimizationRun.kind == kind)
        .order_by(OptimizationRun.created_at.desc(), OptimizationRun.id.desc())
    )
    if exclude_id is not None:
        stmt = stmt.where(OptimizationRun.id != exclude_id)
    return db.execute(stmt.limit(1)).scalar_one_or_none()


def diff_runs(db: Session, previous: OptimizationRun | None, current: OptimizationRun) -> dict[str, Any]:
    """Explain how the new plan differs from the previous one."""
    if previous is None:
        return {
            "previous_run_id": None,
            "changed": True,
            "summary": "This is the first plan, so there is nothing to compare against yet.",
            "goal_changes": [],
            "totals": {},
        }
    prev_rows = {
        a.goal_ref: a
        for a in db.execute(
            select(GoalAllocation).where(GoalAllocation.optimization_run_id == previous.id)
        ).scalars()
    }
    cur_rows = {
        a.goal_ref: a
        for a in db.execute(
            select(GoalAllocation).where(GoalAllocation.optimization_run_id == current.id)
        ).scalars()
    }
    changes: list[dict[str, Any]] = []
    for ref in sorted(set(prev_rows) | set(cur_rows)):
        a, b = prev_rows.get(ref), cur_rows.get(ref)
        if a is None or b is None:
            changes.append(
                {
                    "goal_ref": ref,
                    "change": "added" if b is not None else "removed",
                    "detail": "The goal was not part of the previous plan."
                    if b is not None
                    else "The goal is no longer in the active plan.",
                }
            )
            continue
        deltas = {
            "monthly_savings_contribution": float(b.monthly_savings_contribution)
            - float(a.monthly_savings_contribution),
            "monthly_investment_contribution": float(b.monthly_investment_contribution)
            - float(a.monthly_investment_contribution),
            "initial_savings_allocated": float(b.initial_savings_allocated)
            - float(a.initial_savings_allocated),
            "loan_principal": float(b.loan_principal) - float(a.loan_principal),
            "shortfall": float(b.shortfall) - float(a.shortfall),
        }
        if any(abs(v) > 0.01 for v in deltas.values()):
            changes.append(
                {
                    "goal_ref": ref,
                    "goal_name": b.goal_name or a.goal_name,
                    "change": "updated",
                    "deltas": {k: round(v, 2) for k, v in deltas.items()},
                }
            )
    prev_summary = json.loads(previous.result_json or "{}").get("summary", {})
    cur_summary = json.loads(current.result_json or "{}").get("summary", {})
    totals = {}
    for key in ("total_shortfall", "monthly_contributions_allocated", "weighted_goal_achievement"):
        if key in prev_summary or key in cur_summary:
            p = float(prev_summary.get(key, 0) or 0)
            c = float(cur_summary.get(key, 0) or 0)
            totals[key] = {"previous": round(p, 2), "current": round(c, 2), "delta": round(c - p, 2)}
    changed = bool(changes) or any(abs(t.get("delta", 0)) > 0.01 for t in totals.values())
    if not changed:
        summary = "The new plan is materially identical to the previous one."
    else:
        bits = []
        if totals.get("total_shortfall", {}).get("delta", 0) < -0.01:
            bits.append(
                f"total shortfall fell by {abs(totals['total_shortfall']['delta']):,.0f}"
            )
        elif totals.get("total_shortfall", {}).get("delta", 0) > 0.01:
            bits.append(
                f"total shortfall rose by {totals['total_shortfall']['delta']:,.0f}"
            )
        if totals.get("monthly_contributions_allocated", {}).get("delta", 0) != 0:
            bits.append(
                "planned monthly contributions moved from "
                f"{totals['monthly_contributions_allocated']['previous']:,.0f} to "
                f"{totals['monthly_contributions_allocated']['current']:,.0f}"
            )
        bits.append(f"{len(changes)} goal-level change(s) recorded")
        summary = "; ".join(bits) + "."
    return {
        "previous_run_id": previous.id,
        "changed": changed,
        "summary": summary,
        "goal_changes": changes,
        "totals": totals,
    }


def build_plan_response(
    db: Session,
    run: OptimizationRun,
    result: ArmResult,
    *,
    cashflow: CashFlow,
    goals: list[Goal],
    assumptions: dict[str, Any],
    diff: dict[str, Any] | None,
) -> dict[str, Any]:
    allocations = []
    for row in result.allocations or []:
        allocations.append(
            {
                "goal_ref": str(row.get("goal_ref") or row.get("goal_id") or ""),
                "goal_id": row.get("db_goal_id") or row.get("goal_id")
                if isinstance(row.get("goal_id"), int)
                else None,
                "goal_name": str(row.get("goal_name", "")),
                "funding_gap": float(row.get("funding_gap") or 0),
                "future_goal_cost": float(row.get("future_goal_cost") or row.get("future_cost") or row.get("future_target") or row.get("target") or row.get("target_amount") or 0),
                "initial_savings_allocated": float(row.get("initial_savings_allocated") or 0),
                "existing_assets_allocated": float(row.get("existing_assets_allocated") or 0),
                "monthly_savings_contribution": float(row.get("monthly_savings_contribution") or 0),
                "monthly_investment_contribution": float(
                    row.get("monthly_investment_contribution") or 0
                ),
                "loan_principal": float(row.get("loan_principal") or 0),
                "estimated_loan_emi": float(row.get("estimated_loan_emi") or 0),
                "shortfall": float(row.get("shortfall") or 0),
                "achievement_ratio": float(row.get("achievement_ratio") or 0),
                "projected_new_funding": float(
                    row.get("projected_new_funding") or row.get("funded") or 0
                ),
                "target": float(row["target"]) if row.get("target") is not None else None,
                "funded": float(row["funded"]) if row.get("funded") is not None else None,
            }
        )

    projections = []
    if result.allocations:
        try:
            import pandas as pd

            frame = pd.DataFrame(result.allocations)
            projections = [
                p.as_dict()
                for p in project_goals(
                    goals,
                    inflation=float(assumptions.get("annual_inflation", 0.03)),
                    savings_return=float(assumptions.get("savings_return", 0.0)),
                    investment_return=float(assumptions.get("investment_return", 0.05)),
                    # Feasibility must be judged against the money the household may actually
                    # put towards goals, i.e. surplus net of the protected buffer. Using gross
                    # surplus here marked a goal "feasible" while the buffer consumed the very
                    # money the plan needed.
                    monthly_surplus=max(0.0, cashflow.monthly_surplus),
                    goal_budget=max(0.0, cashflow.available_goal_budget),
                    available_cash=cashflow.available_cash_for_goals,
                    allocations=frame,
                )
            ]
        except Exception:  # pragma: no cover - projection is additive, never fatal
            projections = []

    stored = json.loads(run.result_json or "{}")

    # "Feasible" is a statement about constraints, not about affordability. A plan can satisfy
    # every hard constraint and still leave goals short, which is exactly what the allocation table
    # shows — so the two facts are reported separately instead of one standing in for the other.
    unfunded_goals = [
        str(a.get("goal_name") or a.get("goal_ref") or "")
        for a in allocations
        if float(a.get("shortfall") or 0)
        > max(1.0, 0.001 * float(a.get("future_goal_cost") or 0))
    ]
    total_shortfall = round(sum(float(a.get("shortfall") or 0) for a in allocations), 2)

    # Engine warnings and cash-flow warnings are both the user's business. The cash-flow
    # warnings (emergency fund, EMI ceiling, buffer) used to sit only inside the `cashflow`
    # sub-object, so the plan page never showed them while the goals it displayed could all be
    # "funded". Merging them here keeps the two statements in front of the reader together.
    merged_warnings: list[str] = []
    for warning in list(result.warnings or []) + list(cashflow.warnings or []):
        if warning and warning not in merged_warnings:
            merged_warnings.append(warning)

    return {
        "run_id": run.id,
        "algorithm": result.algorithm,
        "algorithm_label": ALGORITHM_LABELS.get(result.algorithm, result.algorithm),
        "status": result.status,
        "feasible": result.feasible,
        # Same precision as the stored run, so the value returned by the create call and the
        # value returned after a reload are the same number rather than differing in the 7th
        # decimal.
        "objective_value": (
            round(float(result.objective_value), 6) if result.objective_value is not None else None
        ),
        "objective_definition": OBJECTIVE_DEFINITION,
        "readiness": cashflow.readiness(),
        "runtime_ms": result.runtime_ms,
        "model_version": result.model_version,
        "config_version": result.config_version,
        "assumptions": assumptions,
        "summary": result.summary,
        "constraints": result.constraints,
        "diagnostics": result.diagnostics,
        "alternatives": stored.get("alternatives", []) or [],
        "goals_funded": not unfunded_goals,
        "unfunded_goals": unfunded_goals,
        "total_shortfall": total_shortfall,
        "allocations": allocations,
        "goal_projections": projections,
        "cashflow": _cashflow_out(cashflow),
        "warnings": merged_warnings,
        "fallback_reason": result.fallback_reason,
        "diff": diff,
        "created_at": run.created_at,
    }


def _cashflow_out(cf: CashFlow) -> dict[str, Any]:
    data = cf.as_dict()
    data["is_deficit"] = cf.is_deficit
    return data


def situation_tier(cf: CashFlow) -> str:
    """A transparent label, not a credit score. Rules are stated in the data dictionary."""
    if cf.monthly_surplus <= 0:
        return "deficit"
    if cf.emi_income_ratio > cf.emi_income_ratio_cap:
        return "debt_stressed"
    if cf.emergency_fund_progress < 0.5:
        return "thin_buffer"
    ratio = cf.monthly_surplus / cf.monthly_income if cf.monthly_income else 0
    if ratio >= 0.30 and cf.emergency_fund_progress >= 1.0:
        return "strong"
    if ratio >= 0.15:
        return "moderate_saving"
    return "thin_surplus"


