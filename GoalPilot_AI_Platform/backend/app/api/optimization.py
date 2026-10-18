"""Optimisation workspace: plan, compare, run history, model registry, benchmarks."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import current_user, enforce_optimize_rate_limit, require_admin
from app.core.errors import NotFoundError, ValidationFailure
from app.db import get_db
from app.engines import lp_engine, research_loader, rl_engine, selector
from app.engines.common import ALGORITHM_LABELS, OBJECTIVE_DEFINITION, ArmResult
from app.models import Goal, GoalAllocation, OptimizationRun, User
from app.schemas.optimization import (
    AlgorithmAvailability,
    ComparisonResponse,
    PlanRequest,
    PlanResponse,
)
from app.services import alternatives as alternatives_service
from app.services.planner import (
    assumptions_for,
    build_plan_response,
    diff_runs,
    load_cashflow,
    load_goals,
    months_lookup,
    persist_run,
    previous_run,
    run_algorithm,
    situation_tier,
)

router = APIRouter(tags=["optimization"])


def _goal_id_map(goals: list[Goal]) -> dict[str, int]:
    return {f"G{g.id}": g.id for g in goals}


@router.get("/optimize/algorithms", response_model=list[AlgorithmAvailability])
def list_algorithms():
    """Which arms are ready right now, and why."""
    out: list[AlgorithmAvailability] = []

    research_ok = research_loader.is_available()
    out.append(
        AlgorithmAvailability(
            algorithm="lp",
            label=ALGORITHM_LABELS["lp"],
            ready=research_ok,
            status="ready" if research_ok else "unavailable",
            reason=None if research_ok else "The research model project could not be located.",
            detail={
                "solver": "scipy.optimize.linprog(method='highs')",
                "model_version": lp_engine.LP_MODEL_VERSION,
                "constraints": [
                    "shared cash pool (existing earmarks excluded)",
                    "usable existing assets",
                    "monthly surplus",
                    "EMI capacity",
                    "combined affordability",
                    "executable investment capacity",
                    "single active loan limit",
                ],
            },
        )
    )
    rl = rl_engine.readiness()
    out.append(
        AlgorithmAvailability(
            algorithm="rl",
            label=ALGORITHM_LABELS["rl"],
            ready=bool(rl.get("available")),
            status="ready" if rl.get("available") else "unavailable",
            reason=rl.get("reason"),
            detail=rl,
        )
    )
    out.append(
        AlgorithmAvailability(
            algorithm="hybrid",
            label=ALGORITHM_LABELS["hybrid"],
            ready=bool(rl.get("available")),
            status="ready" if rl.get("available") else "unavailable",
            reason=None
            if rl.get("available")
            else "The hybrid needs the RL stage; without it the hybrid falls back to the LP.",
            detail={
                "architecture": "RL proposes theta -> LP allocates -> simulator evaluates",
                "safety": "theta can only lower the investment ceiling and remove financing",
            },
        )
    )
    out.append(
        AlgorithmAvailability(
            algorithm="rule_baseline",
            label="Uniform savings rule",
            ready=research_ok,
            status="ready" if research_ok else "unavailable",
            reason=None if research_ok else "Needs the research environment to score.",
            detail={"purpose": "Deliberately simple control used by the comparison."},
        )
    )
    return out


@router.post(
    "/optimize/plan",
    response_model=PlanResponse,
    dependencies=[Depends(enforce_optimize_rate_limit)],
)
def create_plan(
    payload: PlanRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    # Profile first: it is the harder prerequisite, and its error is the more actionable one.
    cashflow = load_cashflow(db, user.id, period=payload.period)
    goals = load_goals(db, user.id)
    if not goals:
        raise ValidationFailure("Create at least one active goal before generating a plan.")
    lookup = months_lookup(goals)
    overrides = payload.assumptions.model_dump(exclude_none=True) if payload.assumptions else {}
    assumptions = assumptions_for(db, user.id, overrides)

    algorithm = payload.algorithm
    if algorithm == "rule_baseline":
        raise ValidationFailure(
            "The uniform savings rule is available through the comparison endpoint only; "
            "it is a control, not a plan you can adopt."
        )
    result = run_algorithm(
        algorithm=algorithm,
        goals=goals,
        cashflow=cashflow,
        lookup=lookup,
        assumptions=assumptions,
        checkpoint=payload.rl_checkpoint,
    )

    # Alternatives are evaluated for every arm — including rl and hybrid — so a plan that cannot
    # meet its goals reports the same concrete routes the goal page offers instead of only a
    # shortfall. Bounded and additive: a failure here never fails the plan.
    alternative_rows: list[dict] = []
    try:
        alternative_rows = alternatives_service.evaluate(
            goals=goals,
            cashflow=cashflow,
            assumptions=assumptions,
            allocations=result.allocations or [],
            algorithm=result.algorithm,
        )
    except Exception:  # noqa: BLE001 - evaluation is additive, never fatal
        alternative_rows = []
    note = alternatives_service.summary_note(alternative_rows, result.algorithm)
    if note and note not in result.warnings:
        result.warnings.append(note)

    snapshot = {
        "goal_count": len(goals),
        "monthly_income": cashflow.monthly_income,
        "essential_expenses": cashflow.essential_expenses,
        "discretionary_expenses": cashflow.discretionary_expenses,
        "existing_emi": cashflow.existing_emi,
        "monthly_surplus": cashflow.monthly_surplus,
        "liquid_savings": cashflow.liquid_savings,
        "available_cash_for_goals": cashflow.available_cash_for_goals,
        "expense_basis": cashflow.expense_basis,
        "expense_categories_used": cashflow.expense_categories_used,
        "requested_period": payload.period,
        "situation_tier": situation_tier(cashflow),
        "goals": [
            {
                "id": g.id,
                "name": g.name,
                "current_cost": float(g.current_cost),
                "current_funded_amount": float(g.current_funded_amount),
                "target_date": g.target_date.isoformat(),
                "priority": g.priority,
                "criticality": g.criticality,
            }
            for g in goals
        ],
    }
    run = persist_run(
        db,
        user.id,
        result,
        kind="plan",
        assumptions=assumptions.as_dict(),
        input_snapshot=snapshot,
        goal_db_ids=_goal_id_map(goals),
        label=payload.label,
        extra_payload={"alternatives": alternative_rows},
    )
    prev = previous_run(db, user.id, "plan", exclude_id=run.id)
    diff = diff_runs(db, prev, run)
    db.commit()
    db.refresh(run)
    return build_plan_response(
        db, run, result, cashflow=cashflow, goals=goals,
        assumptions=assumptions.as_dict(), diff=diff,
    )


@router.get("/optimize/plan/latest")
def latest_plan(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The most recent persisted plan, rebuilt into the same shape as a fresh run.

    This exists because the Optimize page held its plan in component state only, so a browser
    refresh showed "No plan has been run in this session" even though the run was persisted.
    Returns 404 when no plan has ever been run, so the page can show its honest empty state.
    """
    run = previous_run(db, user.id, "plan")
    if run is None:
        raise NotFoundError("No plan has been run yet.")

    payload = json.loads(run.result_json or "{}")
    allocations = []
    for a in db.execute(
        select(GoalAllocation).where(GoalAllocation.optimization_run_id == run.id)
    ).scalars():
        allocations.append(
            {
                "goal_ref": a.goal_ref,
                "goal_id": a.goal_id,
                "db_goal_id": a.goal_id,
                "goal_name": a.goal_name,
                "funding_gap": float(a.funding_gap),
                "future_goal_cost": float(a.future_goal_cost),
                "existing_funding": float(a.existing_funding),
                "initial_savings_allocated": float(a.initial_savings_allocated),
                "existing_assets_allocated": float(a.existing_assets_allocated),
                "monthly_savings_contribution": float(a.monthly_savings_contribution),
                "monthly_investment_contribution": float(a.monthly_investment_contribution),
                "loan_principal": float(a.loan_principal),
                "estimated_loan_emi": float(a.estimated_loan_emi),
                "estimated_loan_interest_cost": float(a.estimated_loan_interest_cost),
                "projected_new_funding": float(a.projected_new_funding),
                "shortfall": float(a.shortfall),
                "achievement_ratio": float(a.achievement_ratio),
            }
        )

    arm = ArmResult(
        algorithm=run.algorithm,
        status=run.status,
        feasible=run.feasible,
        allocations=allocations,
        summary=payload.get("summary", {}) or {},
        constraints=payload.get("constraints", {}) or {},
        diagnostics=payload.get("diagnostics", {}) or {},
        objective_value=float(run.objective_value) if run.objective_value is not None else None,
        runtime_ms=run.runtime_ms,
        model_version=run.model_version,
        config_version=run.config_version,
        warnings=json.loads(run.warnings_json or "[]"),
        label=payload.get("label", ""),
    )

    goals = load_goals(db, user.id)
    try:
        cashflow = load_cashflow(db, user.id)
    except ValidationFailure:
        from app.services.cashflow import CashFlow

        cashflow = CashFlow()

    diff = diff_runs(db, previous_run(db, user.id, "plan", exclude_id=run.id), run)
    return build_plan_response(
        db,
        run,
        arm,
        cashflow=cashflow,
        goals=goals,
        assumptions=json.loads(run.assumptions_json or "{}"),
        diff=diff,
    )


@router.post(
    "/optimize/compare",
    response_model=ComparisonResponse,
    dependencies=[Depends(enforce_optimize_rate_limit)],
)
def compare_algorithms(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    cashflow = load_cashflow(db, user.id)
    goals = load_goals(db, user.id)
    if not goals:
        raise ValidationFailure("Create at least one active goal before comparing algorithms.")
    lookup = months_lookup(goals)

    comparison = selector.compare(goals=goals, cashflow=cashflow, months_lookup=lookup)

    run = OptimizationRun(
        user_id=user.id,
        kind="compare",
        algorithm=comparison["recommended_algorithm"],
        status="optimal" if comparison["arms"] else "error",
        feasible=any(a["feasible"] for a in comparison["arms"]),
        assumptions_json=json.dumps(
            assumptions_for(db, user.id).as_dict(), default=str
        ),
        input_snapshot_json=json.dumps(
            {"goal_count": len(goals), "monthly_surplus": cashflow.monthly_surplus}, default=str
        ),
        result_json=json.dumps(comparison, default=str),
        runtime_ms=comparison["runtime_ms"],
        model_version=selector.SELECTOR_VERSION,
        config_version="selector",
        warnings_json=json.dumps(comparison["notes"], default=str),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return ComparisonResponse(run_id=run.id, created_at=run.created_at, **comparison)


@router.get("/optimize/runs")
def list_runs(
    kind: str | None = Query(default=None, pattern="^(plan|compare|scenario)$"),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    stmt = select(OptimizationRun).where(OptimizationRun.user_id == user.id)
    if kind:
        stmt = stmt.where(OptimizationRun.kind == kind)
    rows = db.execute(
        stmt.order_by(OptimizationRun.created_at.desc(), OptimizationRun.id.desc())
        .offset(offset)
        .limit(limit)
    ).scalars().all()
    return {
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": r.id,
                "kind": r.kind,
                "algorithm": r.algorithm,
                "status": r.status,
                "feasible": r.feasible,
                "objective_definition": OBJECTIVE_DEFINITION,
                "objective_value": float(r.objective_value) if r.objective_value is not None else None,
                "weighted_achievement": (
                    float(r.weighted_achievement) if r.weighted_achievement is not None else None
                ),
                "total_shortfall": (
                    float(r.total_shortfall) if r.total_shortfall is not None else None
                ),
                "runtime_ms": r.runtime_ms,
                "model_version": r.model_version,
                "created_at": r.created_at,
                "warnings": json.loads(r.warnings_json or "[]"),
            }
            for r in rows
        ],
    }


@router.get("/optimize/runs/{run_id}")
def read_run(
    run_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    run = db.execute(
        select(OptimizationRun).where(
            OptimizationRun.id == run_id, OptimizationRun.user_id == user.id
        )
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError(f"Optimization run {run_id} was not found")
    payload = json.loads(run.result_json or "{}")
    allocations = [
        {
            "goal_ref": a.goal_ref,
            "goal_id": a.goal_id,
            "db_goal_id": a.goal_id,
            "goal_name": a.goal_name,
            "funding_gap": float(a.funding_gap),
            "future_goal_cost": float(a.future_goal_cost),
            "existing_funding": float(a.existing_funding),
            "initial_savings_allocated": float(a.initial_savings_allocated),
            "existing_assets_allocated": float(a.existing_assets_allocated),
            "monthly_savings_contribution": float(a.monthly_savings_contribution),
            "monthly_investment_contribution": float(a.monthly_investment_contribution),
            "loan_principal": float(a.loan_principal),
            "estimated_loan_emi": float(a.estimated_loan_emi),
            "estimated_loan_interest_cost": float(a.estimated_loan_interest_cost),
            "shortfall": float(a.shortfall),
            "achievement_ratio": float(a.achievement_ratio),
            "projected_new_funding": float(a.projected_new_funding),
        }
        for a in db.execute(
            select(GoalAllocation).where(GoalAllocation.optimization_run_id == run.id)
        ).scalars()
    ]

    # A persisted run must be re-readable through the same contract as a fresh one. This
    # endpoint previously built the allocation list and then returned nothing, so every caller
    # received `null` with HTTP 200.
    goals = load_goals(db, user.id)
    try:
        cashflow = load_cashflow(db, user.id)
    except ValidationFailure:
        from app.services.cashflow import CashFlow

        cashflow = CashFlow()

    arm = ArmResult(
        algorithm=run.algorithm,
        status=run.status,
        feasible=run.feasible,
        allocations=allocations,
        summary=payload.get("summary", {}) or {},
        constraints=payload.get("constraints", {}) or {},
        diagnostics=payload.get("diagnostics", {}) or {},
        objective_value=float(run.objective_value) if run.objective_value is not None else None,
        runtime_ms=run.runtime_ms,
        model_version=run.model_version,
        config_version=run.config_version,
        warnings=json.loads(run.warnings_json or "[]"),
        fallback_reason=payload.get("fallback_reason"),
        label=payload.get("label", ""),
    )
    diff = diff_runs(db, previous_run(db, user.id, run.kind, exclude_id=run.id), run)
    return build_plan_response(
        db,
        run,
        arm,
        cashflow=cashflow,
        goals=goals,
        assumptions=json.loads(run.assumptions_json or "{}"),
        diff=diff,
    )


@router.get("/models/registry")
def model_registry(_admin: User = Depends(require_admin)):
    """The model versions this platform uses, with their true status."""
    research = research_loader.status()
    rl = rl_engine.readiness()
    entries = [
        {
            "name": "multi_goal_lp",
            "version": lp_engine.LP_UNCONSTRAINED_MODEL_VERSION,
            "kind": "lp",
            "status": "available_for_comparison_only",
            "artifact_path": "GoalPilot_MultiGoal_Extension/src/multi_goal_optimizer.py",
            "metadata": {
                "note": (
                    "Does not respect the executable investment capacity; the research audit "
                    "showed its apparent advantage was an accounting artefact (F-04)."
                )
            },
            "evaluated_at": None,
        },
        {
            "name": "constrained_lp",
            "version": lp_engine.LP_MODEL_VERSION,
            "kind": "lp",
            "status": "ready" if research.available else "unavailable",
            "artifact_path": "simulation/05_simulation_runs/rl_prototype/goalpilot_constrained_lp.py",
            "metadata": {
                "solver": "scipy.optimize.linprog(method='highs')",
                "role": "The LP arm and the default allocator.",
                "research_metrics": {
                    "weighted_goal_achievement": 0.2452,
                    "pct_goals_met_by_deadline": 0.1531,
                    "cohort": "16 fresh held-out test users",
                },
            },
            "evaluated_at": None,
        },
        {
            "name": "ppo_recommended_v1",
            "version": rl_engine.RL_MODEL_VERSION,
            "kind": "rl",
            "status": "ready" if rl.get("available") else "unavailable",
            "artifact_path": rl.get("checkpoint") or "",
            "metadata": {
                "preset": "recommended()",
                "goal_slots": rl_engine.RL_GOAL_SLOTS,
                "checkpoints_available": rl.get("checkpoint_count", 0),
                "research_metrics": {
                    "weighted_goal_achievement": 0.4842,
                    "pct_goals_met_by_deadline": 0.1083,
                    "cohort": "16 fresh held-out test users",
                    "note": (
                        "Below a simple investment rule (0.5800). Reported as a negative result."
                    ),
                },
            },
            "evaluated_at": None,
        },
        {
            "name": "hybrid_theta_governed_lp",
            "version": "hybrid_rl_theta_lp@v1",
            "kind": "hybrid",
            "status": "ready" if rl.get("available") else "degraded_to_lp",
            "artifact_path": "backend/app/engines/hybrid_engine.py",
            "metadata": {
                "architecture": "RL proposes theta, LP allocates, simulator evaluates",
                "superiority_claimed": False,
                "note": (
                    "Built and end-to-end tested in this platform. No superiority over the LP "
                    "is claimed: the selector only recommends it if it clears a stated margin."
                ),
            },
            "evaluated_at": None,
        },
        {
            "name": "expense_forecaster",
            "version": "forecast_v1",
            "kind": "forecast",
            "status": "ready",
            "artifact_path": "backend/app/services/forecasting.py",
            "metadata": {
                "methods": [
                    "baseline_recurring",
                    "baseline_estimate",
                    "rolling_mean_3",
                    "ewma_0.5",
                    "recurring_median",
                ],
                "selection": "walk-forward backtest must beat the baseline",
                "cross_user_learning": False,
            },
            "evaluated_at": None,
        },
    ]
    return {
        "research": research.as_dict(),
        "entries": entries,
        "note": (
            "Statuses reflect what is genuinely executable at request time. A model is never "
            "reported ready because a file exists."
        ),
    }


@router.get("/models/benchmarks")
def benchmarks(_admin: User = Depends(require_admin), limit: int = Query(default=20, ge=1, le=100)):
    """Sample of the research benchmark population, clearly labelled as synthetic."""
    if not research_loader.is_available():
        return {"available": False, "items": [], "note": "Research project unavailable."}
    try:
        profiles = research_loader.benchmark_profiles(limit)
        split = research_loader.benchmark_split()
    except Exception as exc:
        return {"available": False, "items": [], "note": str(exc)}
    splits = dict(zip(split["user_id"].astype(str), split["split"].astype(str)))
    items = []
    for _, row in profiles.iterrows():
        uid = str(row["user_id"])
        items.append(
            {
                "user_id": uid,
                "split": splits.get(uid, "unknown"),
                "monthly_income": round(float(row["monthly_income"]), 2),
                "monthly_expenditure": round(float(row["monthly_expenditure"]), 2),
                "monthly_emi": round(float(row["monthly_emi"]), 2),
                "initial_savings": round(float(row["initial_savings"]), 2),
                "initial_investment": round(float(row["initial_investment"]), 2),
                "financial_situation": row.get("financial_situation"),
                "risk_profile": row.get("risk_profile"),
                "goal_outcome": row.get("goal_outcome"),
            }
        )
    return {
        "available": True,
        "count": len(items),
        "items": items,
        "note": (
            "Synthetic research population. These are not real people and their values are not "
            "presented as verified personal finances."
        ),
    }


@router.get("/models/checkpoints")
def checkpoints(_admin: User = Depends(require_admin)):
    if not research_loader.is_available():
        return {"available": False, "items": []}
    items = research_loader.list_checkpoints()
    return {
        "available": True,
        "count": len(items),
        "items": items,
        "note": (
            "A checkpoint is only usable with the configuration it was trained under. The "
            "platform refuses a mismatched pair rather than reinterpreting a policy."
        ),
    }


@router.get("/models/research-evaluation")
def research_evaluation(_admin: User = Depends(require_admin)):
    summary = research_loader.evaluation_summary()
    if not summary.get("available"):
        return {
            "available": False,
            "note": "The recorded research evaluation artefacts could not be read.",
        }
    return {
        "available": True,
        "v8_ppo_held_out": summary.get("v8", []),
        "v7_constrained_lp": summary.get("v7", []),
        "note": (
            "These are the research project's own recorded held-out results, copied verbatim "
            "from its output CSVs. They are not recomputed by this application."
        ),
    }


