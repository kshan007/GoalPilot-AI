"""Scenario simulation."""
from __future__ import annotations

import copy
import datetime as dt
import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import current_user, enforce_optimize_rate_limit
from app.core.errors import NotFoundError, ValidationFailure
from app.db import get_db
from app.engines import lp_engine
from app.models import Goal, Scenario, ScenarioRun, User
from app.schemas.optimization import ScenarioPresetOut, ScenarioRunOut, ScenarioRunRequest
from app.services import scenarios as scenario_service
from app.services.planner import (
    assumptions_for,
    build_plan_response,
    load_cashflow,
    load_goals,
    months_lookup,
    persist_run,
    run_algorithm,
)

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("/presets", response_model=list[ScenarioPresetOut])
def list_presets():
    return [ScenarioPresetOut(**p) for p in scenario_service.list_presets()]


def _apply_goal_delays(
    db: Session, goals: list[Goal], new_dates: dict[int, dt.date]
) -> None:
    for goal in goals:
        if goal.id in new_dates:
            goal.target_date = new_dates[goal.id]
    db.flush()


@router.post(
    "/run",
    response_model=ScenarioRunOut,
    dependencies=[Depends(enforce_optimize_rate_limit)],
)
def run_scenario(
    payload: ScenarioRunRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Run a baseline plan and its stressed counterpart under one assumption set.

    Both cases are solved with the same algorithm and the same assumptions except for the
    parameters the scenario names, so the difference is attributable to the shock.
    """
    if payload.preset not in scenario_service.PRESETS:
        raise ValidationFailure(
            f"Unknown scenario preset '{payload.preset}'.",
            details={"allowed": sorted(scenario_service.PRESETS)},
        )

    cashflow = load_cashflow(db, user.id)
    goals = load_goals(db, user.id)
    if not goals:
        raise ValidationFailure("Create at least one active goal before running a scenario.")
    base_assumptions = assumptions_for(db, user.id)

    baseline_result = run_algorithm(
        algorithm=payload.algorithm if payload.algorithm != "rule_baseline" else "lp",
        goals=goals,
        cashflow=cashflow,
        lookup=months_lookup(goals),
        assumptions=base_assumptions,
    )
    baseline_run = persist_run(
        db, user.id, baseline_result, kind="scenario",
        assumptions=base_assumptions.as_dict(),
        input_snapshot={"scenario": "baseline", "preset": payload.preset},
        goal_db_ids={f"G{g.id}": g.id for g in goals},
        label="scenario baseline",
    )
    baseline_payload = {
        "run_id": baseline_run.id,
        "status": baseline_result.status,
        "summary": baseline_result.summary,
        "cashflow": cashflow.as_dict(),
    }

    # ---- stressed case ---------------------------------------------------------------
    stressed_cf, params, narrative = scenario_service.apply_to_cashflow(
        cashflow, payload.preset, payload.parameters
    )
    overrides = scenario_service.assumption_overrides(
        payload.preset, params, base_assumptions.as_dict()
    )
    stressed_assumptions = lp_engine.LpAssumptions(**overrides)

    original_dates: dict[int, dt.date] = {}
    if payload.preset == "delayed_goals":
        new_dates = scenario_service.delay_goals(goals, int(params.get("delay_months", 12)))
        for g in goals:
            if g.id in new_dates:
                original_dates[g.id] = g.target_date
        _apply_goal_delays(db, goals, new_dates)

    try:
        stressed_result = run_algorithm(
            algorithm=payload.algorithm if payload.algorithm != "rule_baseline" else "lp",
            goals=goals,
            cashflow=stressed_cf,
            lookup=months_lookup(goals),
            assumptions=stressed_assumptions,
        )
    finally:
        # The stored goals are never silently rewritten by a scenario.
        for goal in goals:
            if goal.id in original_dates:
                goal.target_date = original_dates[goal.id]
        db.flush()

    stressed_run = persist_run(
        db, user.id, stressed_result, kind="scenario",
        assumptions=stressed_assumptions.as_dict(),
        input_snapshot={"scenario": "stressed", "preset": payload.preset, "parameters": params},
        goal_db_ids={f"G{g.id}": g.id for g in goals},
        label=f"scenario {payload.preset}",
    )
    stressed_payload = {
        "run_id": stressed_run.id,
        "status": stressed_result.status,
        "summary": stressed_result.summary,
        "cashflow": stressed_cf.as_dict(),
    }

    deltas = scenario_service.diff_plans(baseline_payload, stressed_payload)
    narrative = narrative + scenario_service.narrate(baseline_payload, stressed_payload, deltas)

    scenario = Scenario(
        user_id=user.id,
        name=payload.name or scenario_service.PRESETS[payload.preset].name,
        preset=payload.preset,
        parameters_json=json.dumps(params),
    )
    db.add(scenario)
    db.flush()
    run = ScenarioRun(
        user_id=user.id,
        scenario_id=scenario.id,
        baseline_run_id=baseline_run.id,
        stressed_run_id=stressed_run.id,
        result_json=json.dumps(
            {"baseline": baseline_payload, "stressed": stressed_payload, "narrative": narrative},
            default=str,
        ),
        deltas_json=json.dumps(deltas, default=str),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    return ScenarioRunOut(
        id=run.id,
        preset=payload.preset,
        name=scenario.name,
        parameters=params,
        baseline=baseline_payload,
        stressed=stressed_payload,
        deltas=deltas,
        narrative=narrative,
        created_at=run.created_at,
    )


@router.get("/runs")
def list_scenario_runs(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(ScenarioRun)
        .where(ScenarioRun.user_id == user.id)
        .order_by(ScenarioRun.created_at.desc())
        .limit(limit)
    ).scalars().all()
    out = []
    for r in rows:
        payload = json.loads(r.result_json or "{}")
        scenario = db.get(Scenario, r.scenario_id) if r.scenario_id else None
        out.append(
            {
                "id": r.id,
                # This previously evaluated `json.loads(...) and None`, which is always None:
                # every row in the history claimed not to know its own preset.
                "preset": scenario.preset if scenario else None,
                "name": scenario.name if scenario else None,
                "baseline_run_id": r.baseline_run_id,
                "stressed_run_id": r.stressed_run_id,
                "narrative": payload.get("narrative", []),
                "created_at": r.created_at,
            }
        )
    return {"limit": limit, "items": out}


@router.get("/runs/{run_id}")
def read_scenario_run(
    run_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = db.execute(
        select(ScenarioRun).where(ScenarioRun.id == run_id, ScenarioRun.user_id == user.id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Scenario run {run_id} was not found")
    scenario = db.get(Scenario, row.scenario_id) if row.scenario_id else None
    return {
        "id": row.id,
        "preset": scenario.preset if scenario else None,
        "name": scenario.name if scenario else None,
        "parameters": json.loads(scenario.parameters_json) if scenario else {},
        "baseline": json.loads(row.result_json or "{}").get("baseline", {}),
        "stressed": json.loads(row.result_json or "{}").get("stressed", {}),
        "deltas": json.loads(row.deltas_json or "{}"),
        "narrative": json.loads(row.result_json or "{}").get("narrative", []),
        "created_at": row.created_at,
    }
